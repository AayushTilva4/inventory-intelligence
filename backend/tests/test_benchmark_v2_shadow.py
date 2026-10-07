"""
Unit tests for Benchmark V2 Shadow Forecast Pipeline.

Validates:
1. Production isolation: Shadow pipeline does not modify production inputs or forecasts.
2. Deterministic output: Repeated execution yields identical forecasts and targets.
3. Dead-stock safety: Dead stock strictly receives 0 buffer and 0 target stock.
4. Non-negative targets: Target stock is strictly non-negative.
5. Service-level monotonicity: Higher service levels yield equal or higher buffers.
6. Extreme buffer cap: Buffers are capped to avoid explosive inventory.
7. Missing production comparison handling: Handles None / missing production targets gracefully.
8. Diagnostic flags accuracy: Correctly flags large changes, large buffers, dead stock, and risk flags.
"""

import sys
from pathlib import Path
import unittest
import numpy as np
import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.forecasting.benchmark_v2.shadow import ShadowPipeline, ShadowForecastComparison
from app.forecasting.benchmark_v2.calibration import EmpiricalSafetyCalibrator


class TestBenchmarkV2ShadowPipeline(unittest.TestCase):

    def setUp(self):
        # Create deterministic synthetic calibrator
        np.random.seed(42)
        records = []
        for m in ["trimmed_mean_3"]:
            for pat in ["fast_moving", "intermittent", "falling", "dead_stock"]:
                for h in [1, 2, 3]:
                    for _ in range(15):
                        act = float(np.random.normal(30.0, 10.0)) if pat != "dead_stock" else 0.0
                        fc = 25.0 if pat != "dead_stock" else 0.0
                        records.append({
                            "model": m,
                            "as_of_origin_pattern": pat,
                            "horizon": h,
                            "actual": max(0.0, act),
                            "forecast": fc,
                            "mase_scale": 4.0 if pat != "dead_stock" else 1.0,
                        })
        calib_df = pd.DataFrame(records)
        self.calibrator = EmpiricalSafetyCalibrator()
        self.calibrator.fit(calib_df)

        self.shadow = ShadowPipeline(
            calibrator=self.calibrator,
            default_service_level=0.80,
            horizon=3,
            large_change_threshold_pct=0.50,
            understock_risk_delta=10.0,
            overstock_risk_delta=20.0,
        )

    def test_production_output_not_modified(self):
        """Verifies that shadow evaluation does not mutate passed production values or series."""
        orig_sales = [10.0, 15.0, 20.0, 25.0, 30.0]
        sales_copy = list(orig_sales)
        prod_fc = 25.0
        prod_tgt = 35.0

        res = self.shadow.evaluate_product(
            product_id=123,
            product_name="Test Product",
            sales_series=sales_copy,
            stock_on_hand=5.0,
            production_forecast=prod_fc,
            production_target=prod_tgt,
        )

        # Sales list must be unchanged
        self.assertEqual(sales_copy, orig_sales)
        # Production values preserved intact in output
        self.assertEqual(res.production_forecast, prod_fc)
        self.assertEqual(res.production_target_if_available, prod_tgt)

    def test_deterministic_output(self):
        """Verifies bitwise identical output on repeated runs."""
        sales = [5.0, 12.0, 18.0, 22.0, 30.0, 35.0]
        res1 = self.shadow.evaluate_product(
            product_id=456,
            product_name="Deterministic Fabric",
            sales_series=sales,
            production_forecast=20.0,
            production_target=25.0,
        )
        res2 = self.shadow.evaluate_product(
            product_id=456,
            product_name="Deterministic Fabric",
            sales_series=sales,
            production_forecast=20.0,
            production_target=25.0,
        )
        self.assertEqual(res1.to_dict(), res2.to_dict())

    def test_dead_stock_buffer_remains_zero(self):
        """Verifies dead stock items receive strictly 0 forecast, 0 buffer, and 0 target stock."""
        # Flat zeros with positive stock on hand -> dead_stock
        zero_sales = [0.0] * 12
        res = self.shadow.evaluate_product(
            product_id=789,
            product_name="Dead Product",
            sales_series=zero_sales,
            stock_on_hand=50.0,
            production_forecast=5.0,
            production_target=10.0,
        )
        self.assertEqual(res.pattern, "dead_stock")
        self.assertEqual(res.forecast, 0.0)
        self.assertEqual(res.safety_buffer, 0.0)
        self.assertEqual(res.target_stock, 0.0)
        self.assertTrue(res.dead_stock)
        self.assertTrue(res.zero_forecast)

    def test_non_negative_target(self):
        """Target stock must always be >= 0."""
        sales = [0.0, 1.0, 0.0, 2.0, 0.0]
        res = self.shadow.evaluate_product(
            product_id=101,
            product_name="Sparse Fabric",
            sales_series=sales,
        )
        self.assertGreaterEqual(res.target_stock, 0.0)
        self.assertGreaterEqual(res.safety_buffer, 0.0)

    def test_service_level_monotonicity(self):
        """Buffers must not decrease when requesting a higher service level."""
        sales = [20.0, 25.0, 30.0, 35.0, 40.0]
        res_75 = self.shadow.evaluate_product(1, "P1", sales, service_level=0.75)
        res_80 = self.shadow.evaluate_product(1, "P1", sales, service_level=0.80)
        res_85 = self.shadow.evaluate_product(1, "P1", sales, service_level=0.85)
        res_90 = self.shadow.evaluate_product(1, "P1", sales, service_level=0.90)

        self.assertLessEqual(res_75.safety_buffer, res_80.safety_buffer)
        self.assertLessEqual(res_80.safety_buffer, res_85.safety_buffer)
        self.assertLessEqual(res_85.safety_buffer, res_90.safety_buffer)

    def test_extreme_buffer_cap(self):
        """Verifies buffer cap prevents explosive buffer on extreme outlier spikes."""
        sales = [10.0, 10.0, 10.0, 10.0]
        res = self.shadow.evaluate_product(1, "P1", sales, service_level=0.95)
        # Buffer should be capped reasonably
        self.assertLessEqual(res.safety_buffer, 3.0 * max(res.forecast, 10.0))

    def test_correct_handling_of_missing_production_comparison(self):
        """Verifies shadow pipeline executes cleanly when production forecasts are None."""
        sales = [15.0, 20.0, 25.0]
        res = self.shadow.evaluate_product(
            product_id=202,
            product_name="New Launch Fabric",
            sales_series=sales,
            production_forecast=None,
            production_target=None,
        )
        self.assertIsNone(res.production_forecast)
        self.assertIsNone(res.forecast_delta)
        self.assertIsNone(res.production_target_if_available)
        self.assertIsNone(res.target_delta)
        self.assertFalse(res.potential_understock_risk)
        self.assertFalse(res.potential_overstock_risk)
        self.assertGreater(res.target_stock, 0.0)

    def test_diagnostic_flags_accuracy(self):
        """Verifies that large changes and under/overstock flags trigger appropriately."""
        sales = [10.0, 10.0, 10.0, 10.0]
        # Shadow forecast ~ 10.0, production forecast = 2.0 (massive difference > 50%)
        # Shadow target ~ 15.0, production target = 50.0 (understock delta < -10)
        res = self.shadow.evaluate_product(
            product_id=303,
            product_name="Flag Test Fabric",
            sales_series=sales,
            production_forecast=2.0,
            production_target=50.0,
        )
        self.assertTrue(res.large_forecast_change)
        self.assertTrue(res.potential_understock_risk)
        self.assertFalse(res.potential_overstock_risk)

    def test_active_fast_moving_product_shadow_evaluation(self):
        """Verifies active high-velocity products produce positive forecast, positive buffer, and target > forecast."""
        active_sales = [45.0, 50.0, 55.0, 60.0, 58.0, 62.0]
        res = self.shadow.evaluate_product(
            product_id=501,
            product_name="Active Fast Silk",
            sales_series=active_sales,
            stock_on_hand=30.0,
            production_forecast=40.0,
            production_target=80.0,
            service_level=0.80,
        )
        self.assertIn(res.pattern, ["fast_moving", "rising", "stable/normal"])
        self.assertGreater(res.forecast, 0.0)
        self.assertGreater(res.safety_buffer, 0.0)
        self.assertGreater(res.target_stock, res.forecast)
        self.assertAlmostEqual(res.target_stock, res.forecast + res.safety_buffer, places=3)
        self.assertFalse(res.dead_stock)

    def test_active_intermittent_product_shadow_evaluation(self):
        """Verifies active intermittent products with recent demand produce non-negative forecasts and valid targets."""
        intermittent_sales = [0.0, 15.0, 0.0, 0.0, 20.0, 0.0, 10.0]
        res = self.shadow.evaluate_product(
            product_id=502,
            product_name="Active Intermittent Linen",
            sales_series=intermittent_sales,
            stock_on_hand=5.0,
            production_forecast=5.0,
            production_target=15.0,
            service_level=0.75,
        )
        self.assertEqual(res.pattern, "intermittent")
        self.assertGreaterEqual(res.forecast, 0.0)
        self.assertGreaterEqual(res.safety_buffer, 0.0)
        self.assertGreaterEqual(res.target_stock, 0.0)
        self.assertFalse(res.dead_stock)

    def test_active_product_zero_stock_on_hand(self):
        """Verifies active products with 0 stock on hand evaluate safely without negative targets or errors."""
        active_sales = [20.0, 25.0, 22.0, 28.0]
        res = self.shadow.evaluate_product(
            product_id=503,
            product_name="Stockout Active Chiffon",
            sales_series=active_sales,
            stock_on_hand=0.0,
            production_forecast=22.0,
            production_target=45.0,
            service_level=0.80,
        )
        self.assertGreater(res.forecast, 0.0)
        self.assertGreaterEqual(res.target_stock, res.forecast)
        self.assertFalse(res.dead_stock)

    def test_material_delta_detection_on_active_products(self):
        """Verifies material target delta calculations distinguish understock vs overstock flags on active products."""
        active_sales = [30.0, 32.0, 35.0, 34.0]
        # Legacy target = 100.0, shadow target ~ 45.0 -> delta is -55 (potential understock vs legacy, legacy overstocked)
        res_over = self.shadow.evaluate_product(
            product_id=504,
            product_name="Legacy Overstock Active Cotton",
            sales_series=active_sales,
            production_forecast=30.0,
            production_target=100.0,
        )
        self.assertTrue(res_over.potential_understock_risk) # target_delta = shadow - legacy < -10

        # Legacy target = 10.0, shadow target ~ 45.0 -> delta is +35 (potential overstock vs legacy)
        res_under = self.shadow.evaluate_product(
            product_id=505,
            product_name="Legacy Understock Active Cotton",
            sales_series=active_sales,
            production_forecast=10.0,
            production_target=10.0,
        )
        self.assertTrue(res_under.potential_overstock_risk) # target_delta = shadow - legacy > 20


if __name__ == "__main__":
    unittest.main()

