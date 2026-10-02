"""
Unit tests for Forecast Benchmark V2.1 correctness fixes:
- Task 1: MASE (valid scale, zero-demand training, seasonal vs lag-1 fallback, scaled errors aggregation)
- Task 2: As-of-origin classification (leakage-free historical classification)
- Task 3: WAPE edge cases (undefined on zero actuals, standard on positive demand)
- Task 5: ETS parity with V1 and fit failure surfacing
- Task 7: Reproducibility (deterministic forecasts and metrics)
"""

import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd

from app.forecasting.benchmark_v2.metrics import calculate_metrics, calculate_mase_scale
from app.forecasting.benchmark_v2.classification import classify_demand_pattern
from app.forecasting.benchmark_v2.models import (
    forecast_exponential_smoothing,
    forecast_multistep,
    BENCHMARK_MODELS,
)
from app.forecasting.benchmark_v2.runner import BenchmarkRunner
from src.forecasting import exponential_smoothing_forecast


class TestMASE(unittest.TestCase):
    def test_mase_seasonal_lag_available(self):
        # 16 months of history with seasonal variation
        # season length = 12
        history = [
            10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 28.0, 22.0, 18.0, 14.0, 11.0, 9.0,
            12.0, 14.0, 17.0, 22.0
        ]
        scale = calculate_mase_scale(history, season_length=12)
        self.assertIsNotNone(scale)
        # Seasonal diffs: |12-10|=2, |14-12|=2, |17-15|=2, |22-20|=2 -> mean = 2.0
        self.assertAlmostEqual(scale, 2.0, places=4)

        # Evaluate forecast
        actual = [26.0]
        predicted = [30.0]  # abs_error = 4.0
        metrics = calculate_metrics(actual, predicted, train_history=history, season_length=12)
        # MASE = 4.0 / 2.0 = 2.0
        self.assertEqual(metrics["mase"], 2.0)

    def test_mase_seasonal_lag_unavailable_falls_back_to_lag1(self):
        # 6 months of history (len <= 12)
        history = [10.0, 14.0, 12.0, 18.0, 15.0, 20.0]
        # Lag 1 diffs: |14-10|=4, |12-14|=2, |18-12|=6, |15-18|=3, |20-15|=5 -> mean = 20/5 = 4.0
        scale = calculate_mase_scale(history, season_length=12)
        self.assertIsNotNone(scale)
        self.assertAlmostEqual(scale, 4.0, places=4)

        actual = [24.0]
        predicted = [20.0]  # abs_error = 4.0
        metrics = calculate_metrics(actual, predicted, train_history=history, season_length=12)
        # MASE = 4.0 / 4.0 = 1.0
        self.assertEqual(metrics["mase"], 1.0)

    def test_mase_zero_demand_training_history_is_undefined(self):
        # Series with all 0s has 0 difference, hence undefined scale
        history = [0.0] * 18
        scale = calculate_mase_scale(history, season_length=12)
        self.assertIsNone(scale)

        actual = [5.0]
        predicted = [0.0]
        metrics = calculate_metrics(actual, predicted, train_history=history)
        self.assertIsNone(metrics["mase"])
        self.assertEqual(metrics["mae"], 5.0)

    def test_mase_constant_nonzero_training_history_is_undefined(self):
        # Series with constant values has 0 difference, hence undefined scale
        history = [42.0] * 18
        scale = calculate_mase_scale(history, season_length=12)
        self.assertIsNone(scale)

        actual = [42.0]
        predicted = [50.0]
        metrics = calculate_metrics(actual, predicted, train_history=history)
        self.assertIsNone(metrics["mase"])

    def test_mase_scaled_errors_aggregation(self):
        # Multiple evaluation points aggregated
        scaled_errors = [0.5, 1.5, None, np.nan, 1.0]
        metrics = calculate_metrics([10, 20, 30, 40, 50], [12, 18, 30, 45, 52], scaled_errors=scaled_errors)
        # Expected mean of valid [0.5, 1.5, 1.0] = 3.0 / 3 = 1.0
        self.assertEqual(metrics["mase"], 1.0)


class TestHistoricalClassification(unittest.TestCase):
    def test_future_sales_do_not_alter_origin_classification(self):
        # Product active with high consistent sales until 2025-06
        months = pd.date_range("2024-01-01", "2026-06-01", freq="MS")
        origin_dt = pd.Timestamp("2025-06-01")

        # History before origin is steady high volume (fast_moving)
        sales_stable = [50.0 if m <= origin_dt else 50.0 for m in months]
        # Alternative future where product completely dies after origin
        sales_collapse = [50.0 if m <= origin_dt else 0.0 for m in months]

        df_stable = pd.DataFrame({"month": months, "total_quantity": sales_stable})
        df_collapse = pd.DataFrame({"month": months, "total_quantity": sales_collapse})

        # Classify as of origin (strictly using train slice before origin and stock=0)
        train_stable = df_stable[df_stable["month"] <= origin_dt]["total_quantity"]
        train_collapse = df_collapse[df_collapse["month"] <= origin_dt]["total_quantity"]

        origin_cls_stable = classify_demand_pattern(train_stable, stock_on_hand=0.0)
        origin_cls_collapse = classify_demand_pattern(train_collapse, stock_on_hand=0.0)

        # Both must be IDENTICAL as of origin
        self.assertEqual(origin_cls_stable["pattern"], "fast_moving")
        self.assertEqual(origin_cls_collapse["pattern"], "fast_moving")
        self.assertEqual(origin_cls_stable["pattern"], origin_cls_collapse["pattern"])

        # Meanwhile, end-of-period full classifications differ
        current_cls_stable = classify_demand_pattern(df_stable["total_quantity"], stock_on_hand=100.0)
        current_cls_collapse = classify_demand_pattern(df_collapse["total_quantity"], stock_on_hand=100.0)
        self.assertEqual(current_cls_stable["pattern"], "fast_moving")
        self.assertEqual(current_cls_collapse["pattern"], "dead_stock")


class TestWAPE(unittest.TestCase):
    def test_wape_all_zero_actual_demand_is_undefined(self):
        actual = [0.0, 0.0, 0.0]
        predicted = [10.0, 50.0, 100.0]

        metrics = calculate_metrics(actual, predicted)
        # WAPE must be None / NaN, NOT 1.0
        self.assertIsNone(metrics["wape"])
        # MAE and RMSE remain fully valid
        self.assertAlmostEqual(metrics["mae"], 160.0 / 3.0, places=4)
        self.assertGreater(metrics["rmse"], 0)
        self.assertAlmostEqual(metrics["bias"], 160.0 / 3.0, places=4)

    def test_wape_positive_demand_case(self):
        actual = [100.0, 200.0]
        predicted = [110.0, 180.0]
        # sum |diff| = 10 + 20 = 30. sum actual = 300. WAPE = 30/300 = 0.10
        metrics = calculate_metrics(actual, predicted)
        self.assertEqual(metrics["wape"], 0.1)


class TestETS(unittest.TestCase):
    def test_v2_matches_v1_on_normal_data(self):
        # 24 periods of realistic monthly demand
        np.random.seed(42)
        base = np.linspace(20, 40, 24) + np.sin(np.linspace(0, 4 * np.pi, 24)) * 5
        series = pd.Series(base)

        v1_fc = exponential_smoothing_forecast(series, seasonal_periods=12)
        v2_multistep = forecast_exponential_smoothing(series, max_horizon=1, seasonal_periods=12)

        self.assertAlmostEqual(v1_fc, v2_multistep[0], places=4)

    def test_v2_raises_on_fit_failure_without_silent_mean_substitution(self):
        series = pd.Series([10.0, 12.0, 14.0, 16.0, 18.0])

        with patch("app.forecasting.benchmark_v2.models.ExponentialSmoothing.fit", side_effect=RuntimeError("Optimization failed")):
            # Must raise RuntimeError, NOT silently return series.mean()
            with self.assertRaises(RuntimeError):
                forecast_exponential_smoothing(series, max_horizon=3)


class TestReproducibility(unittest.TestCase):
    def test_identical_inputs_produce_identical_forecasts_and_metrics(self):
        product_id = 999001
        months = pd.date_range("2024-01-01", periods=24, freq="MS")
        monthly_df = pd.DataFrame({
            "product_id": product_id,
            "product_name": "Reproducibility Test Fabric",
            "month": months,
            "total_quantity": [float((i % 6) * 10 + 15) for i in range(len(months))],
        })

        def run_isolated():
            with patch("app.forecasting.benchmark_v2.runner.init_benchmark_tables"):
                runner = BenchmarkRunner(
                    horizons=(1, 2, 3),
                    num_origins=2,
                    models=["previous_month", "moving_average_3"],
                    min_train_months=3,
                    engine=object(),
                )
                with patch.object(
                    runner,
                    "load_data",
                    return_value={"monthly_df": monthly_df, "stock_map": {product_id: 50.0}},
                ), patch.object(runner, "print_summary"):
                    return runner.run_benchmark(
                        mode="ids",
                        product_ids=[product_id],
                        save_db=False,
                    )

        res1 = run_isolated()
        res2 = run_isolated()

        pd.testing.assert_frame_equal(
            res1["forecast_df"].drop(columns=["run_id"]),
            res2["forecast_df"].drop(columns=["run_id"]),
        )
        pd.testing.assert_frame_equal(
            res1["metrics_df"].drop(columns=["run_id"]),
            res2["metrics_df"].drop(columns=["run_id"]),
        )


if __name__ == "__main__":
    unittest.main()
