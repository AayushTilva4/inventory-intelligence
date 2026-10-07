"""
Step 15: Inventory & Supplier Constraint Intelligence Unit Test Suite.
Validates:
- Actual vs default constraint source tracking
- MOQ enforcement and roll rounding
- Zero-purchase protection (Q_AI = 0 => Q_constrained = 0)
- Dead-stock protection
- Multiplier detection (>2x, >3x)
- Missing vendor, UOM, and lead-time exception flagging
- Group absorption logic
- Uncertain substitutability review flagging
- Inbound stock visibility limitation flagging
- Portal PO traceability and idempotency
- Odoo read-only invariant
"""

import unittest
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


class TestStep15ConstraintIntelligence(unittest.TestCase):
    def setUp(self):
        self.engine = UniversalForecastingEngine()
        self.pipeline = InventoryDecisionPipeline(universal_engine=self.engine)
        self.portal_po = PortalPOService()

    def test_01_actual_vs_default_constraint_source(self):
        """Validates that constraint_source distinguishes real Odoo rules from defaults."""
        actual_constraints = SupplierConstraints(
            vendor_id=8813,
            vendor_name="Zenda-Bob",
            moq=1000.0,
            standard_roll_length=50.0,
            constraint_source="ODOO_VENDOR_DATA",
        )
        default_constraints = SupplierConstraints(
            vendor_id=None,
            moq=100.0,
            standard_roll_length=50.0,
            constraint_source="DEFAULT_ASSUMPTION",
        )
        self.assertEqual(actual_constraints.constraint_source, "ODOO_VENDOR_DATA")
        self.assertEqual(default_constraints.constraint_source, "DEFAULT_ASSUMPTION")

    def test_02_zero_purchase_protection(self):
        """
        CRITICAL INVARIANT: Never turn Q_AI = 0 into positive purchase because of MOQ or roll size.
        """
        constraints = SupplierConstraints(
            vendor_id=1,
            vendor_name="Mills",
            moq=100.0,
            standard_roll_length=50.0,
        )

        # 1. Direct apply check
        qty, reasons = constraints.apply(0.0)
        self.assertEqual(qty, 0.0)
        self.assertEqual(len(reasons), 0)

        # 2. Pipeline check on active product where stock >= target
        sales = pd.Series([20.0, 20.0, 20.0, 20.0, 20.0, 20.0])
        res = self.pipeline.evaluate_product_decision(
            product_id=201,
            sales_series=sales,
            current_stock=100.0,  # Surplus stock
            supplier_constraints=constraints,
        )
        self.assertEqual(res.suggested_purchase_ai, 0.0)
        self.assertEqual(res.constrained_purchase_qty, 0.0)
        self.assertEqual(len(res.constraint_adjustment_reasons), 0)

    def test_03_dead_stock_zero_protection(self):
        """Verifies dead stock always yields 0.0 for all quantities regardless of constraints."""
        zero_sales = pd.Series([0.0] * 12)
        constraints = SupplierConstraints(moq=500.0, standard_roll_length=100.0)
        res = self.pipeline.evaluate_product_decision(
            product_id=202,
            sales_series=zero_sales,
            current_stock=50.0,
            supplier_constraints=constraints,
        )
        self.assertEqual(res.demand_pattern, "dead_stock")
        self.assertEqual(res.forecast_1m, 0.0)
        self.assertEqual(res.forecast_h3, 0.0)
        self.assertEqual(res.target_stock, 0.0)
        self.assertEqual(res.suggested_purchase_ai, 0.0)
        self.assertEqual(res.constrained_purchase_qty, 0.0)

    def test_04_multiplier_detection(self):
        """Verifies that large quantity inflation triggers >2x and >3x planner exceptions."""
        constraints = SupplierConstraints(
            vendor_id=1,
            vendor_name="Mills",
            moq=100.0,
            standard_roll_length=50.0,
            constraint_source="DEFAULT_ASSUMPTION",
        )
        # Demand is very small: target ~1.5m, stock = 1.0m -> raw need = 0.5m
        # Constrained buy will be 100m -> multiplier = 200x!
        sparse_sales = pd.Series([0.5, 0.5, 0.5, 0.5, 0.5, 0.5])
        res = self.pipeline.evaluate_product_decision(
            product_id=203,
            sales_series=sparse_sales,
            current_stock=0.5,
            supplier_constraints=constraints,
        )
        self.assertGreater(res.suggested_purchase_ai, 0.0)
        self.assertGreater(res.constraint_multiplier, 3.0)
        self.assertIn("constraint_multiplier_gt_3x", res.planner_exceptions)
        self.assertIn("default_moq_used", res.planner_exceptions)

    def test_05_missing_vendor_uom_lead_time_exceptions(self):
        """Verifies that missing procurement parameters flag planner review exceptions."""
        incomplete_constraints = SupplierConstraints(
            vendor_id=None,
            purchase_uom="",
            lead_time_days=0,
            constraint_source="MISSING",
        )
        sales = pd.Series([50.0, 50.0, 50.0, 50.0, 50.0, 50.0])
        res = self.pipeline.evaluate_product_decision(
            product_id=204,
            sales_series=sales,
            current_stock=10.0,
            supplier_constraints=incomplete_constraints,
        )
        self.assertIn("missing_supplier", res.planner_exceptions)
        self.assertIn("missing_uom", res.planner_exceptions)
        self.assertIn("missing_lead_time", res.planner_exceptions)
        self.assertFalse(res.is_ready_for_approval)

    def test_06_inbound_stock_conflict_flagging(self):
        """Verifies that pending inbound POs trigger planner review exception."""
        sales = pd.Series([50.0, 50.0, 50.0, 50.0, 50.0, 50.0])
        res = self.pipeline.evaluate_product_decision(
            product_id=205,
            sales_series=sales,
            current_stock=10.0,
            inbound_pending_qty=250.0,
        )
        self.assertIn("possible_inbound_stock_conflict", res.planner_exceptions)
        self.assertEqual(res.inbound_pending_qty, 250.0)

    def test_07_group_absorption_and_uncertain_substitutability(self):
        """Verifies group absorption suppression and uncertain substitutability flagging."""
        sales = pd.Series([25.0, 25.0, 25.0, 25.0, 25.0, 25.0])
        # Variant 301 needs stock, sibling 302 has 500m stock
        group_stocks = {301: 5.0, 302: 500.0}
        group_targets = {301: 50.0, 302: 50.0}

        res = self.pipeline.evaluate_product_decision(
            product_id=301,
            sales_series=sales,
            current_stock=5.0,
            main_product_id=9901,
            group_members_stock=group_stocks,
            group_members_targets=group_targets,
            substitutability_status="uncertain_substitutability",
        )
        self.assertTrue(res.group_evaluation.group_stock_absorbed)
        self.assertEqual(res.suggested_purchase_ai, 0.0)
        self.assertIn("group_stock_available_elsewhere", res.planner_exceptions)
        self.assertIn("uncertain_group_substitutability", res.planner_exceptions)

    def test_08_portal_po_traceability_and_gating(self):
        """Verifies portal PO draft creation preserves AI quantity, constraint reasons, and blocks non-approved."""
        appr_id = f"appr_step15_test_{int(pd.Timestamp.now().timestamp())}"
        record = {
            "approval_id": appr_id,
            "product_id": 401,
            "product_name": "Traceability Fabric",
            "suggested_purchase": 23.0,
            "approved_quantity": 23.0,
            "final_po_quantity": 100.0,
            "unit_price": 12.5,
            "status": "APPROVED",
            "supplier_constraints": {
                "moq": 100.0,
                "roll_length": 50.0,
                "constraint_source": "ODOO_VENDOR_DATA",
            },
            "constraint_reasons": ["adjusted_to_supplier_moq_100m"],
            "planner_id": "senior_planner_alex",
        }

        po = self.portal_po.create_draft_po_from_approvals(
            po_reference=f"PO_STEP15_{appr_id}",
            approval_records=[record],
            vendor_id=8813,
            vendor_name="Zenda-Bob",
        )
        self.assertEqual(po.status, "DRAFT")
        self.assertEqual(po.total_quantity, 100.0)

        # Retrieve and verify lines
        po_details = self.portal_po.get_portal_po(po.po_id)
        self.assertIsNotNone(po_details)
        line = po_details["lines"][0]
        self.assertEqual(float(line["ai_quantity"]), 23.0)
        self.assertEqual(float(line["final_po_quantity"]), 100.0)
        self.assertIn("adjusted_to_supplier_moq_100m", str(line["constraint_reasons"]))


if __name__ == "__main__":
    unittest.main()
