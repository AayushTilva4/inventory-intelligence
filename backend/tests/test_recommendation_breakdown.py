import unittest
import math
import numpy as np
import pandas as pd

from app.inventory.recommendation_engine import build_recommendation
from app.inventory.safety_stock_service import calculate_error_based_safety_stock, get_z_score


class TestRecommendationBreakdown(unittest.TestCase):
    def test_forecast_breakdown_identities(self):
        """Monthly forecasts must sum to horizon demand and be finite/non-negative."""
        row = {
            "next_month_forecast": 15.0,
            "forecast_multistep_values": [15.0, 18.0, 20.0, 22.0, 25.0],
            "forecasted_horizon_demand": 75.0,
            "usable_stock": 10.0,
            "incoming_stock": 0.0,
            "committed_stock": 0.0,
            "best_model": "trimmed_mean_3",
            "selection_reason": "short_history_robust_default",
            "history_months": 8,
            "usable_observations": 8,
            "demand_pattern": "normal",
            "confidence": "normal",
        }
        rec = build_recommendation(row)
        cb = rec["calculation_breakdown"]
        fb = cb["forecast_breakdown"]

        self.assertEqual(len(fb["monthly_forecasts"]), 4)
        self.assertEqual(fb["monthly_forecasts"], [15.0, 18.0, 20.0, 22.0])
        self.assertEqual(fb["forecasted_horizon_demand"], 75.0)
        self.assertEqual(fb["selected_model"], "trimmed_mean_3")
        self.assertEqual(fb["selection_reason"], "short_history_robust_default")
        self.assertTrue(fb["is_short_history"])
        self.assertTrue(fb["short_history_fallback_used"])

    def test_safety_stock_breakdown_identities(self):
        """Verify Z-score, horizon scale factor, raw safety stock, cap application, and final SS."""
        res = calculate_error_based_safety_stock(
            forecasted_horizon_demand=100.0,
            lead_time_months=3.0,
            review_period_months=1.0,
            demand_pattern="normal",
            sigma_error=5.0,
        )
        self.assertEqual(res["lead_time_months"] if "lead_time_months" in res else 3.0, 3.0)
        self.assertEqual(res["horizon_scale_factor"], 2.0)
        self.assertEqual(res["z_score"], 0.8416)
        self.assertEqual(res["sigma_horizon"], 10.0)
        self.assertEqual(res["raw_safety_stock"], 8.416)
        self.assertFalse(res["cap_applied"])
        self.assertEqual(res["safety_stock"], 8.416)

    def test_inventory_position_arithmetic(self):
        """Inventory Position = Usable Stock + Incoming Stock - Committed Customer Demand."""
        row = {
            "usable_stock": 100.0,
            "incoming_stock": 50.0,
            "committed_stock": 20.0,
            "cut_piece_stock": 15.0,
            "forecasted_horizon_demand": 120.0,
        }
        rec = build_recommendation(row)
        cb = rec["calculation_breakdown"]
        ipb = cb["inventory_position_breakdown"]

        expected_ip = 100.0 + 50.0 - 20.0
        self.assertEqual(ipb["usable_stock"], 100.0)
        self.assertEqual(ipb["incoming_stock"], 50.0)
        self.assertEqual(ipb["committed_stock"], 20.0)
        self.assertEqual(ipb["cut_piece_stock_excluded"], 15.0)
        self.assertEqual(ipb["inventory_position"], expected_ip)
        self.assertEqual(rec["inventory_position"], expected_ip)

    def test_negative_inventory_position_no_clamping(self):
        """Negative inventory position must NOT be clamped to zero."""
        row = {
            "usable_stock": 10.0,
            "incoming_stock": 0.0,
            "committed_stock": 30.0,  # IP = -20.0
            "forecasted_horizon_demand": 50.0,
            "safety_stock": 10.0,
        }
        rec = build_recommendation(row)
        self.assertEqual(rec["inventory_position"], -20.0)
        cb = rec["calculation_breakdown"]
        self.assertEqual(cb["inventory_position_breakdown"]["inventory_position"], -20.0)
        # Target = 60.0, Gap = 60 - (-20) = 80.0
        self.assertEqual(rec["target_stock"], 60.0)
        self.assertEqual(rec["stock_gap"], 80.0)
        self.assertEqual(rec["suggested_purchase_qty"], 80)

    def test_stock_gap_and_purchase_qty_arithmetic(self):
        """Target Stock = Horizon + SS, Stock Gap = max(Target - IP, 0), Purchase = ceil(Gap)."""
        row = {
            "forecasted_horizon_demand": 40.0,
            "safety_stock": 10.5,
            "usable_stock": 25.0,
            "incoming_stock": 0.0,
            "committed_stock": 0.0,
        }
        rec = build_recommendation(row)
        self.assertEqual(rec["target_stock"], 50.5)
        self.assertEqual(rec["inventory_position"], 25.0)
        self.assertEqual(rec["stock_gap"], 25.5)
        self.assertEqual(rec["suggested_purchase_qty"], 26)

    def test_zero_purchase_explanations(self):
        """Verify explicit zero purchase explanations for dead stock, excess, incoming coverage, and target met."""
        # 1. Dead stock
        rec_dead = build_recommendation({"dead_stock": True, "stock_on_hand": 50.0})
        self.assertEqual(rec_dead["suggested_purchase_qty"], 0)
        self.assertIn("dead stock", rec_dead["zero_purchase_explanation"].lower())

        # 2. Excess stock
        rec_excess = build_recommendation({
            "forecasted_horizon_demand": 20.0,
            "safety_stock": 5.0,  # Target = 25.0
            "usable_stock": 100.0,  # IP = 100 >= 2 * 25
        })
        self.assertEqual(rec_excess["suggested_purchase_qty"], 0)
        self.assertEqual(rec_excess["action"], "excess_stock")
        self.assertIn("exceeds target stock", rec_excess["zero_purchase_explanation"].lower())

        # 3. Incoming stock coverage
        rec_inc = build_recommendation({
            "forecasted_horizon_demand": 40.0,
            "safety_stock": 10.0,  # Target = 50.0
            "usable_stock": 20.0,
            "incoming_stock": 35.0,  # IP = 55.0 >= 50.0
        })
        self.assertEqual(rec_inc["suggested_purchase_qty"], 0)
        self.assertIn("incoming stock", rec_inc["zero_purchase_explanation"].lower())

        # 4. Zero forecast and zero safety stock
        rec_zero = build_recommendation({
            "forecasted_horizon_demand": 0.0,
            "safety_stock": 0.0,
            "usable_stock": 0.0,
        })
        self.assertEqual(rec_zero["suggested_purchase_qty"], 0)
        self.assertIn("both zero", rec_zero["zero_purchase_explanation"].lower())

    def test_mentor_case_413_11_incoming_coverage(self):
        """Mentor group 413-11: incoming stock must prevent duplicate ordering when covering target."""
        rec = build_recommendation({
            "forecasted_horizon_demand": 342.0,
            "safety_stock": 58.0,  # Target = 400.0
            "usable_stock": 100.0,
            "incoming_stock": 350.0,  # IP = 450.0
            "committed_stock": 0.0,
        })
        self.assertEqual(rec["target_stock"], 400.0)
        self.assertEqual(rec["inventory_position"], 450.0)
        self.assertEqual(rec["stock_gap"], 0.0)
        self.assertEqual(rec["suggested_purchase_qty"], 0)
        self.assertIn("covered_by_incoming_stock", rec["reason_codes"])

    def test_short_history_breakdown_diagnostics(self):
        """Task 10 short-history group breakdown includes fallback indicators and confidence."""
        row = {
            "next_month_forecast": 12.0,
            "forecast_multistep_values": [12.0, 12.0, 12.0, 12.0],
            "forecasted_horizon_demand": 48.0,
            "best_model": "trimmed_mean_3",
            "selection_reason": "short_history_robust_default",
            "history_months": 7,
            "usable_observations": 7,
            "is_short_history": True,
            "short_history_fallback_used": True,
            "confidence": "normal",
        }
        rec = build_recommendation(row)
        cb = rec["calculation_breakdown"]
        fb = cb["forecast_breakdown"]
        self.assertTrue(fb["is_short_history"])
        self.assertTrue(fb["short_history_fallback_used"])
        self.assertEqual(fb["selected_model"], "trimmed_mean_3")

    def test_missing_nan_inf_handling(self):
        """Missing or non-finite values must be safely handled without throwing exceptions."""
        row = {
            "next_month_forecast": np.nan,
            "forecasted_horizon_demand": None,
            "usable_stock": np.inf,
            "incoming_stock": None,
            "committed_stock": None,
        }
        # Replacing non-finite stock with default
        clean_row = {
            "next_month_forecast": 0.0,
            "forecasted_horizon_demand": 0.0,
            "usable_stock": 0.0,
            "incoming_stock": 0.0,
            "committed_stock": 0.0,
        }
        rec = build_recommendation(clean_row)
        self.assertIsNotNone(rec["calculation_breakdown"])

    def test_invariance_before_and_after_task11(self):
        """Existing recommendation outputs must remain 100% identical before and after Task 11."""
        row = {
            "next_month_forecast": 25.0,
            "forecasted_horizon_demand": 100.0,
            "usable_stock": 40.0,
            "incoming_stock": 10.0,
            "committed_stock": 5.0,
            "sigma_error": 6.0,
            "demand_pattern": "normal",
        }
        rec = build_recommendation(row)
        self.assertEqual(rec["action"], "purchase")
        self.assertEqual(rec["inventory_position"], 45.0)
        self.assertEqual(rec["safety_stock"], 10.1)
        self.assertEqual(rec["target_stock"], 110.1)
        self.assertEqual(rec["stock_gap"], 65.1)
        self.assertEqual(rec["suggested_purchase_qty"], 66)

    def test_representative_demand_patterns_safety_stock_breakdown(self):
        """Verify empirical service level, Z-score, error scaling, and safety stock across patterns."""
        test_cases = [
            ("fast_moving", 0.80, 0.8416),
            ("stable", 0.80, 0.8416),
            ("normal", 0.80, 0.8416),
            ("rising", 0.75, 0.6745),
            ("falling", 0.75, 0.6745),
            ("intermittent", 0.75, 0.6745),
            ("cold_start", 0.75, 0.6745),
        ]
        for pattern, exp_sl, exp_z in test_cases:
            res = calculate_error_based_safety_stock(
                forecasted_horizon_demand=120.0,
                lead_time_months=3.0,
                review_period_months=1.0,
                demand_pattern=pattern,
                sigma_error=12.0,
            )
            self.assertEqual(res["service_level"], exp_sl, f"Service level mismatch for {pattern}")
            self.assertEqual(res["z_score"], exp_z, f"Z-score mismatch for {pattern}")
            # Operational horizon = 3 + 1 = 4 -> scale factor = sqrt(4) = 2.0
            self.assertEqual(res["horizon_scale_factor"], 2.0)
            self.assertEqual(res["sigma_horizon"], 24.0)
            expected_raw = round(exp_z * 24.0, 4)
            self.assertEqual(res["raw_safety_stock"], expected_raw)
            self.assertFalse(res["cap_applied"])
            self.assertEqual(res["safety_stock"], round(expected_raw, 4))
            self.assertEqual(res["safety_stock_method"], "error_based")

        # Dead stock invariant
        res_dead = calculate_error_based_safety_stock(
            forecasted_horizon_demand=120.0,
            demand_pattern="dead_stock",
            dead_stock=True,
        )
        self.assertEqual(res_dead["service_level"], 0.0)
        self.assertEqual(res_dead["z_score"], 0.0)
        self.assertEqual(res_dead["safety_stock"], 0.0)
        self.assertTrue(res_dead["dead_stock_safeguard"])

    def test_safety_stock_cap_behavior(self):
        """High forecast error must trigger the 1.5 * horizon_demand cap."""
        res_capped = calculate_error_based_safety_stock(
            forecasted_horizon_demand=40.0,  # Cap = max(1.5 * 40, 10.0) = 60.0
            lead_time_months=3.0,
            review_period_months=1.0,
            demand_pattern="normal",  # Z = 0.8416
            sigma_error=50.0,  # sigma_horizon = 2 * 50 = 100 -> raw_ss = 84.16 > 60.0
        )
        self.assertTrue(res_capped["cap_applied"])
        self.assertEqual(res_capped["cap_value"], 60.0)
        self.assertEqual(res_capped["safety_stock"], 60.0)


if __name__ == "__main__":
    unittest.main()
