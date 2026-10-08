import calendar
import datetime
import math
import sys
from pathlib import Path
import unittest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.inventory.recommendation_engine import build_recommendation


class TestForecastBasedOrderQuantity(unittest.TestCase):
    """
    Phase 2 — Task 5: Tests for Forecast-Driven Order Quantity across
    Lead Time (3 months) + Review Period (1 month) Operational Horizon.
    """

    def test_1_forecast_driven_order_quantity_basic(self):
        """1. Order quantity derives directly from forecast over operational horizon."""
        row = {
            "next_month_forecast": 50.0,
            "stock_on_hand": 50.0,
            "usable_stock": 50.0,
            "incoming_stock": 0.0,
            "committed_stock": 0.0,
            "lead_time_months": 3.0,
            "review_period_months": 1.0,
            "confidence": "high",
        }
        rec = build_recommendation(row)
        # Horizon demand: 50.0 * (3.0 + 1.0) = 200.0
        self.assertEqual(rec["lead_time_demand"], 150.0)
        self.assertEqual(rec["review_period_demand"], 50.0)
        self.assertEqual(rec["forecasted_horizon_demand"], 200.0)
        self.assertEqual(rec["reorder_point"], 200.0)
        # Target: 200 * 1.10 = 220.0
        self.assertEqual(rec["buffered_target_stock"], 220.0)
        # Stock gap: 220 - 50 = 170.0
        self.assertEqual(rec["stock_gap"], 170.0)
        self.assertEqual(rec["suggested_purchase_qty"], 170)
        self.assertEqual(rec["action"], "purchase")

    def test_2_lead_time_and_review_period_separation(self):
        """2. Lead time (3m) and Review Period (1m) demands are explicitly tracked."""
        row = {
            "lead_time_demand": 300.0,
            "review_period_demand": 100.0,
            "usable_stock": 200.0,
            "incoming_stock": 50.0,
            "committed_stock": 0.0,
            "confidence": "high",
        }
        rec = build_recommendation(row)
        self.assertEqual(rec["lead_time_demand"], 300.0)
        self.assertEqual(rec["review_period_demand"], 100.0)
        self.assertEqual(rec["forecasted_horizon_demand"], 400.0)
        # Target: 400 * 1.10 = 440.0
        # Position: 200 + 50 = 250.0
        # Gap: 440 - 250 = 190.0
        self.assertEqual(rec["inventory_position"], 250.0)
        self.assertEqual(rec["stock_gap"], 190.0)
        self.assertEqual(rec["suggested_purchase_qty"], 190)

    def test_3_partial_current_month_weighting(self):
        """3. Current month partial days correctly scales horizon demand."""
        # Simulated as-of Oct 8 in a 31-day month: 23 days remaining
        # w0 = 23 / 31 = 0.7419
        w0 = 23.0 / 31.0
        # 5-step forecast: [100, 100, 100, 100, 100]
        mf = [100.0, 100.0, 100.0, 100.0, 100.0]
        lt_demand = (w0 * mf[0]) + mf[1] + mf[2] + ((1.0 - w0) * mf[3])
        rp_demand = (w0 * mf[3]) + ((1.0 - w0) * mf[4])
        horizon_demand = lt_demand + rp_demand

        # Must equal exactly 300.0 LT demand, 100.0 RP demand, 400.0 Horizon demand
        self.assertAlmostEqual(lt_demand, 300.0, places=4)
        self.assertAlmostEqual(rp_demand, 100.0, places=4)
        self.assertAlmostEqual(horizon_demand, 400.0, places=4)

        row = {
            "lead_time_demand": lt_demand,
            "review_period_demand": rp_demand,
            "forecasted_horizon_demand": horizon_demand,
            "usable_stock": 100.0,
            "incoming_stock": 0.0,
            "committed_stock": 0.0,
            "confidence": "high",
        }
        rec = build_recommendation(row)
        self.assertEqual(rec["buffered_target_stock"], 440.0)
        self.assertEqual(rec["suggested_purchase_qty"], 340)

    def test_4_incoming_stock_integration_prevents_duplicate_purchase(self):
        """4. Incoming purchase orders correctly reduce replenishment need."""
        row = {
            "next_month_forecast": 40.0,
            "usable_stock": 20.0,
            "incoming_stock": 160.0, # 160m incoming on open PO
            "committed_stock": 0.0,
            "confidence": "normal",
        }
        rec = build_recommendation(row)
        # Horizon demand: 40 * 4 = 160.0 -> Target = 176.0
        # Position: 20 + 160 = 180.0 (>= 176.0)
        self.assertEqual(rec["inventory_position"], 180.0)
        self.assertEqual(rec["stock_gap"], 0.0)
        self.assertEqual(rec["suggested_purchase_qty"], 0)
        self.assertEqual(rec["action"], "hold")
        self.assertIn("covered_by_incoming_stock", rec["reason_codes"])

    def test_5_committed_customer_demand_increases_purchase_need(self):
        """5. Customer commitments deduct from position, preventing stockouts."""
        row = {
            "next_month_forecast": 50.0,
            "usable_stock": 220.0,
            "incoming_stock": 0.0,
            "committed_stock": 100.0, # 100m committed to delivery orders
            "confidence": "high",
        }
        rec = build_recommendation(row)
        # Horizon demand: 50 * 4 = 200.0 -> Target = 220.0
        # Position: 220 - 100 = 120.0
        # Gap: 220 - 120 = 100.0
        self.assertEqual(rec["inventory_position"], 120.0)
        self.assertEqual(rec["suggested_purchase_qty"], 100)
        self.assertEqual(rec["action"], "purchase")

    def test_6_zero_forecast_suppresses_purchase(self):
        """6. When forecast is 0, target is 0 and suggested purchase is 0."""
        row = {
            "next_month_forecast": 0.0,
            "usable_stock": 10.0,
            "incoming_stock": 0.0,
            "committed_stock": 0.0,
            "confidence": "normal",
        }
        rec = build_recommendation(row)
        self.assertEqual(rec["forecasted_horizon_demand"], 0.0)
        self.assertEqual(rec["buffered_target_stock"], 0.0)
        self.assertEqual(rec["stock_gap"], 0.0)
        self.assertEqual(rec["suggested_purchase_qty"], 0)
        self.assertEqual(rec["action"], "hold")
        self.assertIn("zero_forecast", rec["reason_codes"])

    def test_7_excess_stock_classification(self):
        """7. When inventory position exceeds 2x buffered target, classify as excess_stock."""
        row = {
            "next_month_forecast": 20.0,
            "usable_stock": 200.0, # Target = 20 * 4 * 1.10 = 88.0. 200 >= 176.0
            "incoming_stock": 0.0,
            "committed_stock": 0.0,
            "confidence": "high",
        }
        rec = build_recommendation(row)
        self.assertEqual(rec["buffered_target_stock"], 88.0)
        self.assertEqual(rec["inventory_position"], 200.0)
        self.assertEqual(rec["action"], "excess_stock")
        self.assertEqual(rec["suggested_purchase_qty"], 0)

    def test_8_negative_inventory_position(self):
        """8. Negative inventory position adds backlog deficit to purchase order."""
        row = {
            "next_month_forecast": 50.0,
            "usable_stock": 0.0,
            "incoming_stock": 0.0,
            "committed_stock": 100.0, # 100m backlog
            "confidence": "high",
        }
        rec = build_recommendation(row)
        # Horizon demand: 50 * 4 = 200.0 -> Target = 220.0
        # Position: -100.0
        # Gap: 220 - (-100) = 320.0
        self.assertEqual(rec["inventory_position"], -100.0)
        self.assertEqual(rec["stock_gap"], 320.0)
        self.assertEqual(rec["suggested_purchase_qty"], 320)
        self.assertEqual(rec["action"], "purchase")

    def test_9_dead_stock_hard_zero(self):
        """9. Dead stock forces 0 horizon demand, 0 target, and 0 purchase."""
        row = {
            "next_month_forecast": 50.0,
            "stock_on_hand": 100.0,
            "usable_stock": 100.0,
            "incoming_stock": 0.0,
            "committed_stock": 0.0,
            "dead_stock": True,
            "confidence": "normal",
        }
        rec = build_recommendation(row)
        self.assertEqual(rec["forecasted_horizon_demand"], 0.0)
        self.assertEqual(rec["buffered_target_stock"], 0.0)
        self.assertEqual(rec["suggested_purchase_qty"], 0)
        self.assertEqual(rec["action"], "dead_stock")

    def test_10_mentor_413_11_regression(self):
        """
        10. Mentor 413-11 Regression Case:
        0 stock, 1,054m incoming on PO P03497.
        Must NOT suggest ordering another 806 units when 1,054 units are incoming.
        """
        row_413_11 = {
            "next_month_forecast": 0.0,
            "forecasted_horizon_demand": 24.7,
            "usable_stock": 0.0,
            "incoming_stock": 1054.0,
            "committed_stock": 0.0,
            "confidence": "normal",
        }
        rec = build_recommendation(row_413_11)
        self.assertEqual(rec["inventory_position"], 1054.0)
        self.assertEqual(rec["suggested_purchase_qty"], 0)
        self.assertEqual(rec["action"], "excess_stock")
        self.assertIn("stock_far_above_target", rec["reason_codes"])

    def test_11_mentor_325_42_regression(self):
        """
        11. Mentor 325-42 Regression Case:
        High seasonal forecast (1,292m) previously shown as excess due to 6m historical average.
        Under forecast-based requirement, 461.3m stock is recognized as deficient, recommending purchase.
        """
        # Forecast: 1,292m for Nov, 0 for subsequent months -> Horizon demand = 958.58m
        row_325_42 = {
            "next_month_forecast": 1292.0,
            "lead_time_demand": 958.58,
            "review_period_demand": 0.0,
            "forecasted_horizon_demand": 958.58,
            "usable_stock": 247.1,
            "incoming_stock": 214.2,
            "committed_stock": 0.0,
            "confidence": "normal",
        }
        rec = build_recommendation(row_325_42)
        # Position: 247.1 + 214.2 = 461.3m
        self.assertEqual(rec["inventory_position"], 461.3)
        # Target: 958.58 * 1.10 = 1054.438
        self.assertAlmostEqual(rec["buffered_target_stock"], 1054.44, places=1)
        # Gap: 1054.44 - 461.3 = 593.14m -> Purchase 594m
        self.assertGreater(rec["suggested_purchase_qty"], 500)
        self.assertEqual(rec["action"], "purchase")
        self.assertNotEqual(rec["action"], "excess_stock")


if __name__ == "__main__":
    unittest.main()
