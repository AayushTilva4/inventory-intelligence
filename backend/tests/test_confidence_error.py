import unittest
import math
import sys
from pathlib import Path
import numpy as np
import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.forecasting.confidence import (
    calculate_forecast_error_metrics,
    classify_forecast_confidence,
    HIGH_CONFIDENCE_MAX_WAPE,
    NORMAL_CONFIDENCE_MAX_WAPE,
    HIGH_CONFIDENCE_MAX_MASE,
    NORMAL_CONFIDENCE_MAX_MASE,
    MIN_OBSERVATIONS_FOR_CONFIDENCE,
)
from app.inventory.recommendation_engine import build_recommendation


class TestConfidenceError(unittest.TestCase):
    def test_wape_calculation_exact(self):
        actual = [100.0, 200.0, 300.0]
        forecast = [110.0, 190.0, 330.0]
        # errors: [10, 10, 30] -> sum = 50. actual sum = 600.
        # WAPE = 50 / 600 = 1/12 ≈ 0.08333
        metrics = calculate_forecast_error_metrics(actual, forecast)
        self.assertEqual(metrics["observation_count"], 3)
        self.assertAlmostEqual(metrics["wape"], 50.0 / 600.0, places=5)
        self.assertAlmostEqual(metrics["mae"], 50.0 / 3.0, places=5)
        self.assertAlmostEqual(metrics["rmse"], math.sqrt((100 + 100 + 900) / 3.0), places=5)
        self.assertAlmostEqual(metrics["bias"], (10 - 10 + 30) / 3.0, places=5)

    def test_mase_calculation_exact(self):
        train = [100.0, 110.0, 120.0, 130.0]
        # naive diffs: [10, 10, 10] -> mean scale = 10.0
        actual = [140.0, 150.0]
        forecast = [145.0, 145.0]
        # abs errors: [5, 5] -> MAE = 5.0
        # MASE = 5.0 / 10.0 = 0.5
        metrics = calculate_forecast_error_metrics(actual, forecast, train=train)
        self.assertIsNotNone(metrics["mase"])
        self.assertAlmostEqual(metrics["mase"], 0.5, places=5)

    def test_zero_denominator_handling(self):
        # 1. Zero actual demand and zero forecast
        metrics = calculate_forecast_error_metrics([0.0, 0.0], [0.0, 0.0])
        self.assertEqual(metrics["wape"], 0.0)
        conf, reason = classify_forecast_confidence(
            metrics["wape"],
            actual_sum=metrics["actual_sum"],
            forecast_sum=metrics["forecast_sum"],
        )
        self.assertEqual(conf, "trivial_zero")

        # 2. Zero actual demand but positive forecast
        metrics_pos = calculate_forecast_error_metrics([0.0, 0.0], [10.0, 20.0])
        self.assertTrue(math.isinf(metrics_pos["wape"]))
        conf_pos, reason_pos = classify_forecast_confidence(
            metrics_pos["wape"],
            actual_sum=metrics_pos["actual_sum"],
            forecast_sum=metrics_pos["forecast_sum"],
        )
        self.assertEqual(conf_pos, "trivial_zero")

        # 3. Constant train series (zero naive scale)
        train_const = [50.0, 50.0, 50.0]
        metrics_const = calculate_forecast_error_metrics([50.0, 60.0], [55.0, 65.0], train=train_const)
        self.assertIsNone(metrics_const["mase"])  # No division by zero

    def test_sparse_observations(self):
        # Under 5 observations -> must be classified as 'low'
        conf, reason = classify_forecast_confidence(
            wape=0.10,
            mase=0.5,
            observation_count=4,
        )
        self.assertEqual(conf, "low")
        self.assertEqual(reason, "sparse_history")

        # Marked as is_sparse -> must be classified as 'low'
        conf_sparse, reason_sparse = classify_forecast_confidence(
            wape=0.10,
            mase=0.5,
            observation_count=10,
            is_sparse=True,
        )
        self.assertEqual(conf_sparse, "low")
        self.assertEqual(reason_sparse, "sparse_history")

    def test_monotonic_confidence_ordering(self):
        # Test series of error levels:
        # High: WAPE 0.20, MASE 0.8
        conf_high, _ = classify_forecast_confidence(wape=0.20, mase=0.8, observation_count=6)
        self.assertEqual(conf_high, "high")

        # Normal: WAPE 0.42, MASE 0.9
        conf_norm, _ = classify_forecast_confidence(wape=0.42, mase=0.9, observation_count=6)
        self.assertEqual(conf_norm, "normal")

        # Low (WAPE > 50%): WAPE 0.55, MASE 0.8
        conf_low, _ = classify_forecast_confidence(wape=0.55, mase=0.8, observation_count=6)
        self.assertEqual(conf_low, "low")

        # Low (MASE > 1.25): WAPE 0.30, MASE 1.4
        conf_low_mase, _ = classify_forecast_confidence(wape=0.30, mase=1.4, observation_count=6)
        self.assertEqual(conf_low_mase, "low")

        # Strictly monotonic error hierarchy:
        error_rank = {"high": 1, "normal": 2, "low": 3}
        self.assertLess(error_rank[conf_high], error_rank[conf_norm])
        self.assertLess(error_rank[conf_norm], error_rank[conf_low])

    def test_deterministic_confidence(self):
        # Repeated invocations must yield identical outcomes
        for _ in range(10):
            c1, r1 = classify_forecast_confidence(wape=0.32, mase=0.95, observation_count=8)
            self.assertEqual(c1, "high")
            self.assertEqual(r1, "wape_0.3200")

    def test_extreme_error_handling(self):
        # 500% error
        actual = [10.0, 20.0, 10.0, 20.0, 10.0, 20.0]
        forecast = [100.0, 200.0, 100.0, 200.0, 100.0, 200.0]
        metrics = calculate_forecast_error_metrics(actual, forecast)
        self.assertGreater(metrics["wape"], 5.0)

        conf, reason = classify_forecast_confidence(
            metrics["wape"],
            observation_count=metrics["observation_count"],
            actual_sum=metrics["actual_sum"],
            forecast_sum=metrics["forecast_sum"],
        )
        self.assertEqual(conf, "low")
        self.assertIn("wape_over_50_pct", reason)

    def test_nan_inf_handling(self):
        # Handle dirty data with NaNs and Infs cleanly
        actual = [10.0, np.nan, 30.0, np.inf, 50.0, 60.0, 70.0]
        forecast = [12.0, 20.0, np.nan, 40.0, 55.0, 62.0, 68.0]
        metrics = calculate_forecast_error_metrics(actual, forecast)
        self.assertEqual(metrics["observation_count"], 4)
        self.assertIsNotNone(metrics["wape"])
        self.assertTrue(math.isfinite(metrics["wape"]))

        # Undefined WAPE
        conf, reason = classify_forecast_confidence(wape=float("nan"), observation_count=6)
        self.assertEqual(conf, "low")
        self.assertEqual(reason, "undefined_or_infinite_error")

    def test_dead_stock_handling(self):
        conf, reason = classify_forecast_confidence(
            wape=0.0,
            dead_stock=True,
            observation_count=6,
        )
        self.assertEqual(conf, "trivial_zero")
        self.assertEqual(reason, "dead_stock_zero_demand")

    def test_intermittent_handling(self):
        actual = [0.0, 0.0, 50.0, 0.0, 100.0, 0.0]
        forecast = [10.0, 10.0, 30.0, 10.0, 70.0, 10.0]
        metrics = calculate_forecast_error_metrics(actual, forecast)
        self.assertEqual(metrics["observation_count"], 6)
        self.assertTrue(metrics["wape"] > 0)
        self.assertTrue(math.isfinite(metrics["wape"]))
        self.assertAlmostEqual(metrics["actual_sum"], 150.0)

        conf, _ = classify_forecast_confidence(
            wape=metrics["wape"],
            observation_count=metrics["observation_count"],
            actual_sum=metrics["actual_sum"],
            forecast_sum=metrics["forecast_sum"],
        )
        # WAPE is 80/150 = 53.33% > 50% -> low
        self.assertEqual(conf, "low")

    def test_confidence_does_not_change_replenishment_action_or_quantities(self):
        """
        Task 7 Scope Rule:
        Confidence is a diagnostic / reliability classification and must NOT
        change the replenishment action (e.g. purchase -> review) or quantities.
        """
        base_understocked = {
            "next_month_forecast": 100.0,
            "forecasted_horizon_demand": 380.0,
            "usable_stock": 200.0,
            "incoming_stock": 50.0,
            "committed_stock": 30.0,
            "demand_pattern": "intermittent",
            "sigma_error": 45.2,
        }

        rec_none = build_recommendation({**base_understocked, "confidence": None})
        rec_high = build_recommendation({**base_understocked, "confidence": "high"})
        rec_normal = build_recommendation({**base_understocked, "confidence": "normal"})
        rec_low = build_recommendation({**base_understocked, "confidence": "low"})

        fields_to_check = [
            "action",
            "reason_codes",
            "suggested_purchase_qty",
            "forecasted_horizon_demand",
            "safety_stock",
            "target_stock",
            "inventory_position",
            "stock_gap",
        ]

        for field in fields_to_check:
            self.assertEqual(
                rec_none[field],
                rec_low[field],
                f"Field '{field}' changed when confidence was set to 'low'!",
            )
            self.assertEqual(
                rec_normal[field],
                rec_low[field],
                f"Field '{field}' differed between 'normal' and 'low' confidence!",
            )
            self.assertEqual(
                rec_high[field],
                rec_low[field],
                f"Field '{field}' differed between 'high' and 'low' confidence!",
            )

        self.assertEqual(rec_low["action"], "purchase")
        self.assertNotIn("low_forecast_confidence", rec_low["reason_codes"])


if __name__ == "__main__":
    unittest.main()
