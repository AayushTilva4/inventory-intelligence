import unittest
import pandas as pd
import numpy as np

from app.forecasting.cold_start_analogue_service import (
    compute_attribute_similarity,
    get_cold_start_analogues,
    MIN_EFFECTIVE_SIMILARITY_THRESHOLD,
    CREDIBILITY_CONSTANT_K,
)
from app.forecasting.group_forecast_service import get_group_forecast, MINIMUM_HISTORY
from app.inventory.group_recommendation_service import get_group_recommendation


class TestColdStartAnalogueDiagnostic(unittest.TestCase):
    def test_attribute_similarity_exact_matches(self):
        """When attributes match exactly, score reflects full weighted components and 100% coverage."""
        target = {
            "categ_id": 101,
            "brand_id": 5,
            "composition": "100% Polyester",
            "quality": "Velvet",
            "gsm": "320",
            "list_price": 50.0,
            "main_product": 1001,
        }
        candidate = {
            "categ_id": 101,
            "brand_id": 5,
            "composition": "100% polyester",
            "quality": "velvet",
            "gsm": "320",
            "list_price": 50.0,
            "main_product": 1001,
            "link_sources": "similar_relation",
        }
        sim = compute_attribute_similarity(target, candidate)
        self.assertGreaterEqual(sim["effective_similarity_score"], 0.90)
        self.assertTrue(sim["has_explicit_link"])
        self.assertEqual(sim["evidence_coverage"], 1.0)
        self.assertGreaterEqual(sim["matched_attribute_count"], 5)
        self.assertIn("categ_id", sim["matching_attributes"])
        self.assertIn("brand_id", sim["matching_attributes"])
        self.assertIn("composition", sim["matching_attributes"])
        self.assertIn("quality", sim["matching_attributes"])
        self.assertEqual(len(sim["missing_attributes"]), 0)
        self.assertEqual(len(sim["unmatched_attributes"]), 0)

    def test_exact_numerical_formula_and_coverage_identity(self):
        """Verify the exact mathematical relationship effective_similarity = raw_similarity * evidence_coverage."""
        # Case A: Only Category (0.25) matches out of 0.75 benchmark
        t_a = {"categ_id": 100}
        c_a = {"categ_id": 100}
        sim_a = compute_attribute_similarity(t_a, c_a)
        self.assertEqual(sim_a["raw_similarity_score"], 1.0)
        self.assertAlmostEqual(sim_a["available_weight"], 0.25, places=4)
        self.assertAlmostEqual(sim_a["evidence_coverage"], 0.25 / 0.75, places=4)
        self.assertAlmostEqual(sim_a["effective_similarity_score"], 0.25 / 0.75, places=4)
        self.assertAlmostEqual(
            sim_a["effective_similarity_score"],
            sim_a["raw_similarity_score"] * sim_a["evidence_coverage"],
            places=4,
        )

        # Case B: Category (0.25) matches, Brand (0.15) present but mismatches
        t_b = {"categ_id": 100, "brand_id": 1}
        c_b = {"categ_id": 100, "brand_id": 2}
        sim_b = compute_attribute_similarity(t_b, c_b)
        self.assertAlmostEqual(sim_b["available_weight"], 0.40, places=4)
        self.assertAlmostEqual(sim_b["raw_similarity_score"], 0.25 / 0.40, places=4)  # 0.625
        self.assertAlmostEqual(sim_b["evidence_coverage"], 0.40 / 0.75, places=4)     # 0.5333
        self.assertAlmostEqual(sim_b["effective_similarity_score"], 0.25 / 0.75, places=4)  # 0.3333
        self.assertAlmostEqual(
            sim_b["effective_similarity_score"],
            sim_b["raw_similarity_score"] * sim_b["evidence_coverage"],
            places=4,
        )

        # Case C: Explicit Lineage (similar_rel = 0.35) + Category (0.25) match
        t_c = {"categ_id": 100}
        c_c = {"categ_id": 100, "link_sources": "similar_relation"}
        sim_c = compute_attribute_similarity(t_c, c_c)
        self.assertTrue(sim_c["has_explicit_link"])
        self.assertAlmostEqual(sim_c["available_weight"], 0.60, places=4)
        self.assertAlmostEqual(sim_c["raw_similarity_score"], 1.0, places=4)
        self.assertAlmostEqual(sim_c["evidence_coverage"], 0.60 / 1.0, places=4)
        self.assertAlmostEqual(sim_c["effective_similarity_score"], 0.60 / 1.0, places=4)
        self.assertAlmostEqual(
            sim_c["effective_similarity_score"],
            sim_c["raw_similarity_score"] * sim_c["evidence_coverage"],
            places=4,
        )

    def test_missing_attributes_not_hallucinated(self):
        """Missing attributes in target or candidate must be marked in missing_attributes without inventing matches."""
        target = {
            "categ_id": 101,
            "brand_id": None,
            "composition": None,
            "quality": None,
            "gsm": None,
            "list_price": None,
        }
        candidate = {
            "categ_id": 101,
            "brand_id": 5,
            "composition": "Cotton",
            "quality": "Linen Look",
            "gsm": "250",
            "list_price": 40.0,
        }
        sim = compute_attribute_similarity(target, candidate)
        self.assertIn("categ_id", sim["matching_attributes"])
        self.assertIn("brand_id", sim["missing_attributes"])
        self.assertIn("composition", sim["missing_attributes"])
        self.assertIn("quality", sim["missing_attributes"])
        self.assertIn("gsm", sim["missing_attributes"])
        self.assertIn("list_price", sim["missing_attributes"])
        self.assertAlmostEqual(sim["effective_similarity_score"], 0.25 / 0.75, places=3)
        self.assertEqual(sim["matched_attribute_count"], 1)

    def test_sparse_attributes_denominator_shrinkage_prevented(self):
        """Sparse attribute overlap must not yield artificial 100% similarity score."""
        target = {
            "categ_id": 101,
            "brand_id": None,
            "composition": None,
            "quality": None,
            "gsm": None,
            "list_price": None,
        }
        candidate = {
            "categ_id": 101,
            "brand_id": None,
            "composition": None,
            "quality": None,
            "gsm": None,
            "list_price": None,
        }
        sim = compute_attribute_similarity(target, candidate)
        self.assertEqual(sim["raw_similarity_score"], 1.0)
        self.assertAlmostEqual(sim["effective_similarity_score"], 0.3333, places=3)
        self.assertAlmostEqual(sim["evidence_coverage"], 0.3333, places=3)

    def test_unmatched_attributes_tracked(self):
        """Different attributes must be tracked in unmatched_attributes and not contribute to score."""
        target = {
            "categ_id": 101,
            "brand_id": 5,
            "composition": "100% Polyester",
            "quality": "Velvet",
            "gsm": "350",
            "list_price": 60.0,
        }
        candidate = {
            "categ_id": 202,  # different
            "brand_id": 9,    # different
            "composition": "100% Linen",  # different
            "quality": "Sheer",  # different
            "gsm": "120",  # different (>25% diff)
            "list_price": 20.0,  # different (>35% diff)
        }
        sim = compute_attribute_similarity(target, candidate)
        self.assertEqual(sim["effective_similarity_score"], 0.0)
        self.assertEqual(sim["matched_attribute_count"], 0)
        self.assertIn("categ_id", sim["unmatched_attributes"])
        self.assertIn("brand_id", sim["unmatched_attributes"])
        self.assertIn("composition", sim["unmatched_attributes"])
        self.assertIn("quality", sim["unmatched_attributes"])
        self.assertIn("gsm", sim["unmatched_attributes"])
        self.assertIn("list_price", sim["unmatched_attributes"])

    def test_score_range_and_boundary_conditions(self):
        """All computed scores must strictly reside within [0.0, 1.0]."""
        for t, c in [
            ({}, {}),
            ({"categ_id": 1}, {"categ_id": 1}),
            ({"list_price": -10}, {"list_price": 50}),
            ({"gsm": "abc"}, {"gsm": "def"}),
        ]:
            sim = compute_attribute_similarity(t, c)
            self.assertGreaterEqual(sim["effective_similarity_score"], 0.0)
            self.assertLessEqual(sim["effective_similarity_score"], 1.0)
            self.assertGreaterEqual(sim["raw_similarity_score"], 0.0)
            self.assertLessEqual(sim["raw_similarity_score"], 1.0)
            self.assertGreaterEqual(sim["evidence_coverage"], 0.0)
            self.assertLessEqual(sim["evidence_coverage"], 1.0)

    def test_zero_history_diagnostic_generation(self):
        """Products with 0 months of sales receive clean diagnostic with candidate signals without modifying operational invariants."""
        diag = get_cold_start_analogues(target_product_id=7737, target_history_sales=[])
        self.assertIn("status", diag)
        self.assertIn(diag["status"], ["cold_start_analogue_available", "cold_start_no_suitable_analogue"])
        self.assertEqual(diag["diagnostic_type"], "cold_start_historical_analogue")
        self.assertIn("limitations", diag)
        self.assertGreaterEqual(len(diag["limitations"]), 1)
        if diag["status"] == "cold_start_analogue_available":
            self.assertIsNotNone(diag["summary_analogue_estimate"])
            self.assertEqual(diag["target_history_months"], 0)
            self.assertEqual(diag["credibility_weight_z"], 0.0)
            self.assertGreater(diag["candidate_count"], 0)
            for c in diag["analogue_candidates"]:
                self.assertGreaterEqual(c["history_months"], 6)
                self.assertGreaterEqual(c["effective_similarity_score"], 0.0)

    def test_1_to_5_months_history_bayesian_credibility(self):
        """Products with 1-5 months of history blend candidate demand with target observed mean via Bayesian credibility."""
        own_early_sales = pd.Series([20.0, 25.0, 30.0])  # 3 months, mean = 25.0
        diag = get_cold_start_analogues(target_product_id=7737, target_history_sales=own_early_sales)
        if diag["status"] == "cold_start_analogue_available":
            self.assertEqual(diag["target_history_months"], 3)
            self.assertEqual(diag["target_observed_mean"], 25.0)
            expected_z = round(3.0 / (3.0 + CREDIBILITY_CONSTANT_K), 3)  # 3 / (3 + 3) = 0.50
            self.assertEqual(diag["credibility_weight_z"], expected_z)
            self.assertIn("analogue_prior_median", diag)

    def test_division_by_zero_and_empty_candidate_safety(self):
        """Candidates with 0 sales or non-numeric fields do not cause division-by-zero or crash."""
        target = {"categ_id": 101, "list_price": 0.0, "gsm": "invalid_gsm"}
        candidate = {"categ_id": 101, "list_price": "none", "gsm": None}
        sim = compute_attribute_similarity(target, candidate)
        self.assertIsInstance(sim["effective_similarity_score"], float)
        self.assertIn("list_price", sim["missing_attributes"])
        self.assertIn("gsm", sim["missing_attributes"])

    def test_no_suitable_analogue_fallback(self):
        """When a target has non-existent ID, diagnostic returns clean fallback with zero candidates."""
        diag = get_cold_start_analogues(target_product_id=99999999)
        self.assertEqual(diag["status"], "cold_start_target_not_found")
        self.assertEqual(diag["candidate_count"], 0)
        self.assertIsNone(diag["summary_analogue_estimate"])

    def test_ranking_by_effective_similarity(self):
        """Candidates must be sorted primarily by effective similarity score descending."""
        diag = get_cold_start_analogues(target_product_id=7737)
        if diag["status"] == "cold_start_analogue_available" and len(diag["analogue_candidates"]) >= 2:
            cands = diag["analogue_candidates"]
            for i in range(len(cands) - 1):
                self.assertGreaterEqual(cands[i]["effective_similarity_score"], cands[i+1]["effective_similarity_score"])

    def test_invariance_for_6_plus_months_products(self):
        """Products with >= 6 months of usable history retain operational forecasts without cold_start_diagnostic interference."""
        self.assertEqual(MINIMUM_HISTORY, 6)
        fc = get_group_forecast(21)  # 351-09 (18 months)
        if fc:
            self.assertEqual(fc["status"], "ok")
            self.assertIsNotNone(fc["next_month_forecast"])
            self.assertNotIn("cold_start_diagnostic", fc)

    def test_diagnostic_does_not_alter_recommendation_action(self):
        """A cold-start group (N < 6) must remain status='insufficient_group_history', action='review', suggested_purchase_qty=0."""
        rec = get_group_recommendation(18569)  # 426-01
        if rec and rec["group_valid"]:
            self.assertEqual(rec["action"], "review")
            self.assertEqual(rec["group_suggested_purchase_qty"], 0)
            self.assertEqual(rec["status"], "insufficient_group_history")
            self.assertIn("group_forecast_unavailable", rec["reason_codes"])


if __name__ == "__main__":
    unittest.main()
