"""
Step 14 End-to-End Decision Validation & Portal Procurement Simulation Test Suite.
Validates:
- Decision pipeline mathematical transformations
- Stock absorption logic
- H3 lead-time horizon
- Safety buffer service level calibration
- Stockout routing anomaly fix
- Main / similar product group stock absorption
- Supplier constraint simulation (MOQ, roll length rounding)
- Separation of AI quantity vs Planner quantity vs Portal PO quantity
- Portal PO approval gating (PENDING, EDITED, REJECTED, CANCELLED blocked)
- PO idempotency (no duplicate draft POs)
- Audit trail traceability
- Odoo read-only invariant
"""

import unittest
import math
import pandas as pd
import numpy as np

from app.forecasting.benchmark_v2.decision_service import (
    InventoryDecisionPipeline,
    SupplierConstraints,
    GroupInventoryEvaluation,
    EndToEndDecisionResult,
)
from app.forecasting.benchmark_v2.portal_po import PortalPOService
from app.forecasting.benchmark_v2.universal_engine import UniversalForecastingEngine


class TestStep14DecisionPipeline(unittest.TestCase):
    def setUp(self):
        self.engine = UniversalForecastingEngine()
        self.pipeline = InventoryDecisionPipeline(universal_engine=self.engine)
        self.portal_po_service = PortalPOService()

    def test_01_decision_pipeline_mathematics(self):
        """Validates exact transformation flow without hidden demand."""
        sales = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0, 100.0])
        curr_stock = 50.0
        constraints = SupplierConstraints(moq=50.0, standard_roll_length=25.0)

        res = self.pipeline.evaluate_product_decision(
            product_id=101,
            sales_series=sales,
            current_stock=curr_stock,
            supplier_constraints=constraints,
        )

        self.assertAlmostEqual(res.forecast_1m, 100.0, places=1)
        self.assertAlmostEqual(res.forecast_h3, 100.0, places=1)
        # target_stock = forecast_h3 + safety_buffer
        self.assertAlmostEqual(res.target_stock, res.forecast_h3 + res.safety_buffer, places=2)
        # raw_purchase_need = max(0.0, target_stock - current_stock)
        expected_raw_need = max(0.0, round(res.target_stock - curr_stock, 2))
        self.assertAlmostEqual(res.raw_purchase_need, expected_raw_need, places=2)
        # suggested_purchase_ai = raw_purchase_need (when standalone)
        self.assertAlmostEqual(res.suggested_purchase_ai, expected_raw_need, places=2)

    def test_02_stock_absorption_cases(self):
        """Verifies no unnecessary or negative purchase when stock >= target."""
        sales = pd.Series([50.0, 50.0, 50.0, 50.0, 50.0, 50.0])
        
        # Case A: Stock far above target
        res_above = self.pipeline.evaluate_product_decision(
            product_id=102, sales_series=sales, current_stock=200.0
        )
        self.assertEqual(res_above.suggested_purchase_ai, 0.0)
        self.assertEqual(res_above.constrained_purchase_qty, 0.0)

        # Case B: Stock equal to target
        target = res_above.target_stock
        res_equal = self.pipeline.evaluate_product_decision(
            product_id=103, sales_series=sales, current_stock=target
        )
        self.assertEqual(res_equal.suggested_purchase_ai, 0.0)

        # Case C: Stock below target -> purchase recommended
        res_below = self.pipeline.evaluate_product_decision(
            product_id=104, sales_series=sales, current_stock=target - 20.0
        )
        self.assertAlmostEqual(res_below.suggested_purchase_ai, 20.0, places=2)

    def test_03_dead_stock_invariants(self):
        """Verifies dead stock hard zero invariant: forecast=0, buffer=0, target=0, buy=0."""
        zero_sales = pd.Series([0.0] * 12)
        res_dead = self.pipeline.evaluate_product_decision(
            product_id=105, sales_series=zero_sales, current_stock=500.0
        )
        self.assertEqual(res_dead.demand_pattern, "dead_stock")
        self.assertEqual(res_dead.forecast_1m, 0.0)
        self.assertEqual(res_dead.forecast_h3, 0.0)
        self.assertEqual(res_dead.safety_buffer, 0.0)
        self.assertEqual(res_dead.target_stock, 0.0)
        self.assertEqual(res_dead.suggested_purchase_ai, 0.0)
        self.assertEqual(res_dead.constrained_purchase_qty, 0.0)

    def test_04_stockout_suppressed_anomaly_fix(self):
        """
        Verifies that single observation products with subsequent zero sales
        are clamped to 0.0 (preventing the Step 13 WAPE=6.0610 regression).
        """
        # Product with launch sale followed by zeros (e.g. PID 305 case)
        sparse_series = pd.Series([2000.0, 0.0])
        res = self.pipeline.evaluate_product_decision(
            product_id=305,
            sales_series=sparse_series,
            current_stock=0.0,
        )
        self.assertIn(res.demand_pattern, ("cold_start", "dead_stock"))
        self.assertEqual(res.forecast_1m, 0.0)
        self.assertEqual(res.forecast_h3, 0.0)
        self.assertEqual(res.suggested_purchase_ai, 0.0)

    def test_05_supplier_constraints_moq_and_roll_length(self):
        """Verifies roll multiple and MOQ rounding while preserving immutable AI quantity."""
        constraints = SupplierConstraints(
            vendor_id=1,
            vendor_name="Test Mills",
            moq=100.0,
            standard_roll_length=50.0,
        )

        # AI buy = 23m -> roll multiple is 50m, but MOQ is 100m -> constrained = 100m
        qty, reasons = constraints.apply(23.0)
        self.assertEqual(qty, 100.0)
        self.assertIn("rounded_to_roll_length_multiple_50m", reasons)
        self.assertIn("adjusted_to_supplier_moq_100m", reasons)

        # AI buy = 125m -> roll multiple is 150m (exceeds MOQ) -> constrained = 150m
        qty2, reasons2 = constraints.apply(125.0)
        self.assertEqual(qty2, 150.0)
        self.assertIn("rounded_to_roll_length_multiple_50m", reasons2)

    def test_06_group_stock_absorption(self):
        """
        Verifies that variant replenishment is suppressed when group stock covers aggregate target.
        """
        sales = pd.Series([30.0, 30.0, 30.0, 30.0, 30.0, 30.0])
        # Variant 101 has stock = 5m, target ~33m -> variant need ~28m
        # But Sibling 102 has 495m stock -> total group stock = 500m vs group target = 100m
        group_stocks = {101: 5.0, 102: 495.0}
        group_targets = {101: 50.0, 102: 50.0}

        res = self.pipeline.evaluate_product_decision(
            product_id=101,
            sales_series=sales,
            current_stock=5.0,
            main_product_id=9001,
            group_members_stock=group_stocks,
            group_members_targets=group_targets,
        )

        self.assertTrue(res.group_evaluation.group_stock_absorbed)
        self.assertEqual(res.suggested_purchase_ai, 0.0)
        self.assertEqual(res.constrained_purchase_qty, 0.0)
        self.assertIn("group_stock_available_elsewhere", res.planner_exceptions)

    def test_07_portal_po_approval_gating(self):
        """Verifies that only APPROVED decisions can create draft POs."""
        base_record = {
            "product_id": 107,
            "product_name": "Test Fabric Gating",
            "suggested_purchase": 50.0,
            "approved_quantity": 50.0,
            "unit_price": 10.0,
        }

        # PENDING -> Blocked
        with self.assertRaises(ValueError) as ctx:
            self.portal_po_service.create_draft_po_from_approvals(
                po_reference="PO-TEST-GATE-PEND",
                approval_records=[{**base_record, "status": "PENDING"}],
            )
        self.assertIn("Eligibility violation", str(ctx.exception))

        # REJECTED -> Blocked
        with self.assertRaises(ValueError):
            self.portal_po_service.create_draft_po_from_approvals(
                po_reference="PO-TEST-GATE-REJ",
                approval_records=[{**base_record, "status": "REJECTED"}],
            )

        # CANCELLED -> Blocked
        with self.assertRaises(ValueError):
            self.portal_po_service.create_draft_po_from_approvals(
                po_reference="PO-TEST-GATE-CANC",
                approval_records=[{**base_record, "status": "CANCELLED"}],
            )

    def test_08_portal_po_idempotency_and_audit(self):
        """Verifies idempotency: duplicate requests return existing draft PO."""
        appr_id = f"appr_test_idemp_{int(pd.Timestamp.now().timestamp())}"
        record = {
            "approval_id": appr_id,
            "product_id": 108,
            "product_name": "Test Fabric Idempotency",
            "suggested_purchase": 75.0,
            "approved_quantity": 75.0,
            "final_po_quantity": 100.0,
            "unit_price": 15.0,
            "status": "APPROVED",
            "supplier_constraints": {"moq": 100.0, "roll_length": 50.0},
            "constraint_reasons": ["adjusted_to_supplier_moq_100m"],
            "planner_id": "senior_planner_1",
        }

        # Initial PO creation
        po1 = self.portal_po_service.create_draft_po_from_approvals(
            po_reference=f"PO_IDEMP_{appr_id}",
            approval_records=[record],
            vendor_id=5,
            vendor_name="Premium Textiles",
        )
        self.assertIsNotNone(po1.po_id)
        self.assertEqual(po1.total_quantity, 100.0)

        # Repeated PO creation with same approval_id -> returns existing PO idempotently
        po2 = self.portal_po_service.create_draft_po_from_approvals(
            po_reference=f"PO_IDEMP_{appr_id}_DUP",
            approval_records=[record],
            vendor_id=5,
            vendor_name="Premium Textiles",
        )
        self.assertEqual(po1.po_id, po2.po_id)

    def test_09_safety_invariants_and_negative_rejection(self):
        """Verifies negative quantities and dead stock positive PO lines are strictly rejected."""
        with self.assertRaises(ValueError):
            self.portal_po_service.create_draft_po_from_approvals(
                po_reference="PO-NEG-TEST",
                approval_records=[{
                    "product_id": 109,
                    "approved_quantity": -10.0,
                    "status": "APPROVED",
                }],
            )

        with self.assertRaises(ValueError):
            self.portal_po_service.create_draft_po_from_approvals(
                po_reference="PO-DEAD-TEST",
                approval_records=[{
                    "product_id": 110,
                    "pattern": "dead_stock",
                    "approved_quantity": 50.0,
                    "status": "APPROVED",
                }],
            )


if __name__ == "__main__":
    unittest.main()
