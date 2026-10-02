import unittest
from unittest.mock import patch

import pandas as pd

import app.forecasting.benchmark_v2.runner as runner_module
from app.forecasting.benchmark_v2.models import BENCHMARK_MODELS
from app.forecasting.benchmark_v2.runner import BenchmarkRunner


class BenchmarkV2LeakageTest(unittest.TestCase):
    def test_future_actual_changes_do_not_change_origin_forecasts(self):
        product_id = 987654
        months = pd.date_range("2024-01-01", periods=24, freq="MS")
        monthly_df = pd.DataFrame(
            {
                "product_id": product_id,
                "product_name": "Leakage Test Product",
                "month": months,
                "total_quantity": [float(value % 7 + 1) for value in range(len(months))],
            }
        )
        origin = pd.Timestamp("2025-07-01")
        changed_future_df = monthly_df.copy()
        future_mask = changed_future_df["month"] > origin
        changed_future_df.loc[future_mask, "total_quantity"] = [10000.0 * value for value in range(1, 6)]

        original_forecast = runner_module.forecast_multistep

        def run_with_data(data):
            histories = []

            def capture_history(model_name, history, max_horizon=5):
                histories.append((model_name, tuple(history.astype(float).tolist())))
                return original_forecast(model_name, history, max_horizon=max_horizon)

            with patch.object(runner_module, "init_benchmark_tables"), patch.object(
                runner_module, "forecast_multistep", side_effect=capture_history
            ):
                runner = BenchmarkRunner(
                    horizons=(1, 2, 3, 4, 5),
                    num_origins=1,
                    models=BENCHMARK_MODELS,
                    min_train_months=3,
                    engine=object(),
                )
                with patch.object(
                    runner,
                    "load_data",
                    return_value={"monthly_df": data, "stock_map": {product_id: 0.0}},
                ), patch.object(runner, "print_summary"):
                    result = runner.run_benchmark(
                        mode="ids",
                        product_ids=[product_id],
                        save_db=False,
                    )

            forecasts = result["forecast_df"].sort_values(["model", "horizon"])
            return histories, forecasts[["model", "horizon", "forecast"]].reset_index(drop=True)

        original_histories, original_forecasts = run_with_data(monthly_df)
        changed_histories, changed_forecasts = run_with_data(changed_future_df)

        self.assertNotEqual(
            monthly_df.loc[future_mask, "total_quantity"].tolist(),
            changed_future_df.loc[future_mask, "total_quantity"].tolist(),
        )
        self.assertEqual(original_histories, changed_histories)
        pd.testing.assert_frame_equal(original_forecasts, changed_forecasts)
        self.assertEqual(original_forecasts["horizon"].tolist(), [1, 2, 3, 4, 5] * len(BENCHMARK_MODELS))


if __name__ == "__main__":
    unittest.main()