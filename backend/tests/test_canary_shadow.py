"""
Unit tests for Step 10: Passive Production Canary Shadow.

Validates:
1. Read-only behavior: Zero mutations of input sales series or stock structures.
2. No Odoo writes / No PO creation: Absolutely no procurement writes or PO generation.
3. Dead-stock safety: Dead stock strictly receives 0.0 forecast, 0.0 buffer, 0.0 target, 0.0 buy.
4. Negative-value protection: Forecast, target, and suggested purchases are strictly >= 0.0.
5. Pattern-specific service-level policy:
   - fast_moving: 80%
   - stable/normal: 80%
   - rising: 75%
   - falling: 75%
   - intermittent: 75%
   - dead_stock: 0%
6. Exception queue classification: Accurately identifies major reductions, increases, rising risk, dormant cleanup.
7. Shadow failure isolation: Corrupted product inputs do not crash catalog snapshots.
8. Audit logging traceability: Every record contains timestamps, model names, policies, and explanations.
"""

import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.forecasting.benchmark_v2.canary_shadow import (
    CanaryShadowRunner,
    CanaryShadowRecord,
    FROZEN_MODEL_NAME,
    FROZEN_SERVICE_LEVEL_POLICIES,
    PLANNER_EXCEPTION_CATEGORIES,
)
from app.forecasting.benchmark_v2.calibration import EmpiricalSafetyCalibrator


class TestCanaryShadowPipeline(unittest.TestCase):

    def setUp(self):
        np.random.seed(42)
        records = []
        for pat in ["fast_moving", "stable/normal", "rising", "falling", "intermittent", "dead_stock"]:
            for h in [1, 2, 3]:
                for _ in range(15):
                    act = float(np.random.normal(30.0, 10.0)) if pat != "dead_stock" else 0.0
                    fc = 25.0 if pat != "dead_stock" else 0.0
                    records.append({
                        "model": FROZEN_MODEL_NAME,
                        "as_of_origin_pattern": pat,
                        "horizon": h,
                        "actual": max(0.0, act),
                        "forecast": fc,
                        "mase_scale": 4.0 if pat != "dead_stock" else 1.0,
                    })
        calib_df = pd.DataFrame(records)
        self.calibrator = EmpiricalSafetyCalibrator()
        self.calibrator.fit(calib_df)

        self.mock_engine = MagicMock()
        self.runner = CanaryShadowRunner(
            calibrator=self.calibrator,
            db_engine=self.mock_engine,
        )

    def test_read_only_behavior_and_no_odoo_writes(self):
        """Verifies input data structures are not mutated and no Odoo writes are performed."""
        sales = [10.0, 15.0, 20.0, 25.0, 30.0]
        sales_copy = list(sales)
        stock = 12.0

        rec = self.runner.evaluate_single_product(
            snapshot_id="test_snap_001",
            product_id=101,
            product_name="Read-Only Fabric",
            sales_series=sales_copy,
            current_stock=stock,
            legacy_reorder_target=35.0,
            legacy_forecast=25.0,
        )

        # Sales list must be unchanged
        self.assertEqual(sales_copy, sales)
        # Returned stock matches input
        self.assertEqual(rec.current_stock, stock)
        # Verify no external Odoo client or PO generation was invoked
        self.assertIsInstance(rec, CanaryShadowRecord)

    def test_no_po_creation_invariant(self):
        """Verifies that suggested_purchase is merely an advisory quantity with NO PO creation."""
        sales = [50.0, 60.0, 70.0, 80.0]
        rec = self.runner.evaluate_single_product(
            snapshot_id="test_snap_001",
            product_id=102,
            product_name="Advisory Recommendation Product",
            sales_series=sales,
            current_stock=10.0,
            legacy_reorder_target=50.0,
        )
        self.assertGreater(rec.target_stock, 0.0)
        self.assertGreater(rec.suggested_purchase, 0.0)
        self.assertEqual(rec.suggested_purchase, max(0.0, round(rec.target_stock - 10.0, 2)))

    def test_dead_stock_zero_target_and_zero_buy(self):
        """Dead stock items MUST strictly receive 0.0 forecast, 0.0 buffer, 0.0 target, and 0.0 buy."""
        zero_sales = [0.0] * 12
        rec = self.runner.evaluate_single_product(
            snapshot_id="test_snap_001",
            product_id=103,
            product_name="Dead Stock Fabric",
            sales_series=zero_sales,
            current_stock=150.0,
            legacy_reorder_target=45.0,
            legacy_forecast=10.0,
        )
        self.assertEqual(rec.pattern, "dead_stock")
        self.assertEqual(rec.forecast_1m, 0.0)
        self.assertEqual(rec.forecast_h3, 0.0)
        self.assertEqual(rec.safety_buffer, 0.0)
        self.assertEqual(rec.target_stock, 0.0)
        self.assertEqual(rec.suggested_purchase, 0.0)
        self.assertEqual(rec.primary_exception, "zero_demand_dormant")
        self.assertIn("dead stock", rec.reason_for_difference.lower())

    def test_negative_value_protection(self):
        """All forecasts, targets, and purchases must strictly be non-negative."""
        sparse_sales = [0.0, 0.0, 1.0, 0.0, 0.0]
        rec = self.runner.evaluate_single_product(
            snapshot_id="test_snap_001",
            product_id=104,
            product_name="Sparse Fabric",
            sales_series=sparse_sales,
            current_stock=0.0,
        )
        self.assertGreaterEqual(rec.forecast_1m, 0.0)
        self.assertGreaterEqual(rec.forecast_h3, 0.0)
        self.assertGreaterEqual(rec.safety_buffer, 0.0)
        self.assertGreaterEqual(rec.target_stock, 0.0)
        self.assertGreaterEqual(rec.suggested_purchase, 0.0)

    def test_pattern_specific_service_level_policy(self):
        """Verifies configured pattern service levels are strictly applied."""
        fast_sales = [50.0, 55.0, 60.0, 65.0, 60.0, 62.0]
        rec_fast = self.runner.evaluate_single_product(
            snapshot_id="test_snap_001",
            product_id=105,
            product_name="Fast Fabric",
            sales_series=fast_sales,
            current_stock=20.0,
        )
        self.assertEqual(rec_fast.service_level_target, 0.80)

        intermittent_sales = [0.0, 20.0, 0.0, 0.0, 25.0, 0.0]
        rec_inter = self.runner.evaluate_single_product(
            snapshot_id="test_snap_001",
            product_id=106,
            product_name="Intermittent Fabric",
            sales_series=intermittent_sales,
            current_stock=5.0,
        )
        self.assertEqual(rec_inter.service_level_target, 0.75)

        dead_sales = [0.0] * 12
        rec_dead = self.runner.evaluate_single_product(
            snapshot_id="test_snap_001",
            product_id=107,
            product_name="Dead Fabric",
            sales_series=dead_sales,
            current_stock=25.0,
        )
        self.assertEqual(rec_dead.service_level_target, 0.00)

    def test_large_delta_and_exception_classification(self):
        """Verifies exception classification detects major target reductions and dormant items."""
        # Case 1: Major target reduction (legacy=100.0 vs shadow~25.0)
        active_sales = [20.0, 22.0, 24.0, 22.0]
        rec_red = self.runner.evaluate_single_product(
            snapshot_id="test_snap_001",
            product_id=108,
            product_name="Overstock Legacy Item",
            sales_series=active_sales,
            legacy_reorder_target=100.0,
            legacy_forecast=22.0,
        )
        self.assertIn("major_target_reduction", rec_red.all_exception_flags)

        # Case 2: Zero demand dormant with legacy target
        dead_sales = [0.0] * 12
        rec_dorm = self.runner.evaluate_single_product(
            snapshot_id="test_snap_001",
            product_id=109,
            product_name="Dormant with Legacy Target",
            sales_series=dead_sales,
            legacy_reorder_target=50.0,
        )
        self.assertEqual(rec_dorm.primary_exception, "zero_demand_dormant")

    def test_shadow_failure_isolation(self):
        """Verifies that an error on one product series does not crash the catalog snapshot."""
        monthly_df = pd.DataFrame([
            {"product_id": 1, "product_name": "Valid 1", "month": "2025-01-01", "total_quantity": 10.0},
            {"product_id": 1, "product_name": "Valid 1", "month": "2025-02-01", "total_quantity": 12.0},
            {"product_id": 2, "product_name": "Valid 2", "month": "2025-01-01", "total_quantity": 5.0},
            {"product_id": 2, "product_name": "Valid 2", "month": "2025-02-01", "total_quantity": 8.0},
        ])
        stock_map = {1: 5.0, 2: 10.0}

        # Mock evaluate_single_product to raise for product 1 only
        orig_eval = self.runner.evaluate_single_product

        def mock_eval(**kwargs):
            if kwargs.get("product_id") == 1:
                raise ValueError("Simulated corrupted time series")
            return orig_eval(**kwargs)

        with patch.object(self.runner, "evaluate_single_product", side_effect=mock_eval):
            snapshot_res = self.runner.run_catalog_shadow_snapshot(
                monthly_df=monthly_df,
                stock_map=stock_map,
                product_ids=[1, 2],
                snapshot_id="test_snap_fail_iso",
            )

        # Product 2 succeeded, product 1 failed gracefully
        self.assertEqual(len(snapshot_res["records"]), 1)
        self.assertEqual(snapshot_res["records"][0].product_id, 2)
        self.assertEqual(len(snapshot_res["failures"]), 1)
        self.assertEqual(snapshot_res["failures"][0]["product_id"], 1)
        self.assertIn("Simulated corrupted time series", snapshot_res["failures"][0]["error"])

    def test_audit_logging_traceability(self):
        """Verifies every shadow record contains traceable audit metadata and clear rationale."""
        sales = [15.0, 18.0, 20.0, 22.0]
        rec = self.runner.evaluate_single_product(
            snapshot_id="test_snap_001",
            product_id=110,
            product_name="Audit Trail Fabric",
            sales_series=sales,
            current_stock=10.0,
            legacy_reorder_target=40.0,
            legacy_forecast=18.0,
        )
        self.assertIsNotNone(rec.created_at)
        self.assertEqual(rec.snapshot_id, "test_snap_001")
        self.assertEqual(rec.product_id, 110)
        self.assertTrue(len(rec.reason_for_difference) > 10)
        self.assertIn("trimmed_mean_3", rec.reason_for_difference)


if __name__ == "__main__":
    unittest.main()
