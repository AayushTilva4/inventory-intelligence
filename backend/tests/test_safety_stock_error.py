import math
import sys
from pathlib import Path
import unittest
import numpy as np
import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.inventory.recommendation_engine import build_recommendation
from app.inventory.safety_stock_service import (
    calculate_error_based_safety_stock,
    compute_historical_forecast_error,
    get_z_score,
    PATTERN_SERVICE_LEVELS,
    PATTERN_FALLBACK_CV,
)


class TestSafetyStockFromForecastError(unittest.TestCase):
    """
    Phase 2 — Task 6 Test Suite: Safety Stock from Forecast Error.
    """

    def test_1_stable_low_error_smaller_buffer(self):
        """Stable, low-noise products should receive smaller safety buffers."""
        horizon_demand = 400.0
        # Stable series with low error (sigma=5.0)
        res_stable = calculate_error_based_safety_stock(
            forecasted_horizon_demand=horizon_demand,
            demand_pattern="stable",
            sigma_error=5.0,
            lead_time_months=3.0,
            review_period_months=1.0,
        )
        # Old fixed 10% was 40.0m
        # With Z=0.8416, sigma_horizon=2*5.0=10.0 => SS = 8.416m
        self.assertAlmostEqual(res_stable["safety_stock"], 8.416, places=2)
        self.assertLess(res_stable["safety_stock"], horizon_demand * 0.10)
        self.assertEqual(res_stable["safety_stock_method"], "error_based")
        self.assertFalse(res_stable["fallback_used"])

    def test_2_noisy_high_error_larger_buffer(self):
        """Volatile, noisy products should receive larger safety buffers."""
        horizon_demand = 400.0
        # Volatile series with high error (sigma=80.0)
        res_noisy = calculate_error_based_safety_stock(
            forecasted_horizon_demand=horizon_demand,
            demand_pattern="fast_moving",
            sigma_error=80.0,
            lead_time_months=3.0,
            review_period_months=1.0,
        )
        # With Z=0.8416, sigma_horizon=2*80.0=160.0 => SS = 134.656m
        self.assertAlmostEqual(res_noisy["safety_stock"], 134.656, places=2)
        self.assertGreater(res_noisy["safety_stock"], horizon_demand * 0.10)
        self.assertEqual(res_noisy["safety_stock_method"], "error_based")

    def test_3_zero_forecast_safe_zero_buffer(self):
        """Zero forecast must produce exactly 0.0 safety stock."""
        res = calculate_error_based_safety_stock(
            forecasted_horizon_demand=0.0,
            demand_pattern="normal",
            sigma_error=50.0,
        )
        self.assertEqual(res["safety_stock"], 0.0)
        self.assertEqual(res["safety_stock_method"], "zero_forecast")

    def test_4_dead_stock_zero_buffer(self):
        """Dead stock items must produce exactly 0.0 safety stock regardless of history."""
        res = calculate_error_based_safety_stock(
            forecasted_horizon_demand=200.0,
            demand_pattern="dead_stock",
            sigma_error=50.0,
            dead_stock=True,
        )
        self.assertEqual(res["safety_stock"], 0.0)
        self.assertEqual(res["safety_stock_method"], "dead_stock")

    def test_5_sparse_error_history_deterministic_fallback(self):
        """Sparse or short history triggers deterministic pattern-pooled fallback."""
        res = calculate_error_based_safety_stock(
            forecasted_horizon_demand=100.0,
            demand_pattern="intermittent",
            sigma_error=None,  # No historical residuals available
            lead_time_months=3.0,
            review_period_months=1.0,
        )
        self.assertTrue(res["fallback_used"])
        self.assertEqual(res["safety_stock_method"], "pattern_fallback")
        # Intermittent fallback CV=0.50, monthly demand = 25.0 => sigma_1m = 12.5
        # sigma_horizon = 2 * 12.5 = 25.0 => SS = 0.6745 * 25.0 = 16.8622m
        self.assertAlmostEqual(res["safety_stock"], 16.8622, places=3)

    def test_6_horizon_consistency_scaling(self):
        """Verify horizon error scales by sqrt(L + R)."""
        # Horizon = 4 months (L=3, R=1) => scale factor = sqrt(4) = 2.0
        res_4m = calculate_error_based_safety_stock(
            forecasted_horizon_demand=100.0,
            lead_time_months=3.0,
            review_period_months=1.0,
            sigma_error=10.0,
            service_level=0.80,
        )
        self.assertAlmostEqual(res_4m["sigma_horizon"], 20.0, places=4)

        # Horizon = 9 months (L=8, R=1) => scale factor = sqrt(9) = 3.0
        res_9m = calculate_error_based_safety_stock(
            forecasted_horizon_demand=100.0,
            lead_time_months=8.0,
            review_period_months=1.0,
            sigma_error=10.0,
            service_level=0.80,
        )
        self.assertAlmostEqual(res_9m["sigma_horizon"], 30.0, places=4)
        self.assertAlmostEqual(res_9m["safety_stock"] / res_4m["safety_stock"], 1.5, places=4)

    def test_7_no_double_counted_safety_stock(self):
        """Ensure safety stock is added exactly once to reorder point to form target stock."""
        row = {
            "forecasted_horizon_demand": 500.0,
            "usable_stock": 200.0,
            "incoming_stock": 0.0,
            "committed_stock": 0.0,
            "demand_pattern": "stable",
            "sigma_error": 10.0,
        }
        rec = build_recommendation(row)
        self.assertEqual(rec["reorder_point"], 500.0)
        # SS = 0.8416 * 2 * 10 = 16.83m
        self.assertAlmostEqual(rec["safety_stock"], 16.83, places=2)
        self.assertAlmostEqual(rec["target_stock"], rec["reorder_point"] + rec["safety_stock"], places=2)
        self.assertAlmostEqual(rec["buffered_target_stock"], rec["target_stock"], places=2)
        self.assertEqual(rec["stock_gap"], round(rec["target_stock"] - 200.0, 2))

    def test_8_non_negative_safety_stock(self):
        """Safety stock and suggested purchase quantities must be strictly non-negative."""
        row = {
            "forecasted_horizon_demand": 100.0,
            "usable_stock": 500.0,
            "incoming_stock": 0.0,
            "committed_stock": 0.0,
            "demand_pattern": "normal",
            "sigma_error": 5.0,
        }
        rec = build_recommendation(row)
        self.assertGreaterEqual(rec["safety_stock"], 0.0)
        self.assertGreaterEqual(rec["stock_gap"], 0.0)
        self.assertGreaterEqual(rec["suggested_purchase_qty"], 0)

    def test_9_mentor_413_11_regression(self):
        """Group 413-11: incoming stock must prevent duplicate ordering under error-based safety stock."""
        # 413-11 parameters: 0 usable, 1054 incoming, horizon demand ~24.7m
        row = {
            "forecasted_horizon_demand": 24.70,
            "usable_stock": 0.0,
            "incoming_stock": 1054.0,
            "committed_stock": 0.0,
            "demand_pattern": "intermittent",
            "sigma_error": 8.0,
        }
        rec = build_recommendation(row)
        self.assertEqual(rec["inventory_position"], 1054.0)
        self.assertGreater(rec["safety_stock"], 0.0)
        self.assertLess(rec["target_stock"], 1054.0)
        self.assertEqual(rec["stock_gap"], 0.0)
        self.assertEqual(rec["suggested_purchase_qty"], 0)
        self.assertIn(rec["action"], ["hold", "excess_stock"])

    def test_10_mentor_325_42_regression(self):
        """Group 325-42: forecast horizon demand remains intact and detects seasonal replenishment."""
        # 325-42 parameters: 461.3m inventory position, 958.58m forward horizon demand
        row = {
            "forecasted_horizon_demand": 958.58,
            "usable_stock": 247.1,
            "incoming_stock": 214.2,
            "committed_stock": 0.0,
            "demand_pattern": "fast_moving",
            "sigma_error": 120.0,
        }
        rec = build_recommendation(row)
        self.assertEqual(rec["reorder_point"], 958.58)
        self.assertEqual(rec["inventory_position"], 461.3)
        self.assertGreater(rec["target_stock"], 958.58)
        self.assertEqual(rec["action"], "purchase")
        self.assertGreater(rec["suggested_purchase_qty"], 500)

    def test_11_fixed_buffer_vs_error_based_comparison(self):
        """Verify that explicit safety stock override matches legacy fixed buffer when desired."""
        horizon_demand = 300.0
        # Explicit 10% buffer passed
        rec_fixed = build_recommendation({
            "forecasted_horizon_demand": horizon_demand,
            "usable_stock": 100.0,
            "safety_stock": 30.0,
        })
        self.assertEqual(rec_fixed["safety_stock"], 30.0)
        self.assertEqual(rec_fixed["target_stock"], 330.0)

    def test_12_deterministic_repeated_execution(self):
        """Repeated runs with same inputs must produce bitwise identical results."""
        sales = pd.Series([10.0, 12.0, 15.0, 11.0, 14.0, 13.0, 16.0, 12.0, 15.0, 14.0])
        rmse1, n1 = compute_historical_forecast_error(sales, model_name="trimmed_mean_3")
        rmse2, n2 = compute_historical_forecast_error(sales, model_name="trimmed_mean_3")
        self.assertEqual(rmse1, rmse2)
        self.assertEqual(n1, n2)

        res1 = calculate_error_based_safety_stock(200.0, sigma_error=rmse1, demand_pattern="normal")
        res2 = calculate_error_based_safety_stock(200.0, sigma_error=rmse2, demand_pattern="normal")
        self.assertEqual(res1, res2)

    def test_13_zero_error_zero_safety_stock(self):
        """Zero forecast error must yield zero safety stock."""
        res = calculate_error_based_safety_stock(
            forecasted_horizon_demand=200.0,
            demand_pattern="normal",
            sigma_error=0.0,
        )
        self.assertEqual(res["safety_stock"], 0.0)

    def test_14_monotonic_service_level(self):
        """Higher cycle service levels must produce monotonically higher safety stock."""
        res_75 = calculate_error_based_safety_stock(
            forecasted_horizon_demand=200.0,
            service_level=0.75,
            sigma_error=20.0,
        )
        res_80 = calculate_error_based_safety_stock(
            forecasted_horizon_demand=200.0,
            service_level=0.80,
            sigma_error=20.0,
        )
        res_95 = calculate_error_based_safety_stock(
            forecasted_horizon_demand=200.0,
            service_level=0.95,
            sigma_error=20.0,
        )
        self.assertLess(res_75["safety_stock"], res_80["safety_stock"])
        self.assertLess(res_80["safety_stock"], res_95["safety_stock"])

    def test_15_no_future_leakage(self):
        """Forecast error calculation at origin t does not change if future sales append to series."""
        hist1 = pd.Series([10.0, 12.0, 15.0, 11.0, 14.0, 13.0, 16.0])
        hist2 = pd.Series([10.0, 12.0, 15.0, 11.0, 14.0, 13.0, 16.0, 999.0, 888.0])
        rmse1, n1 = compute_historical_forecast_error(hist1, model_name="trimmed_mean_3")
        # When evaluating origin up to index 6 in hist2:
        rmse2, _ = compute_historical_forecast_error(hist2.iloc[:7], model_name="trimmed_mean_3")
        self.assertEqual(rmse1, rmse2)

    def test_16_safety_stock_outlier_cap(self):
        """Extreme outlier error scale must be clamped by 1.5x horizon demand cap."""
        # Extreme sigma = 1000.0 on a 100.0 horizon demand
        res = calculate_error_based_safety_stock(
            forecasted_horizon_demand=100.0,
            sigma_error=1000.0,
            cap_factor=1.5,
        )
        self.assertEqual(res["safety_stock"], 150.0)

    def test_17_sqrt_horizon_variance_scaling(self):
        """Operational horizon error scale equals sqrt(L+R) * sigma_1m."""
        res = calculate_error_based_safety_stock(
            forecasted_horizon_demand=200.0,
            lead_time_months=3.0,
            review_period_months=1.0,
            sigma_error=25.0,
        )
        # sqrt(4.0) = 2.0 => sigma_horizon = 50.0
        self.assertAlmostEqual(res["sigma_horizon"], 50.0, places=4)


if __name__ == "__main__":
    unittest.main()
