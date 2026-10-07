"""
Unit Test Suite for Step 12: Forecasting Engine Hardening & Universal Coverage.

Verifies:
- Task 14: Adversarial Synthetic Tests on 10 difficult demand histories
- Task 3: History Sufficiency Layer (length, quality, eligibility, reason)
- Task 4: Universal Fallback Hierarchy (Levels 0, 1, 2, 3, 4)
- Task 5: Demand Pattern Hardening (Reactivation & Sudden Collapse)
- Task 9: Stockout-suppressed demand diagnostic flags
- Task 11: Business guardrails and safety invariants
- Task 15: Inventory recommendation chain safety
- Task 16: Portal-side PO model and status workflow (Strictly Zero Odoo Writes)
"""

import sys
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.forecasting.benchmark_v2.universal_engine import (
    UniversalForecastingEngine,
    HistorySufficiencyLayer,
    HistorySufficiency,
    UniversalForecastResult,
    CHAMPION_MODEL,
)
from app.forecasting.benchmark_v2.calibration import EmpiricalSafetyCalibrator
from app.forecasting.benchmark_v2.portal_po import (
    PortalPOService,
    PortalPORecord,
    ALLOWED_PO_STATUSES,
)


class TestAdversarialSyntheticHistories(unittest.TestCase):
    """Task 14: Deliberately difficult demand histories tested against champion and engine."""

    def setUp(self):
        self.calibrator = EmpiricalSafetyCalibrator()
        self.engine = UniversalForecastingEngine(calibrator=self.calibrator)

    def test_adversarial_vector_1_all_zeros(self):
        # [0, 0, 0, 0, 0, 0]
        s = pd.Series([0, 0, 0, 0, 0, 0], dtype=float)
        res = self.engine.forecast_product(product_id=9001, series=s, current_stock=10.0)
        self.assertEqual(res.forecast_1m, 0.0)
        self.assertEqual(res.forecast_h3, 0.0)
        self.assertEqual(res.target_stock, 0.0)
        self.assertEqual(res.suggested_purchase, 0.0)
        self.assertEqual(res.selected_strategy, "dead_stock_zero_clamp")

    def test_adversarial_vector_2_spike_at_start(self):
        # [10, 0, 0, 0, 0, 0]
        s = pd.Series([10, 0, 0, 0, 0, 0], dtype=float)
        res = self.engine.forecast_product(product_id=9002, series=s, current_stock=5.0)
        self.assertEqual(res.forecast_1m, 0.0)
        self.assertEqual(res.forecast_h3, 0.0)
        self.assertEqual(res.target_stock, 0.0)
        self.assertEqual(res.suggested_purchase, 0.0)

    def test_adversarial_vector_3_spike_in_middle(self):
        # [0, 0, 100, 0, 0, 0]
        s = pd.Series([0, 0, 100, 0, 0, 0], dtype=float)
        res = self.engine.forecast_product(product_id=9003, series=s, current_stock=20.0)
        self.assertEqual(res.forecast_1m, 0.0)
        self.assertEqual(res.forecast_h3, 0.0)
        self.assertEqual(res.target_stock, 0.0)
        self.assertEqual(res.suggested_purchase, 0.0)

    def test_adversarial_vector_4_flat_high(self):
        # [100, 100, 100, 100, 100, 100]
        s = pd.Series([100, 100, 100, 100, 100, 100], dtype=float)
        res = self.engine.forecast_product(product_id=9004, series=s, current_stock=50.0)
        self.assertAlmostEqual(res.forecast_1m, 100.0, places=1)
        self.assertAlmostEqual(res.forecast_h3, 100.0, places=1)
        self.assertGreater(res.target_stock, 100.0)
        self.assertGreater(res.suggested_purchase, 0.0)

    def test_adversarial_vector_5_rising(self):
        # [10, 20, 30, 40, 50, 60]
        s = pd.Series([10, 20, 30, 40, 50, 60], dtype=float)
        res = self.engine.forecast_product(product_id=9005, series=s, current_stock=0.0)
        self.assertGreater(res.forecast_1m, 0.0)
        self.assertGreater(res.forecast_h3, 0.0)
        self.assertFalse(np.isnan(res.forecast_h3))
        self.assertGreaterEqual(res.target_stock, res.forecast_h3)

    def test_adversarial_vector_6_falling(self):
        # [60, 50, 40, 30, 20, 10]
        s = pd.Series([60, 50, 40, 30, 20, 10], dtype=float)
        res = self.engine.forecast_product(product_id=9006, series=s, current_stock=100.0)
        self.assertGreater(res.forecast_1m, 0.0)
        self.assertLess(res.forecast_1m, 30.0)
        self.assertEqual(res.suggested_purchase, 0.0)  # Overstocked

    def test_adversarial_vector_7_huge_outlier_spike(self):
        # [10, 1000, 10, 10, 10, 10]
        s = pd.Series([10, 1000, 10, 10, 10, 10], dtype=float)
        res = self.engine.forecast_product(product_id=9007, series=s, current_stock=10.0)
        # Trimmed mean removes outlier; forecast must be ~10, NOT distorted by 1000
        self.assertAlmostEqual(res.forecast_1m, 10.0, places=1)
        self.assertAlmostEqual(res.forecast_h3, 10.0, places=1)

    def test_adversarial_vector_8_alternating(self):
        # [100, 0, 100, 0, 100, 0]
        s = pd.Series([100, 0, 100, 0, 100, 0], dtype=float)
        res = self.engine.forecast_product(product_id=9008, series=s, current_stock=0.0)
        self.assertGreaterEqual(res.forecast_1m, 0.0)
        self.assertFalse(np.isnan(res.forecast_1m))

    def test_adversarial_vector_9_single_late_spike(self):
        # [0, 0, 0, 50, 0, 0]
        s = pd.Series([0, 0, 0, 50, 0, 0], dtype=float)
        res = self.engine.forecast_product(product_id=9009, series=s, current_stock=10.0)
        # 2 trailing zeroes plus dead stock check
        self.assertEqual(res.forecast_1m, 0.0)
        self.assertEqual(res.target_stock, 0.0)

    def test_adversarial_vector_10_plateau_with_spike(self):
        # [5, 5, 5, 100, 5, 5]
        s = pd.Series([5, 5, 5, 100, 5, 5], dtype=float)
        res = self.engine.forecast_product(product_id=9010, series=s, current_stock=5.0)
        self.assertAlmostEqual(res.forecast_1m, 5.0, places=1)
        self.assertAlmostEqual(res.forecast_h3, 5.0, places=1)


class TestHistorySufficiencyLayer(unittest.TestCase):
    """Task 3: History Sufficiency Layer verification."""

    def test_empty_series_sufficiency(self):
        suff = HistorySufficiencyLayer.assess([], stock_on_hand=0.0)
        self.assertEqual(suff.history_length, 0)
        self.assertEqual(suff.positive_months, 0)
        self.assertEqual(suff.history_tier, "no_history")
        self.assertEqual(suff.history_quality, "none")
        self.assertEqual(suff.forecast_eligibility, "no_history_dormant")

    def test_extremely_short_series_sufficiency(self):
        # 2 calendar months
        suff = HistorySufficiencyLayer.assess([10, 20], stock_on_hand=5.0)
        self.assertEqual(suff.history_length, 2)
        self.assertEqual(suff.positive_months, 2)
        self.assertEqual(suff.history_tier, "<3m_extremely_short")
        self.assertEqual(suff.history_quality, "sparse")
        self.assertEqual(suff.forecast_eligibility, "extremely_short_fallback")

    def test_rich_long_series_sufficiency(self):
        s = [10] * 24
        suff = HistorySufficiencyLayer.assess(s, stock_on_hand=5.0)
        self.assertEqual(suff.history_length, 24)
        self.assertEqual(suff.positive_months, 24)
        self.assertEqual(suff.history_tier, ">=24m_long")
        self.assertEqual(suff.history_quality, "rich")
        self.assertEqual(suff.forecast_eligibility, "fully_eligible")


class TestUniversalFallbackHierarchy(unittest.TestCase):
    """Task 4: Deterministic fallback hierarchy levels."""

    def setUp(self):
        self.calibrator = EmpiricalSafetyCalibrator()
        self.engine = UniversalForecastingEngine(
            calibrator=self.calibrator,
            category_medians={"FABRIC_TEST": 40.0},
        )

    def test_level_0_champion_trimmed_mean(self):
        s = pd.Series([20, 25, 22, 28, 24, 26], dtype=float)
        res = self.engine.forecast_product(product_id=101, series=s, current_stock=10.0)
        self.assertEqual(res.selected_strategy, CHAMPION_MODEL)
        self.assertFalse(res.fallback_used)
        self.assertEqual(res.fallback_level, 0)

    def test_level_1_short_history_fallback(self):
        # 2 months history
        s = pd.Series([30, 50], dtype=float)
        res = self.engine.forecast_product(product_id=102, series=s, current_stock=10.0)
        self.assertEqual(res.selected_strategy, "recent_mean_fallback")
        self.assertTrue(res.fallback_used)
        self.assertEqual(res.fallback_level, 1)
        self.assertEqual(res.forecast_1m, 26.0)  # 65% damped positive mean (40.0 * 0.65)

    def test_level_2_category_analogue_fallback(self):
        # 0 history but cold_start with category median
        s = pd.Series([], dtype=float)
        res = self.engine.forecast_product(
            product_id=103,
            series=s,
            current_stock=0.0,
            category_id="FABRIC_TEST",
        )
        self.assertTrue(res.fallback_used)
        self.assertIn(res.fallback_level, [2, 4])

    def test_level_3_dead_stock_zero_clamp(self):
        # Dormant 12 months with stock
        s = pd.Series([50] + [0] * 12, dtype=float)
        res = self.engine.forecast_product(product_id=104, series=s, current_stock=20.0)
        self.assertEqual(res.selected_strategy, "dead_stock_zero_clamp")
        self.assertTrue(res.fallback_used)
        self.assertEqual(res.fallback_level, 3)
        self.assertEqual(res.forecast_1m, 0.0)
        self.assertEqual(res.target_stock, 0.0)
        self.assertEqual(res.suggested_purchase, 0.0)


class TestSafetyInvariantsAndSanity(unittest.TestCase):
    """Task 11 & 13: Safety Invariants and Business Guardrails."""

    def setUp(self):
        self.engine = UniversalForecastingEngine()

    def test_negative_stock_ledger_is_floored(self):
        # Ledger shows -5.0
        s = pd.Series([10, 10, 10, 10, 10, 10], dtype=float)
        res = self.engine.forecast_product(product_id=201, series=s, current_stock=-5.0)
        self.assertEqual(res.current_stock, 0.0)
        self.assertGreater(res.suggested_purchase, 0.0)

    def test_phantom_demand_protection_on_collapsed_demand(self):
        # Sold heavily in distant past, 0 in last 3 months
        s = pd.Series([100, 100, 100, 0, 0, 0], dtype=float)
        res = self.engine.forecast_product(product_id=202, series=s, current_stock=0.0)
        self.assertEqual(res.forecast_h3, 0.0)
        self.assertEqual(res.safety_buffer, 0.0)
        self.assertEqual(res.target_stock, 0.0)
        self.assertEqual(res.suggested_purchase, 0.0)

    def test_stockout_risk_flag_trigger(self):
        # 0 stock, 0 in last 3m, but sold in previous 12m
        s = pd.Series([20, 20, 20, 20, 20, 0, 0, 0], dtype=float)
        res = self.engine.forecast_product(product_id=203, series=s, current_stock=0.0)
        self.assertIn("stockout_suppressed_demand_risk", res.diagnostic_flags)


class TestPortalPOService(unittest.TestCase):
    """Task 16: Portal-side PO Model Only (Strictly Zero Odoo Writes)."""

    def setUp(self):
        self.service = PortalPOService()

    def test_create_draft_po_and_lifecycle(self):
        mock_approvals = [
            {
                "approval_id": "appr_test_001",
                "snapshot_id": "snap_test_001",
                "product_id": 99991,
                "product_name": "Test Fabric Silk White",
                "approved_quantity": 50.0,
                "unit_price": 4.50,
                "forecast_1m": 25.0,
                "forecast_h3": 25.0,
                "target_stock": 60.0,
                "current_stock": 10.0,
                "status": "APPROVED",
            },
            {
                "approval_id": "appr_test_002",
                "snapshot_id": "snap_test_001",
                "product_id": 99992,
                "product_name": "Test Fabric Silk Black",
                "approved_quantity": 30.0,
                "unit_price": 5.00,
                "forecast_1m": 15.0,
                "forecast_h3": 15.0,
                "target_stock": 40.0,
                "current_stock": 10.0,
                "status": "APPROVED",
            },
        ]

        ref = f"PO-TEST-{int(pd.Timestamp.now().timestamp())}"
        po = self.service.create_draft_po_from_approvals(
            po_reference=ref,
            approval_records=mock_approvals,
            vendor_id=77,
            vendor_name="Test Silk Mills Ltd",
            notes="Quarterly replenishment draft",
        )

        self.assertEqual(po.status, "DRAFT")
        self.assertEqual(po.total_quantity, 80.0)
        self.assertEqual(po.total_amount, 375.0)  # 50*4.50 + 30*5.00 = 225 + 150 = 375
        self.assertEqual(len(po.lines), 2)

        # Status transition to APPROVED_FOR_EXTERNAL_SYNC
        upd = self.service.update_po_status(po.po_id, "APPROVED_FOR_EXTERNAL_SYNC")
        self.assertEqual(upd["status"], "APPROVED_FOR_EXTERNAL_SYNC")

        # Status transition to CANCELLED
        upd2 = self.service.update_po_status(po.po_id, "CANCELLED")
        self.assertEqual(upd2["status"], "CANCELLED")

    def test_negative_quantity_rejected(self):
        bad_approval = [{
            "approval_id": "appr_bad_001",
            "product_id": 99993,
            "approved_quantity": -10.0,
        }]
        with self.assertRaises(ValueError):
            self.service.create_draft_po_from_approvals("PO-BAD-001", bad_approval)


class TestStep13ActiveFallbackAndReactivation(unittest.TestCase):
    """Step 13: Active Fallback and Reactivation Accuracy Tests."""

    def setUp(self):
        self.engine = UniversalForecastingEngine()

    def test_reactivation_candidate_diagnostic_flag(self):
        # Product with sales, then 4 months gap, then renewed sale in last month
        # [20, 20, 0, 0, 0, 0, 30]
        s = pd.Series([20, 20, 0, 0, 0, 0, 30], dtype=float)
        res = self.engine.forecast_product(product_id=5001, series=s, current_stock=0.0)
        self.assertIn("recent_reactivation_candidate", res.diagnostic_flags)
        # Verify it is not falsely clamped to dead stock
        self.assertNotEqual(res.demand_pattern, "dead_stock")

    def test_short_history_1m_damped(self):
        # 1 month history: [40]
        s = pd.Series([40], dtype=float)
        res = self.engine.forecast_product(product_id=5002, series=s, current_stock=0.0)
        # 50% damping: 40 * 0.50 = 20.0
        self.assertEqual(res.forecast_1m, 20.0)
        self.assertEqual(res.forecast_h3, 20.0)
        self.assertIn("single_recent_sale_diagnostic", res.diagnostic_flags)

    def test_short_history_2m_damped(self):
        # 2 months history: [30, 50]
        s = pd.Series([30, 50], dtype=float)
        res = self.engine.forecast_product(product_id=5003, series=s, current_stock=0.0)
        # 65% damping on mean(40): 40 * 0.65 = 26.0
        self.assertEqual(res.forecast_1m, 26.0)
        self.assertEqual(res.forecast_h3, 26.0)

    def test_single_observation_dormant_clamped(self):
        # Single sale 4 months ago, 0 since: [50, 0, 0, 0, 0]
        s = pd.Series([50, 0, 0, 0, 0], dtype=float)
        res = self.engine.forecast_product(product_id=5004, series=s, current_stock=10.0)
        self.assertEqual(res.forecast_1m, 0.0)
        self.assertEqual(res.forecast_h3, 0.0)
        self.assertEqual(res.target_stock, 0.0)
        self.assertEqual(res.suggested_purchase, 0.0)


if __name__ == "__main__":
    unittest.main()
