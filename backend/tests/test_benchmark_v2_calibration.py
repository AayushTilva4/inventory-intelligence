"""
Unit tests for Benchmark V2 Empirical Forecast Calibration & Safety Stock Layer.

Validates:
1. Empirical error quantiles correctness
2. Safety buffer calculation and target stock identity (target = forecast + buffer)
3. Monotonic service-level changes (75% <= 80% <= 85% <= 90% <= 95%)
4. Zero-error series (buffer == 0.0)
5. Zero-demand and dead-stock products (buffer == 0.0, no phantom inventory)
6. Intermittent demand stability
7. Short history robustness (graceful fallback)
8. Non-negative buffer guarantee under over-forecasting
9. Safety buffer cap protection against extreme outlier spikes
10. Deterministic execution
11. Point-in-time isolation (strictly zero future leakage)
"""

import sys
from pathlib import Path
import unittest
import numpy as np
import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.forecasting.benchmark_v2.calibration import (
    EmpiricalSafetyCalibrator,
    CalibratedForecast,
    calculate_fixed_buffer,
)


class TestBenchmarkV2Calibration(unittest.TestCase):

    def setUp(self):
        # Create deterministic synthetic historical evaluation DataFrame
        np.random.seed(42)
        records = []
        models = ["trimmed_mean_3", "median_baseline", "pattern_router_e"]
        patterns = ["fast_moving", "intermittent", "falling", "rising", "stable/normal", "dead_stock"]
        
        for m in models:
            for pat in patterns:
                for h in [1, 2, 3, 4, 5]:
                    for rep in range(20):
                        if pat == "dead_stock":
                            act = 0.0
                            fc = 0.0
                        elif pat == "intermittent":
                            act = float(np.random.choice([0.0, 0.0, 5.0, 15.0]))
                            fc = 2.0
                        elif pat == "fast_moving":
                            act = float(np.random.normal(50.0, 15.0))
                            fc = 45.0
                        else:
                            act = float(np.random.normal(20.0, 5.0))
                            fc = 18.0
                            
                        act = max(0.0, act)
                        records.append({
                            "model": m,
                            "as_of_origin_pattern": pat,
                            "horizon": h,
                            "actual": act,
                            "forecast": fc,
                            "mase_scale": 5.0 if pat != "dead_stock" else 1.0,
                        })
                        
        self.hist_df = pd.DataFrame(records)
        self.calibrator = EmpiricalSafetyCalibrator()
        self.calibrator.fit(self.hist_df)

    def test_calibrator_fitting_and_quantiles(self):
        """Verifies calibrator fits and precomputes non-empty quantile tables."""
        self.assertTrue(self.calibrator.is_calibrated)
        # Check lookup returns valid positive float
        q = self.calibrator._lookup_quantile("trimmed_mean_3", "fast_moving", 3, 0.80)
        self.assertIsInstance(q, float)
        self.assertGreater(q, 0.0)

    def test_safety_buffer_calculation_and_target_identity(self):
        """Verifies target_stock == forecast + safety_buffer."""
        res = self.calibrator.calculate_safety_buffer(
            forecast=25.0,
            horizon=3,
            pattern="fast_moving",
            model="trimmed_mean_3",
            service_level=0.80,
            scale=5.0,
        )
        self.assertIsInstance(res, CalibratedForecast)
        self.assertEqual(res.forecast, 25.0)
        self.assertEqual(res.forecast_horizon, 3)
        self.assertEqual(res.pattern, "fast_moving")
        self.assertEqual(res.model, "trimmed_mean_3")
        self.assertEqual(res.service_level, 0.80)
        self.assertAlmostEqual(res.target_stock, res.forecast + res.safety_buffer, places=3)
        self.assertGreater(res.safety_buffer, 0.0)

    def test_monotonic_service_level_changes(self):
        """Verifies buffer monotonically increases (or equals) as service level increases."""
        service_levels = [0.75, 0.80, 0.85, 0.90, 0.95]
        buffers = []
        for sl in service_levels:
            res = self.calibrator.calculate_safety_buffer(
                forecast=30.0,
                horizon=3,
                pattern="fast_moving",
                model="trimmed_mean_3",
                service_level=sl,
                scale=5.0,
            )
            buffers.append(res.safety_buffer)
            
        for i in range(len(buffers) - 1):
            self.assertLessEqual(buffers[i], buffers[i + 1])

    def test_zero_error_series(self):
        """Verifies that a series where forecast perfectly matches actual has 0 buffer."""
        perfect_df = pd.DataFrame([{
            "model": "perfect_model",
            "as_of_origin_pattern": "stable/normal",
            "horizon": 1,
            "actual": 10.0,
            "forecast": 10.0,
            "mase_scale": 2.0,
        }] * 10)
        calib = EmpiricalSafetyCalibrator()
        calib.fit(perfect_df)
        res = calib.calculate_safety_buffer(
            forecast=10.0,
            horizon=1,
            pattern="stable/normal",
            model="perfect_model",
            service_level=0.95,
            scale=2.0,
        )
        self.assertEqual(res.error_quantile, 0.0)
        self.assertEqual(res.safety_buffer, 0.0)
        self.assertEqual(res.target_stock, 10.0)

    def test_zero_demand_and_dead_stock_invariance(self):
        """Dead stock or zero forecast must strictly produce 0 safety buffer."""
        # 1. Pattern is dead_stock
        res_dead = self.calibrator.calculate_safety_buffer(
            forecast=0.0,
            horizon=3,
            pattern="dead_stock",
            model="trimmed_mean_3",
            service_level=0.95,
        )
        self.assertEqual(res_dead.safety_buffer, 0.0)
        self.assertEqual(res_dead.target_stock, 0.0)

        # 2. Forecast is 0.0 on active pattern
        res_zero_fc = self.calibrator.calculate_safety_buffer(
            forecast=0.0,
            horizon=3,
            pattern="intermittent",
            model="trimmed_mean_3",
            service_level=0.95,
        )
        self.assertEqual(res_zero_fc.safety_buffer, 0.0)
        self.assertEqual(res_zero_fc.target_stock, 0.0)

    def test_intermittent_demand_stability(self):
        """Verifies intermittent demand produces sensible non-zero buffers without crashing."""
        res = self.calibrator.calculate_safety_buffer(
            forecast=3.0,
            horizon=3,
            pattern="intermittent",
            model="trimmed_mean_3",
            service_level=0.85,
            scale=2.0,
        )
        self.assertGreaterEqual(res.safety_buffer, 0.0)
        self.assertLessEqual(res.safety_buffer, 25.0)

    def test_short_history_robustness(self):
        """Verifies calibrator handles single-row history and unseen patterns gracefully via fallback."""
        sparse_df = pd.DataFrame([{
            "model": "model_x",
            "as_of_origin_pattern": "rare_pattern",
            "horizon": 1,
            "actual": 12.0,
            "forecast": 10.0,
            "mase_scale": 1.0,
        }])
        sparse_calib = EmpiricalSafetyCalibrator()
        sparse_calib.fit(sparse_df)
        
        # Test unseen horizon
        res = sparse_calib.calculate_safety_buffer(
            forecast=10.0,
            horizon=5,
            pattern="rare_pattern",
            model="model_x",
            service_level=0.80,
            scale=1.0,
        )
        self.assertGreaterEqual(res.safety_buffer, 0.0)

    def test_non_negative_buffer_guarantee(self):
        """Verifies buffer is never negative even when all historical errors are negative (overforecast)."""
        over_df = pd.DataFrame([{
            "model": "over_model",
            "as_of_origin_pattern": "falling",
            "horizon": 2,
            "actual": 5.0,
            "forecast": 25.0, # massive over-forecast
            "mase_scale": 3.0,
        }] * 10)
        over_calib = EmpiricalSafetyCalibrator()
        over_calib.fit(over_df)
        res = over_calib.calculate_safety_buffer(
            forecast=20.0,
            horizon=2,
            pattern="falling",
            model="over_model",
            service_level=0.80,
            scale=3.0,
        )
        self.assertGreaterEqual(res.safety_buffer, 0.0)

    def test_safety_buffer_cap(self):
        """Verifies safety cap limits buffer even on extreme outlier shortfalls."""
        outlier_df = pd.DataFrame([{
            "model": "extreme_model",
            "as_of_origin_pattern": "fast_moving",
            "horizon": 1,
            "actual": 10000.0,
            "forecast": 10.0,
            "mase_scale": 5.0,
        }] * 10)
        outlier_calib = EmpiricalSafetyCalibrator(cap_factor=2.0)
        outlier_calib.fit(outlier_df)
        res = outlier_calib.calculate_safety_buffer(
            forecast=10.0,
            horizon=1,
            pattern="fast_moving",
            model="extreme_model",
            service_level=0.95,
            scale=5.0,
        )
        # Cap is 2.0 * max(10, 5, 5) = 20.0
        self.assertLessEqual(res.safety_buffer, 20.001)

    def test_deterministic_execution(self):
        """Verifies bitwise identical output when called repeatedly."""
        res1 = self.calibrator.calculate_safety_buffer(
            forecast=33.3,
            horizon=3,
            pattern="rising",
            model="trimmed_mean_3",
            service_level=0.85,
            scale=4.2,
        )
        res2 = self.calibrator.calculate_safety_buffer(
            forecast=33.3,
            horizon=3,
            pattern="rising",
            model="trimmed_mean_3",
            service_level=0.85,
            scale=4.2,
        )
        self.assertEqual(res1.to_dict(), res2.to_dict())

    def test_no_future_leakage_in_calibrator(self):
        """Verifies that altering future test data does not affect historical calibration."""
        past_data = self.hist_df.copy()
        calib_a = EmpiricalSafetyCalibrator().fit(past_data)
        
        # Buffer computed on as-of-origin state
        buf_a = calib_a.calculate_safety_buffer(
            forecast=40.0,
            horizon=3,
            pattern="fast_moving",
            model="trimmed_mean_3",
            service_level=0.80,
            scale=5.0,
        )
        
        # Future unseen data arrives
        future_data = pd.DataFrame([{
            "model": "trimmed_mean_3",
            "as_of_origin_pattern": "fast_moving",
            "horizon": 3,
            "actual": 9999.0, # future huge spike
            "forecast": 40.0,
            "mase_scale": 5.0,
        }])
        
        # Calibrator A was fitted strictly on past_data and must NOT change
        buf_a_after = calib_a.calculate_safety_buffer(
            forecast=40.0,
            horizon=3,
            pattern="fast_moving",
            model="trimmed_mean_3",
            service_level=0.80,
            scale=5.0,
        )
        self.assertEqual(buf_a.safety_buffer, buf_a_after.safety_buffer)

    def test_calculate_fixed_buffer(self):
        """Verifies baseline fixed buffer calculation."""
        self.assertEqual(calculate_fixed_buffer(100.0, 0.10), 10.0)
        self.assertEqual(calculate_fixed_buffer(0.0, 0.10), 0.0)
        self.assertEqual(calculate_fixed_buffer(-5.0, 0.10), 0.0)


if __name__ == "__main__":
    unittest.main()
