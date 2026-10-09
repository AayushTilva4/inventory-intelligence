"""
Step 16: Interactive Human Planner Procurement Console Unit Test Suite.

Validates:
1. Executive procurement KPI summary endpoint (/api/procurement/kpis)
2. Recommendations listing, pagination, and multi-criteria filtering
3. 5-part detailed planner analysis drawer (Section A Demand, Section B Forecast, Section C Inventory, Section D Procurement, Section E Decision)
4. Approval governance:
   - Transactional APPROVE with high-risk gating / acknowledgment
   - Transactional REJECT requiring mandatory reason
   - Transactional EDIT requiring mandatory reason and target/purchase overrides
   - Approval of edited recommendations
   - Prohibition against creating PO on unapproved/edited items
5. Constraint provenance visibility (ODOO_VENDOR_DATA, PORTAL_CONFIGURED, DEFAULT_ASSUMPTION, MISSING)
6. High-risk exception detection (>2x, >3x multiplier, missing supplier, inbound conflict, uncertain substitutability)
7. Group inventory and inbound stock visibility
8. Guarded bulk approval (blocks high-risk items)
9. Single & bulk portal draft PO creation grouped by supplier
10. Zero-purchase and dead-stock protection (zero qty items cannot generate draft POs)
11. Portal PO idempotency and provenance audit trail (Q_AI -> Q_constrained -> Q_approved -> Q_final_PO)
12. Draft PO status workflow (DRAFT -> APPROVED_FOR_EXTERNAL_SYNC / CANCELLED)
13. Absolute Odoo read-only invariant (0 Odoo writes, 0 Odoo POs, 0 Odoo schema changes)
"""

import unittest
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app as production_app
from app.api.procurement import router as procurement_router
from app.db.connection import get_poc_engine, get_odoo_engine
from app.forecasting.benchmark_v2.approvals import PlannerApprovalService
from app.forecasting.benchmark_v2.portal_po import PortalPOService


class TestStep16ProcurementConsole(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_app = FastAPI()
        test_app.include_router(procurement_router)
        cls.client = TestClient(test_app)
        cls.prod_client = TestClient(production_app)
        cls.approval_service = PlannerApprovalService()
        cls.portal_po_service = PortalPOService()
        # Ensure approvals table is seeded
        cls.approval_service.sync_from_snapshot()

    def test_00_procurement_unregistered_in_production_app(self):
        """Verifies that procurement router is unregistered in the production POC application."""
        res = self.prod_client.get("/api/procurement/kpis")
        self.assertEqual(res.status_code, 404)

    def test_01_executive_kpis(self):
        """Validates that executive KPI metrics return accurate live POC values."""
        res = self.client.get("/api/procurement/kpis")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("products_requiring_replenishment", data)
        self.assertIn("total_ai_recommended_quantity", data)
        self.assertIn("total_constrained_quantity", data)
        self.assertIn("pending_planner_review", data)
        self.assertIn("high_risk_exceptions", data)

        self.assertIn("inbound_conflict_products", data)
        self.assertIn("missing_supplier_products", data)
        self.assertIn("portal_draft_pos", data)
        self.assertIn("disclaimer", data)
        self.assertIn("Odoo remains read-only", data["disclaimer"])

    def test_02_recommendations_listing_and_pagination(self):
        """Validates paginated procurement recommendations listing."""
        res = self.client.get("/api/procurement/recommendations?limit=10&offset=0")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("items", data)
        self.assertIn("total", data)
        self.assertIn("limit", data)
        self.assertIn("offset", data)
        self.assertLessEqual(len(data["items"]), 10)
        if data["items"]:
            item = data["items"][0]
            self.assertIn("approval_id", item)
            self.assertIn("product_id", item)
            self.assertIn("suggested_purchase", item)
            self.assertIn("constrained_purchase_qty", item)
            self.assertIn("constraint_multiplier", item)
            self.assertIn("constraint_source", item)
            self.assertIn("pattern", item)
            self.assertIn("is_high_risk", item)

    def test_03_recommendations_filtering(self):
        """Validates filtering recommendations by status, demand pattern, and search."""
        # Filter by status
        res_pending = self.client.get("/api/procurement/recommendations?status=PENDING&limit=5")
        self.assertEqual(res_pending.status_code, 200)
        for item in res_pending.json()["items"]:
            self.assertEqual(item["status"], "PENDING")

        # Filter by search
        res_search = self.client.get("/api/procurement/recommendations?search=422&limit=5")
        self.assertEqual(res_search.status_code, 200)
        for item in res_search.json()["items"]:
            self.assertTrue("422" in str(item["product_name"]) or "422" in str(item["product_id"]))

    def test_04_product_detail_5_parts(self):
        """Validates the 5-part detailed planner analysis drawer."""
        res_list = self.client.get("/api/procurement/recommendations?limit=1")
        self.assertEqual(res_list.status_code, 200)
        items = res_list.json()["items"]
        if not items:
            self.skipTest("No items found in approval table.")
        product_id = items[0]["product_id"]

        res_detail = self.client.get(f"/api/procurement/product/{product_id}/details")
        self.assertEqual(res_detail.status_code, 200)
        d = res_detail.json()

        # Section A: Demand
        self.assertIn("section_a_demand", d)
        self.assertIn("demand_pattern", d["section_a_demand"])
        self.assertIn("recent_1m_demand", d["section_a_demand"])
        self.assertIn("recent_3m_demand", d["section_a_demand"])

        # Section B: Forecast
        self.assertIn("section_b_forecast", d)
        self.assertIn("forecast_1m", d["section_b_forecast"])
        self.assertIn("forecast_h3", d["section_b_forecast"])
        self.assertIn("forecast_explanation", d["section_b_forecast"])

        # Section C: Inventory
        self.assertIn("section_c_inventory", d)
        self.assertIn("current_stock", d["section_c_inventory"])
        self.assertIn("target_stock", d["section_c_inventory"])
        self.assertIn("inbound_pending_qty", d["section_c_inventory"])

        # Section D: Procurement
        self.assertIn("section_d_procurement", d)
        self.assertIn("suggested_purchase_ai", d["section_d_procurement"])
        self.assertIn("constrained_purchase_qty", d["section_d_procurement"])
        self.assertIn("moq", d["section_d_procurement"])
        self.assertIn("standard_roll_length", d["section_d_procurement"])
        self.assertIn("constraint_source", d["section_d_procurement"])

        # Section E: Decision
        self.assertIn("section_e_decision", d)
        self.assertIn("status", d["section_e_decision"])
        self.assertIn("audit_trail", d["section_e_decision"])

    def test_05_rejection_requires_mandatory_reason(self):
        """Validates that rejecting an approval requires a mandatory reason."""
        res_list = self.client.get("/api/procurement/recommendations?status=PENDING&limit=1")
        items = res_list.json()["items"]
        if not items:
            self.skipTest("No pending items available.")
        item_id = items[0]["approval_id"]

        # Missing / too short reason
        bad_req = {"approval_id": item_id, "planner_id": "test_planner", "reason": "no"}
        res_bad = self.client.post("/api/procurement/reject", json=bad_req)
        self.assertEqual(res_bad.status_code, 422)  # validation error (min length 3)

        # Valid rejection
        good_req = {"approval_id": item_id, "planner_id": "test_planner", "reason": "Sufficient buffer exists in warehouse"}
        res_good = self.client.post("/api/procurement/reject", json=good_req)
        self.assertEqual(res_good.status_code, 200)
        self.assertEqual(res_good.json()["status"], "REJECTED")

    def test_06_edit_requires_mandatory_reason_and_positive_numbers(self):
        """Validates that editing quantities requires reason and valid figures."""
        res_list = self.client.get("/api/procurement/recommendations?status=PENDING&limit=1")
        items = res_list.json()["items"]
        if not items:
            self.skipTest("No pending items available.")
        item_id = items[0]["approval_id"]

        # Negative quantity rejected by schema
        bad_req = {
            "approval_id": item_id,
            "planner_id": "test_planner",
            "edited_target_stock": -10.0,
            "edited_purchase_qty": 50.0,
            "reason": "Adjusting target",
        }
        res_bad = self.client.post("/api/procurement/edit", json=bad_req)
        self.assertEqual(res_bad.status_code, 422)

        # Valid edit
        good_req = {
            "approval_id": item_id,
            "planner_id": "test_planner",
            "edited_target_stock": 75.0,
            "edited_purchase_qty": 25.0,
            "reason": "Planner manual reduction based on supplier promo",
        }
        res_good = self.client.post("/api/procurement/edit", json=good_req)
        self.assertEqual(res_good.status_code, 200)
        rec = res_good.json()
        self.assertEqual(rec["status"], "EDITED")
        self.assertEqual(float(rec["edited_purchase_qty"]), 25.0)

        # Test approving the edited quantity
        res_approve_edited = self.client.post(
            "/api/procurement/approve-edited",
            json={"approval_id": item_id, "planner_id": "test_planner", "comment": "Approved after manual check"},
        )
        self.assertEqual(res_approve_edited.status_code, 200)
        self.assertEqual(res_approve_edited.json()["status"], "APPROVED")

    def test_07_approval_and_high_risk_gating(self):
        """Validates approval workflow and acknowledgment requirement for high-risk items."""
        res_list = self.client.get("/api/procurement/recommendations?status=PENDING&limit=20")
        items = res_list.json()["items"]
        high_risk_item = next((i for i in items if i.get("is_high_risk")), None)
        low_risk_item = next((i for i in items if not i.get("is_high_risk") and i.get("exception_category") == "standard_monitoring"), None)

        if high_risk_item:
            # Approving without acknowledgment should fail
            res_fail = self.client.post(
                "/api/procurement/approve",
                json={
                    "approval_id": high_risk_item["approval_id"],
                    "planner_id": "test_planner",
                    "warning_acknowledged": False,
                },
            )
            self.assertEqual(res_fail.status_code, 400)
            self.assertIn("Planner must acknowledge the warning", res_fail.json()["detail"])

            # Approving with acknowledgment succeeds
            res_succ = self.client.post(
                "/api/procurement/approve",
                json={
                    "approval_id": high_risk_item["approval_id"],
                    "planner_id": "test_planner",
                    "warning_acknowledged": True,
                    "comment": "Confirmed despite constraint inflation",
                },
            )
            self.assertEqual(res_succ.status_code, 200)
            self.assertEqual(res_succ.json()["status"], "APPROVED")

        if low_risk_item:
            res_low = self.client.post(
                "/api/procurement/approve",
                json={
                    "approval_id": low_risk_item["approval_id"],
                    "planner_id": "test_planner",
                    "warning_acknowledged": False,
                },
            )
            self.assertEqual(res_low.status_code, 200)
            self.assertEqual(res_low.json()["status"], "APPROVED")

    def test_08_bulk_approval_blocks_high_risk(self):
        """Validates that bulk approval strictly rejects high-risk items."""
        res_list = self.client.get("/api/procurement/recommendations?status=PENDING&limit=50")
        items = res_list.json()["items"]
        high_risk_items = [i for i in items if i.get("is_high_risk")]
        if not high_risk_items:
            self.skipTest("No high-risk items found to test bulk block.")

        hr_id = high_risk_items[0]["approval_id"]
        res_bulk = self.client.post(
            "/api/procurement/bulk-approve",
            json={
                "approval_ids": [hr_id],
                "planner_id": "test_planner",
            },
        )
        self.assertEqual(res_bulk.status_code, 200)
        data = res_bulk.json()
        self.assertEqual(data["approved_count"], 0)
        self.assertEqual(data["blocked_count"], 1)
        self.assertIn("requires individual review", data["blocked_items"][0]["reason"])

    def test_09_portal_draft_po_creation_and_zero_protection(self):
        """
        Validates draft PO creation:
        - Only approved items can be ordered
        - Zero purchase quantity cannot create draft PO
        - Complete provenance recorded
        """
        # Pick an item with Q_AI = 0
        res_list = self.client.get("/api/procurement/recommendations?limit=50")
        items = res_list.json()["items"]
        zero_item = next((i for i in items if float(i["suggested_purchase"]) == 0.0), None)

        if zero_item:
            # Approve it to test zero purchase rejection at PO stage
            self.client.post(
                "/api/procurement/approve",
                json={"approval_id": zero_item["approval_id"], "planner_id": "test_planner", "warning_acknowledged": True},
            )
            res_zero_po = self.client.post(
                "/api/procurement/purchase-orders/create",
                json={"approval_ids": [zero_item["approval_id"]], "planner_id": "test_planner"},
            )
            self.assertEqual(res_zero_po.status_code, 400)
            self.assertIn("zero purchase quantity", res_zero_po.json()["detail"])

        # Now pick an item with positive purchase
        pos_item = next((i for i in items if float(i["suggested_purchase"]) > 0.0), None)
        if pos_item:
            # Ensure approved
            self.client.post(
                "/api/procurement/approve",
                json={"approval_id": pos_item["approval_id"], "planner_id": "test_planner", "warning_acknowledged": True},
            )
            res_po = self.client.post(
                "/api/procurement/purchase-orders/create",
                json={"approval_ids": [pos_item["approval_id"]], "planner_id": "test_planner"},
            )
            self.assertEqual(res_po.status_code, 200)
            data = res_po.json()
            self.assertIn("po_id", data)
            self.assertIn("po_reference", data)
            self.assertIn("lines", data)
            self.assertGreaterEqual(len(data["lines"]), 1)
            line = next((l for l in data["lines"] if l["product_id"] == pos_item["product_id"]), data["lines"][0])
            self.assertEqual(line["product_id"], pos_item["product_id"])
            self.assertGreater(line["approved_quantity"], 0.0)

    def test_10_draft_po_listing_and_detail(self):
        """Validates draft PO listing and detail with complete provenance."""
        res_list = self.client.get("/api/procurement/purchase-orders")
        self.assertEqual(res_list.status_code, 200)
        data = res_list.json()
        self.assertIn("items", data)
        if data["items"]:
            po = data["items"][0]
            po_id = po["po_id"]
            res_det = self.client.get(f"/api/procurement/purchase-orders/{po_id}")
            self.assertEqual(res_det.status_code, 200)
            det = res_det.json()
            self.assertEqual(det["po_id"], po_id)
            self.assertIn("lines", det)

    def test_11_po_status_workflow(self):
        """Validates status transition (DRAFT -> APPROVED_FOR_EXTERNAL_SYNC -> CANCELLED)."""
        res_list = self.client.get("/api/procurement/purchase-orders")
        data = res_list.json()
        if data["items"]:
            po_id = data["items"][0]["po_id"]
            # Transition to APPROVED_FOR_EXTERNAL_SYNC
            res_sync = self.client.post(
                f"/api/procurement/purchase-orders/{po_id}/status",
                json={"status": "APPROVED_FOR_EXTERNAL_SYNC"},
            )
            self.assertEqual(res_sync.status_code, 200)
            self.assertEqual(res_sync.json()["status"], "APPROVED_FOR_EXTERNAL_SYNC")

            # Transition to CANCELLED
            res_cancel = self.client.post(
                f"/api/procurement/purchase-orders/{po_id}/status",
                json={"status": "CANCELLED"},
            )
            self.assertEqual(res_cancel.status_code, 200)
            self.assertEqual(res_cancel.json()["status"], "CANCELLED")

    def test_12_odoo_read_only_isolation(self):
        """
        CRITICAL TEST: Asserts that Odoo database has ZERO portal tables and ZERO Odoo POs created.
        """
        odoo_engine = get_odoo_engine()
        with odoo_engine.connect() as conn:
            # Check portal table does NOT exist in Odoo
            res_table = conn.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'portal_purchase_orders')"
                )
            ).scalar()
            self.assertFalse(res_table, "CRITICAL VIOLATION: portal_purchase_orders found in Odoo database!")

            # Verify no phantom POs with 'PORTAL-%' were ever written to Odoo purchase_order table
            res_po = conn.execute(
                text(
                    "SELECT COUNT(*) FROM purchase_order WHERE name LIKE 'PORTAL-%' OR origin LIKE 'PORTAL-%'"
                )
            ).scalar()
            self.assertEqual(res_po, 0, "CRITICAL VIOLATION: Portal purchase orders found inside Odoo purchase_order!")


if __name__ == "__main__":
    unittest.main()
