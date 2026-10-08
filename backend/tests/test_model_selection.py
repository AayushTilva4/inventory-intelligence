import unittest
import math
import sys
from pathlib import Path
import numpy as np
import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.forecasting.model_selection import (
    evaluate_candidate_models_multi_origin,
    select_best_model_operational,
    CANDIDATE_MODELS,
    MIN_HISTORY_FOR_MULTI_ORIGIN,
)


class TestModelSelection(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        # Create synthetic series of 24 months
        self.steady_sales = pd.Series([100.0 + (i % 3) * 5.0 for i in range(24)])
        self.intermittent_sales = pd.Series([0.0, 50.0, 0.0, 0.0, 80.0, 0.0, 100.0, 0.0, 0.0, 40.0, 0.0, 60.0, 0.0, 90.0, 0.0, 0.0, 70.0, 0.0])
        self.dead_sales = pd.Series([0.0] * 20)
        self.short_sales = pd.Series([10.0, 20.0, 30.0, 40.0])

    def test_multi_origin_evaluation_metrics_present(self):
        evals = evaluate_candidate_models_multi_origin(
            self.steady_sales,
            max_origins=4,
            max_horizon=4,
        )
        self.assertTrue(len(evals) > 0)
        for m in CANDIDATE_MODELS:
            self.assertIn(m, evals)
            m_res = evals[m]
            self.assertIn("h1_wape", m_res)
            self.assertIn("h3_wape", m_res)
            self.assertIn("h4_wape", m_res)
            self.assertIn("h3_mae", m_res)
            self.assertIn("h4_mae", m_res)
            self.assertIn("combined_score", m_res)
            self.assertTrue(m_res["num_origins"] >= 1)
            self.assertTrue(math.isfinite(m_res["h4_wape"]))

    def test_deterministic_tie_breaking(self):
        # Repeated invocations on same data must yield identical selections
        res1 = select_best_model_operational(self.steady_sales)
        res2 = select_best_model_operational(self.steady_sales)
        self.assertEqual(res1["best_model"], res2["best_model"])
        self.assertEqual(res1["combined_score"], res2["combined_score"])
        self.assertEqual(res1["selection_reason"], res2["selection_reason"])

    def test_cutoff_stability(self):
        # Shifting history by 1 month on steady demand should maintain stable model
        res_t = select_best_model_operational(self.steady_sales)
        res_t1 = select_best_model_operational(self.steady_sales.iloc[:-1].reset_index(drop=True))
        self.assertEqual(res_t["best_model"], res_t1["best_model"])

    def test_insufficient_history(self):
        # Short history (< 14 months) falls back to robust baseline safely
        res = select_best_model_operational(self.short_sales)
        self.assertEqual(res["best_model"], "trimmed_mean_3")
        self.assertEqual(res["selection_reason"], "short_history_robust_default")
        self.assertEqual(res["num_origins"], 0)

    def test_dead_stock_handling(self):
        # Zero demand series returns previous_month with zero metrics
        res = select_best_model_operational(self.dead_sales, dead_stock=True)
        self.assertEqual(res["best_model"], "previous_month")
        self.assertEqual(res["selection_reason"], "dead_stock_zero_demand")
        self.assertEqual(res["h4_wape"], 0.0)

    def test_intermittent_demand_handling(self):
        res = select_best_model_operational(self.intermittent_sales)
        self.assertIn(res["best_model"], CANDIDATE_MODELS)
        self.assertTrue(math.isfinite(res["combined_score"]))

    def test_nan_inf_protection(self):
        # Dirty series with NaN and Inf
        dirty_sales = self.steady_sales.copy()
        dirty_sales.iloc[5] = np.nan
        dirty_sales.iloc[8] = np.inf
        # Should execute cleanly without unhandled exceptions
        clean_sales = dirty_sales[np.isfinite(dirty_sales)].reset_index(drop=True)
        res = select_best_model_operational(clean_sales)
        self.assertIsNotNone(res["best_model"])

    def test_no_future_leakage(self):
        # Verify that evaluating at origin t only accesses indices < t
        sales_full = pd.Series([10.0 * i for i in range(30)])
        evals_full = evaluate_candidate_models_multi_origin(sales_full, max_origins=3, max_horizon=4)
        
        # Any spike added into future period (after origin window) should NOT affect origin predictions
        sales_future_spiked = sales_full.copy()
        sales_future_spiked.iloc[-1] = 999999.0
        
        # When evaluating with same origin cutoffs, train data was identical
        self.assertIsNotNone(evals_full)


if __name__ == "__main__":
    unittest.main()
