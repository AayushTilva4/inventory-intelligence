import unittest
import math
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.inventory.recommendation_engine import build_recommendation
from app.inventory.group_recommendation_service import get_group_recommendation


class TestInventoryPositionCalculation(unittest.TestCase):
    """
    Phase 2 Task 4: Tests for Canonical Inventory Position Calculation:
    Inventory Position = Usable Stock + Incoming Stock - Committed Customer Demand
    """

    def test_1_no_incoming_stock(self):
        """1. When there is no incoming stock, inventory position is usable_stock - committed_stock."""
        row = {
            "next_month_forecast": 100.0,
            "stock_on_hand": 200.0,
            "usable_stock": 180.0,
            "cut_piece_stock": 20.0,
            "incoming_stock": 0.0,
            "committed_stock": 30.0,
            "reorder_point": 300.0,
            "confidence": "high",
        }
        rec = build_recommendation(row)
        # Expected inventory position: 180 + 0 - 30 = 150.0
        self.assertEqual(rec["inventory_position"], 150.0)
        # Buffered target: 300 * 1.10 = 330.0
        self.assertEqual(rec["buffered_target_stock"], 330.0)
        # Stock gap: 330 - 150 = 180.0
        self.assertEqual(rec["stock_gap"], 180.0)
        self.assertEqual(rec["suggested_purchase_qty"], 180)
        self.assertEqual(rec["action"], "purchase")

    def test_2_incoming_stock_fully_covers_deficit(self):
        """2. When incoming stock fully covers the deficit, suggested purchase drops to 0."""
        row = {
            "next_month_forecast": 50.0,
            "stock_on_hand": 50.0,
            "usable_stock": 50.0,
            "incoming_stock": 300.0,
            "committed_stock": 0.0,
            "reorder_point": 200.0,
            "confidence": "normal",
        }
        rec = build_recommendation(row)
        # Buffered target: 200 * 1.10 = 220.0
        # Inventory position: 50 + 300 - 0 = 350.0
        self.assertEqual(rec["inventory_position"], 350.0)
        self.assertEqual(rec["stock_gap"], 0.0)
        self.assertEqual(rec["suggested_purchase_qty"], 0)
        self.assertEqual(rec["action"], "hold")
        self.assertIn("covered_by_incoming_stock", rec["reason_codes"])

    def test_3_incoming_stock_partially_covers_deficit(self):
        """3. When incoming stock partially covers deficit, suggested purchase is target - inventory_position."""
        row = {
            "next_month_forecast": 50.0,
            "stock_on_hand": 50.0,
            "usable_stock": 50.0,
            "incoming_stock": 100.0,
            "committed_stock": 0.0,
            "reorder_point": 200.0,
            "confidence": "high",
        }
        rec = build_recommendation(row)
        # Target: 220.0
        # Inventory position: 50 + 100 = 150.0
        # Gap: 220 - 150 = 70.0
        self.assertEqual(rec["inventory_position"], 150.0)
        self.assertEqual(rec["stock_gap"], 70.0)
        self.assertEqual(rec["suggested_purchase_qty"], 70)
        self.assertEqual(rec["action"], "purchase")
        self.assertIn("partial_incoming_coverage", rec["reason_codes"])

    def test_4_incoming_plus_usable_exceeds_target_excess(self):
        """4. When incoming + usable stock exceeds 2x buffered target, classify as excess_stock."""
        row = {
            "next_month_forecast": 50.0,
            "stock_on_hand": 100.0,
            "usable_stock": 100.0,
            "incoming_stock": 400.0,
            "committed_stock": 0.0,
            "reorder_point": 150.0,
            "confidence": "normal",
        }
        rec = build_recommendation(row)
        # Target: 150 * 1.10 = 165.0; 2x target = 330.0
        # Inventory position: 100 + 400 = 500.0 (>= 330.0)
        self.assertEqual(rec["inventory_position"], 500.0)
        self.assertEqual(rec["suggested_purchase_qty"], 0)
        self.assertEqual(rec["action"], "excess_stock")
        self.assertIn("stock_far_above_target", rec["reason_codes"])

    def test_5_committed_customer_quantity_reduces_usable_position(self):
        """5. Committed customer demand reduces inventory position, preventing under-ordering."""
        # Without commitment
        row_no_commit = {
            "next_month_forecast": 50.0,
            "stock_on_hand": 220.0,
            "usable_stock": 220.0,
            "incoming_stock": 0.0,
            "committed_stock": 0.0,
            "reorder_point": 200.0,
            "confidence": "high",
        }
        rec_no_commit = build_recommendation(row_no_commit)
        self.assertEqual(rec_no_commit["suggested_purchase_qty"], 0)
        self.assertEqual(rec_no_commit["action"], "hold")

        # With 100 units committed to open customer delivery orders
        row_with_commit = {
            "next_month_forecast": 50.0,
            "stock_on_hand": 220.0,
            "usable_stock": 220.0,
            "incoming_stock": 0.0,
            "committed_stock": 100.0,
            "reorder_point": 200.0,
            "confidence": "high",
        }
        rec_with_commit = build_recommendation(row_with_commit)
        # Position: 220 - 100 = 120.0
        # Target: 220.0 -> Gap = 100.0
        self.assertEqual(rec_with_commit["inventory_position"], 120.0)
        self.assertEqual(rec_with_commit["suggested_purchase_qty"], 100)
        self.assertEqual(rec_with_commit["action"], "purchase")
        self.assertIn("committed_customer_demand_deducted", rec_with_commit["reason_codes"])

    def test_6_cut_pieces_excluded_from_usable_position(self):
        """6. Cut piece stock is excluded from usable inventory position."""
        row = {
            "next_month_forecast": 50.0,
            "stock_on_hand": 300.0,     # Total on-hand includes cut pieces
            "usable_stock": 100.0,     # Only 100 is usable
            "cut_piece_stock": 200.0,  # 200 is cut pieces
            "incoming_stock": 0.0,
            "committed_stock": 0.0,
            "reorder_point": 200.0,
            "confidence": "high",
        }
        rec = build_recommendation(row)
        # Position: 100.0 (cut pieces excluded)
        # Target: 220.0 -> Gap: 120.0
        self.assertEqual(rec["inventory_position"], 100.0)
        self.assertEqual(rec["usable_stock"], 100.0)
        self.assertEqual(rec["cut_piece_stock"], 200.0)
        self.assertEqual(rec["suggested_purchase_qty"], 120)
        self.assertEqual(rec["action"], "purchase")

    def test_7_negative_inventory_position_covers_backlog_deficit(self):
        """7. Negative inventory position correctly adds customer backlog to purchase quantity."""
        row = {
            "next_month_forecast": 50.0,
            "stock_on_hand": 20.0,
            "usable_stock": 20.0,
            "incoming_stock": 10.0,
            "committed_stock": 100.0,  # Backlog exceeding inventory
            "reorder_point": 100.0,    # Target = 110.0
            "confidence": "high",
        }
        rec = build_recommendation(row)
        # Position: 20 + 10 - 100 = -70.0 (unclamped)
        self.assertEqual(rec["inventory_position"], -70.0)
        # Target: 110.0 -> Gap: 110 - (-70) = 180.0
        self.assertEqual(rec["stock_gap"], 180.0)
        self.assertEqual(rec["suggested_purchase_qty"], 180)
        self.assertEqual(rec["action"], "purchase")

    def test_8_group_level_aggregation(self):
        """8. Group-level recommendation correctly combines multiple variants."""
        # Simulated group with 3 members
        member_1 = {"usable_qty": 50.0, "incoming_qty": 20.0, "outgoing_qty": 5.0}
        member_2 = {"usable_qty": 30.0, "incoming_qty": 80.0, "outgoing_qty": 10.0}
        member_3 = {"usable_qty": 20.0, "incoming_qty": 0.0, "outgoing_qty": 0.0}

        group_usable = sum(m["usable_qty"] for m in [member_1, member_2, member_3])  # 100.0
        group_incoming = sum(m["incoming_qty"] for m in [member_1, member_2, member_3])  # 100.0
        group_committed = sum(m["outgoing_qty"] for m in [member_1, member_2, member_3])  # 15.0

        group_inv_pos = group_usable + group_incoming - group_committed  # 185.0
        self.assertEqual(group_inv_pos, 185.0)

        row = {
            "next_month_forecast": 40.0,
            "usable_stock": group_usable,
            "incoming_stock": group_incoming,
            "committed_stock": group_committed,
            "reorder_point": 150.0,  # Target = 165.0
            "confidence": "high",
        }
        rec = build_recommendation(row)
        # Target: 165.0, Position: 185.0 -> Gap: 0, Suggested: 0, Action: hold
        self.assertEqual(rec["inventory_position"], 185.0)
        self.assertEqual(rec["suggested_purchase_qty"], 0)
        self.assertEqual(rec["action"], "hold")

    def test_9_mentor_413_11_regression_case(self):
        """
        9. Mentor 413-11 Regression Case:
        0 on-hand stock, 1,054 units incoming on PO P03497.
        Must NOT suggest ordering another 806 units when 1,054 units are already incoming.
        """
        row_413_11 = {
            "next_month_forecast": 0.0,
            "stock_on_hand": 0.0,
            "usable_stock": 0.0,
            "cut_piece_stock": 0.0,
            "incoming_stock": 1054.0,  # Open PO P03497
            "committed_stock": 0.0,
            "reorder_point": 633.3,   # Target = 696.63
            "confidence": "normal",
        }
        rec = build_recommendation(row_413_11)

        # Inventory position: 0 + 1054 - 0 = 1054.0
        self.assertEqual(rec["inventory_position"], 1054.0)
        # Buffered target: 633.3 * 1.10 = 696.63
        self.assertEqual(rec["buffered_target_stock"], 696.63)
        # Gap: max(696.63 - 1054.0, 0) = 0.0
        self.assertEqual(rec["stock_gap"], 0.0)
        # Suggested purchase MUST be 0 (preventing double-ordering of 806 to 3,000 units)
        self.assertEqual(rec["suggested_purchase_qty"], 0)
        self.assertEqual(rec["action"], "hold")
        self.assertIn("covered_by_incoming_stock", rec["reason_codes"])

    def test_10_mentor_sanity_cases_1_to_4(self):
        """
        10. Final Sanity Check Cases from Mentor Specification:
        Case 1: usable=0, incoming=0, committed=100, target=200 -> position=-100, gap=300
        Case 2: usable=50, incoming=20, committed=100, target=200 -> position=-30, gap=230
        Case 3: usable=100, incoming=50, committed=20, target=100 -> position=130, gap=0
        Case 4: usable=0, incoming=1054, committed=0, target=806 -> position=1054, gap=0
        """
        # Case 1
        # To get buffered target = 200.0: reorder_point = 200 / 1.10 = 181.8181818181818
        row1 = {
            "usable_stock": 0.0,
            "incoming_stock": 0.0,
            "committed_stock": 100.0,
            "reorder_point": 200.0 / 1.10,
            "confidence": "high",
        }
        rec1 = build_recommendation(row1)
        self.assertEqual(rec1["inventory_position"], -100.0)
        self.assertEqual(rec1["buffered_target_stock"], 200.0)
        self.assertEqual(rec1["stock_gap"], 300.0)
        self.assertEqual(rec1["suggested_purchase_qty"], 300)
        self.assertEqual(rec1["action"], "purchase")

        # Case 2
        row2 = {
            "usable_stock": 50.0,
            "incoming_stock": 20.0,
            "committed_stock": 100.0,
            "reorder_point": 200.0 / 1.10,
            "confidence": "high",
        }
        rec2 = build_recommendation(row2)
        self.assertEqual(rec2["inventory_position"], -30.0)
        self.assertEqual(rec2["buffered_target_stock"], 200.0)
        self.assertEqual(rec2["stock_gap"], 230.0)
        self.assertEqual(rec2["suggested_purchase_qty"], 230)
        self.assertEqual(rec2["action"], "purchase")

        # Case 3
        row3 = {
            "usable_stock": 100.0,
            "incoming_stock": 50.0,
            "committed_stock": 20.0,
            "reorder_point": 100.0 / 1.10,
            "confidence": "high",
        }
        rec3 = build_recommendation(row3)
        self.assertEqual(rec3["inventory_position"], 130.0)
        self.assertEqual(rec3["buffered_target_stock"], 100.0)
        self.assertEqual(rec3["stock_gap"], 0.0)
        self.assertEqual(rec3["suggested_purchase_qty"], 0)
        self.assertEqual(rec3["action"], "hold")

        # Case 4
        row4 = {
            "usable_stock": 0.0,
            "incoming_stock": 1054.0,
            "committed_stock": 0.0,
            "reorder_point": 806.0 / 1.10,
            "confidence": "normal",
        }
        rec4 = build_recommendation(row4)
        self.assertEqual(rec4["inventory_position"], 1054.0)
        self.assertEqual(rec4["buffered_target_stock"], 806.0)
        self.assertEqual(rec4["stock_gap"], 0.0)
        self.assertEqual(rec4["suggested_purchase_qty"], 0)
        self.assertEqual(rec4["action"], "hold")


if __name__ == "__main__":
    unittest.main()
