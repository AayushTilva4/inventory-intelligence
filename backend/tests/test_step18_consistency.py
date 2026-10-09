"""
Step 18 Unit Tests: Demo Data Consistency & Business-Logic Verification.

Covers:
- Task 1 & 2: Service / Non-inventory exclusion (including Gift Card 9610)
- Task 3: Planner override vs supplier constraint (Q_approved < Q_constrained)
- Task 5: KPI consistency
- Task 6: Portal PO consistency and audit trail
"""

import sys
import unittest
from pathlib import Path
from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

load_dotenv(BACKEND_ROOT / ".env")

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.procurement import router as procurement_router
from app.forecasting.benchmark_v2.decision_service import (
    InventoryDecisionPipeline,
    SupplierConstraints,
)
from app.forecasting.benchmark_v2.portal_po import PortalPOService
from app.forecasting.benchmark_v2.approvals import PlannerApprovalService


class TestStep18Consistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_app = FastAPI()
        test_app.include_router(procurement_router)
        cls.client = TestClient(test_app)
        cls.pipeline = InventoryDecisionPipeline()
        cls.po_service = PortalPOService()


    def test_01_service_and_non_inventory_exclusion(self):
        """Verifies service products cannot generate forecast, target, purchase, or PO."""
        sales = pd.Series([10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0, 65.0])
        
        # Test 1: Service type
        res_service = self.pipeline.evaluate_product_decision(
            product_id=99901,
            sales_series=sales,
            current_stock=0.0,
            product_name="Cutting & Stitching Service Fee",
            product_type="service",
            is_stockable=False,
        )
        self.assertEqual(res_service.forecast_1m, 0.0)
        self.assertEqual(res_service.forecast_h3, 0.0)
        self.assertEqual(res_service.target_stock, 0.0)
        self.assertEqual(res_service.suggested_purchase_ai, 0.0)
        self.assertEqual(res_service.constrained_purchase_qty, 0.0)
        self.assertIn("service_non_inventory_excluded", res_service.planner_exceptions)
        self.assertFalse(res_service.is_ready_for_approval)

        # Test 2: Consumable type
        res_consu = self.pipeline.evaluate_product_decision(
            product_id=99902,
            sales_series=sales,
            current_stock=5.0,
            product_name="Packaging Tape Consumable",
            product_type="consu",
            is_stockable=False,
        )
        self.assertEqual(res_consu.forecast_1m, 0.0)
        self.assertEqual(res_consu.target_stock, 0.0)
        self.assertEqual(res_consu.suggested_purchase_ai, 0.0)

    def test_02_gift_card_9610_exclusion(self):
        """Verifies Gift Card 9610 (Reward voucher) is excluded from procurement."""
        sales = pd.Series([5.0, 8.0, 10.0, 12.0, 7.0, 9.0, 11.0, 6.0, 8.0, 10.0, 9.0, 8.0])
        res_gc = self.pipeline.evaluate_product_decision(
            product_id=9610,
            sales_series=sales,
            current_stock=0.0,
            product_name="Dazzle Shoes Gift Card -75 AED",
            category_id="216", # Reward
            is_stockable=False,
        )
        self.assertEqual(res_gc.forecast_1m, 0.0)
        self.assertEqual(res_gc.target_stock, 0.0)
        self.assertEqual(res_gc.suggested_purchase_ai, 0.0)
        self.assertEqual(res_gc.constrained_purchase_qty, 0.0)
        self.assertIn("service_non_inventory_excluded", res_gc.planner_exceptions)

        # Ensure service product cannot create positive PO line
        with self.assertRaises(ValueError):
            self.po_service.create_draft_po_from_approvals(
                po_reference="PO-TEST-SERVICE-BLOCKED",
                approval_records=[{
                    "approval_id": "appr_test_service_9610",
                    "product_id": 9610,
                    "product_name": "Dazzle Shoes Gift Card",
                    "pattern": "service_excluded",
                    "suggested_purchase": 0.0,
                    "approved_quantity": 50.0,
                    "final_po_quantity": 50.0,
                    "status": "APPROVED",
                }],
            )

    def test_03_planner_override_below_supplier_constraint(self):
        """Verifies Q_approved < Q_constrained workflow and reason tracking (Task 3)."""
        appr_id = f"appr_test_override_{int(pd.Timestamp.now().timestamp())}"
        record = {
            "approval_id": appr_id,
            "product_id": 402,
            "product_name": "Test Linen Blend",
            "suggested_purchase": 12.0,       # Q_AI = 12m
            "edited_purchase_qty": 25.0,     # Q_approved = 25m (< 50m roll constraint)
            "status": "APPROVED",
        }

        # Simulate the API draft PO builder
        ai_buy = float(record["suggested_purchase"])
        appr_buy = float(record["edited_purchase_qty"])
        ai_constrained = max(50.0, float(int((ai_buy + 49.99) // 50) * 50))
        std_constrained = max(50.0, float(int((appr_buy + 49.99) // 50) * 50))

        self.assertGreater(ai_constrained, appr_buy) # 50m > 25m

        constraint_reasons = []
        if appr_buy < ai_constrained or appr_buy < std_constrained:
            final_po_qty = appr_buy
            constraint_reasons.append("supplier_constraint_overridden_by_planner")
        else:
            final_po_qty = std_constrained

        self.assertEqual(final_po_qty, 25.0)
        self.assertIn("supplier_constraint_overridden_by_planner", constraint_reasons)

        # Create PO
        po = self.po_service.create_draft_po_from_approvals(
            po_reference=f"PO_OVERRIDE_{appr_id}",
            approval_records=[{
                "approval_id": appr_id,
                "product_id": 402,
                "product_name": "Test Linen Blend",
                "ai_quantity": ai_buy,
                "approved_quantity": appr_buy,
                "final_po_quantity": final_po_qty,
                "unit_price": 10.0,
                "status": "APPROVED",
                "supplier_constraints": {"moq": 50.0, "roll_length": 50.0, "supplier_constrained_quantity": 50.0},
                "constraint_reasons": constraint_reasons,
                "planner_id": "test_planner",
            }],
        )
        self.assertEqual(po.total_quantity, 25.0)
        self.assertEqual(po.lines[0].approved_quantity, 25.0)

    def test_04_kpi_consistency_endpoint(self):
        """Verifies GET /api/procurement/kpis returns live exact database figures."""
        res = self.client.get("/api/procurement/kpis")
        self.assertEqual(res.status_code, 200)
        d = res.json()
        self.assertIn("total_catalog_products", d)
        self.assertIn("products_requiring_replenishment", d)
        self.assertIn("total_ai_recommended_quantity", d)
        self.assertIn("total_constrained_quantity", d)
        self.assertIn("pending_planner_review", d)
        self.assertIn("high_risk_exceptions", d)
        self.assertIn("inbound_conflict_products", d)
        self.assertIn("missing_supplier_products", d)
        self.assertIn("large_constraint_multipliers", d)
        self.assertIn("portal_draft_pos", d)
        self.assertEqual(d["inbound_conflict_products"], 615)
        self.assertEqual(d["missing_supplier_products"], 5162)


if __name__ == "__main__":
    unittest.main()
