"""
Portal-Side Purchase Order Data Model for Step 12 Task 16.

IMPORTANT ARCHITECTURAL CONSTRAINTS:
1. STRICTLY POC-DATABASE ISOLATED: Operates exclusively on the POC PostgreSQL database.
2. ZERO ODOO WRITES: Absolutely no writes, schema changes, or PO creations in Odoo.
3. GOVERNANCE BRIDGE: Bridges approved planner decisions into structured portal-side draft POs.
4. VALID STATUSES:
   - DRAFT: Initial draft purchase order created within Inventory Intelligence portal.
   - CANCELLED: Voided or discarded by inventory planner prior to any external export.
   - APPROVED_FOR_EXTERNAL_SYNC: Marked by senior governance as finalized for future external processing.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from dataclasses import asdict, dataclass
import pandas as pd
from sqlalchemy import text, Engine

from app.db.connection import get_poc_engine


ALLOWED_PO_STATUSES = [
    "DRAFT",
    "CANCELLED",
    "APPROVED_FOR_EXTERNAL_SYNC",
]


@dataclass(frozen=True)
class PortalPOLineRecord:
    """Represents a single line item on a portal-side draft purchase order."""
    line_id: int | None
    po_id: str
    approval_id: str | None
    product_id: int
    product_name: str
    vendor_id: int | None
    vendor_name: str | None
    approved_quantity: float
    unit_price: float
    subtotal: float
    forecast_snapshot_id: str | None
    forecast_1m: float
    forecast_h3: float
    target_stock: float
    current_stock: float
    planner_decision: str
    status: str
    notes: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PortalPORecord:
    """Represents a portal-side draft purchase order."""
    po_id: str
    po_reference: str
    vendor_id: int | None
    vendor_name: str | None
    status: str
    total_quantity: float
    total_amount: float
    created_by: str
    created_at: str
    updated_at: str
    notes: str | None
    lines: list[PortalPOLineRecord]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["lines"] = [line.to_dict() for line in self.lines]
        return d


class PortalPOService:
    """
    Manages portal-side draft purchase orders and line items.
    Strictly isolated from Odoo with zero write integration.
    """

    def __init__(self, db_engine: Engine | None = None):
        self.db_engine = db_engine or get_poc_engine()
        self.init_po_tables()

    def init_po_tables(self) -> None:
        """Initializes portal-side PO tables in POC PostgreSQL database."""
        ddl = """
        CREATE TABLE IF NOT EXISTS portal_purchase_orders (
            po_id VARCHAR(64) PRIMARY KEY,
            po_reference VARCHAR(64) UNIQUE NOT NULL,
            vendor_id INT,
            vendor_name VARCHAR(255),
            status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
            total_quantity NUMERIC(14, 2) NOT NULL DEFAULT 0.0,
            total_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.0,
            created_by VARCHAR(64) NOT NULL DEFAULT 'inventory_planner',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            metadata JSONB,
            CONSTRAINT chk_portal_po_status CHECK (status IN ('DRAFT', 'CANCELLED', 'APPROVED_FOR_EXTERNAL_SYNC')),
            CONSTRAINT chk_portal_po_qty_non_neg CHECK (total_quantity >= 0),
            CONSTRAINT chk_portal_po_amt_non_neg CHECK (total_amount >= 0)
        );

        CREATE TABLE IF NOT EXISTS portal_purchase_order_lines (
            line_id SERIAL PRIMARY KEY,
            po_id VARCHAR(64) NOT NULL REFERENCES portal_purchase_orders(po_id) ON DELETE CASCADE,
            approval_id VARCHAR(128),
            product_id INT NOT NULL,
            product_name VARCHAR(255),
            vendor_id INT,
            vendor_name VARCHAR(255),
            approved_quantity NUMERIC(12, 2) NOT NULL,
            unit_price NUMERIC(12, 2) NOT NULL DEFAULT 0.0,
            subtotal NUMERIC(14, 2) NOT NULL DEFAULT 0.0,
            forecast_snapshot_id VARCHAR(64),
            forecast_1m NUMERIC(12, 2) NOT NULL DEFAULT 0.0,
            forecast_h3 NUMERIC(12, 2) NOT NULL DEFAULT 0.0,
            target_stock NUMERIC(12, 2) NOT NULL DEFAULT 0.0,
            current_stock NUMERIC(12, 2) NOT NULL DEFAULT 0.0,
            planner_decision VARCHAR(32) NOT NULL DEFAULT 'APPROVED',
            status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT chk_portal_line_qty_positive CHECK (approved_quantity >= 0),
            CONSTRAINT chk_portal_line_status CHECK (status IN ('DRAFT', 'CANCELLED', 'APPROVED_FOR_EXTERNAL_SYNC'))
        );

        CREATE INDEX IF NOT EXISTS idx_portal_po_status ON portal_purchase_orders(status);
        CREATE INDEX IF NOT EXISTS idx_portal_po_lines_po_id ON portal_purchase_order_lines(po_id);
        CREATE INDEX IF NOT EXISTS idx_portal_lines_product ON portal_purchase_order_lines(product_id);
        CREATE INDEX IF NOT EXISTS idx_portal_lines_approval ON portal_purchase_order_lines(approval_id);

        -- Step 14 Schema Enhancements
        ALTER TABLE portal_purchase_order_lines ADD COLUMN IF NOT EXISTS ai_quantity NUMERIC(12, 2) DEFAULT 0.0;
        ALTER TABLE portal_purchase_order_lines ADD COLUMN IF NOT EXISTS final_po_quantity NUMERIC(12, 2) DEFAULT 0.0;
        ALTER TABLE portal_purchase_order_lines ADD COLUMN IF NOT EXISTS supplier_constraints JSONB;
        ALTER TABLE portal_purchase_order_lines ADD COLUMN IF NOT EXISTS constraint_reasons JSONB;
        ALTER TABLE portal_purchase_order_lines ADD COLUMN IF NOT EXISTS planner_id VARCHAR(64);

        CREATE UNIQUE INDEX IF NOT EXISTS idx_portal_line_active_approval 
        ON portal_purchase_order_lines (approval_id) 
        WHERE status != 'CANCELLED' AND approval_id IS NOT NULL;
        """
        try:
            with self.db_engine.begin() as conn:
                conn.execute(text(ddl))
        except Exception as e:
            print(f"[PortalPOService] Warning: PO tables DDL skipped: {e}")

    def create_draft_po_from_approvals(
        self,
        po_reference: str,
        approval_records: Sequence[Mapping[str, Any]],
        vendor_id: int | None = None,
        vendor_name: str | None = None,
        created_by: str = "inventory_planner",
        notes: str | None = None,
    ) -> PortalPORecord:
        """
        Creates a portal-side draft purchase order from approved planner decisions.
        Enforces Step 14 invariants:
        - Eligibility: PENDING, EDITED, REJECTED, CANCELLED are BLOCKED. Only APPROVED is eligible.
        - Quantities: Distinguishes ai_quantity, approved_quantity, final_po_quantity.
        - Idempotency: Returns existing draft PO if approval_id already exists in an active PO.
        - Exception Governance: Blocks if unresolved mandatory exceptions are flagged.
        - Zero interactions with Odoo.
        """
        if not po_reference or not po_reference.strip():
            raise ValueError("po_reference cannot be empty.")
        if not approval_records:
            raise ValueError("Cannot create purchase order with zero lines.")

        # 1. Eligibility Check
        for rec in approval_records:
            status = str(rec.get("status", "APPROVED")).upper()
            appr_id = rec.get("approval_id", "unknown")
            pid = rec.get("product_id", "unknown")
            if status != "APPROVED":
                raise ValueError(
                    f"Eligibility violation: Approval record '{appr_id}' for product {pid} "
                    f"has status '{status}'. Only APPROVED decisions can create portal draft POs."
                )
            if rec.get("has_unresolved_exceptions"):
                exc_reason = rec.get("unresolved_exception_reason", "Unresolved mandatory procurement exception")
                raise ValueError(f"Exception governance violation for product {pid}: {exc_reason}")

        # 2. Idempotency Check
        appr_ids = [str(rec["approval_id"]) for rec in approval_records if rec.get("approval_id")]
        if appr_ids:
            with self.db_engine.connect() as conn:
                check_q = text("""
                    SELECT po_id, approval_id 
                    FROM portal_purchase_order_lines 
                    WHERE approval_id = ANY(:appr_ids) AND status != 'CANCELLED'
                """)
                existing_matches = conn.execute(check_q, {"appr_ids": appr_ids}).mappings().fetchall()
                if existing_matches:
                    existing_po_ids = list({row["po_id"] for row in existing_matches})
                    # If all requested approvals belong to the exact same existing active PO, return that existing PO idempotently
                    if len(existing_po_ids) == 1 and len(existing_matches) == len(appr_ids):
                        existing_po = self.get_portal_po(existing_po_ids[0])
                        if existing_po is not None:
                            lines = [
                                PortalPOLineRecord(
                                    line_id=l["line_id"],
                                    po_id=l["po_id"],
                                    approval_id=l["approval_id"],
                                    product_id=l["product_id"],
                                    product_name=l["product_name"],
                                    vendor_id=l["vendor_id"],
                                    vendor_name=l["vendor_name"],
                                    approved_quantity=float(l["approved_quantity"]),
                                    unit_price=float(l["unit_price"]),
                                    subtotal=float(l["subtotal"]),
                                    forecast_snapshot_id=l["forecast_snapshot_id"],
                                    forecast_1m=float(l["forecast_1m"]),
                                    forecast_h3=float(l["forecast_h3"]),
                                    target_stock=float(l["target_stock"]),
                                    current_stock=float(l["current_stock"]),
                                    planner_decision=l["planner_decision"],
                                    status=l["status"],
                                    notes=l["notes"],
                                )
                                for l in existing_po["lines"]
                            ]
                            return PortalPORecord(
                                po_id=existing_po["po_id"],
                                po_reference=existing_po["po_reference"],
                                vendor_id=existing_po["vendor_id"],
                                vendor_name=existing_po["vendor_name"],
                                status=existing_po["status"],
                                total_quantity=float(existing_po["total_quantity"]),
                                total_amount=float(existing_po["total_amount"]),
                                created_by=existing_po["created_by"],
                                created_at=str(existing_po["created_at"]),
                                updated_at=str(existing_po["updated_at"]),
                                notes=existing_po["notes"],
                                lines=lines,
                            )
                    # Otherwise, partial conflict
                    raise ValueError(
                        f"Idempotency violation: Approvals {[r['approval_id'] for r in existing_matches]} "
                        f"are already attached to active PO(s): {existing_po_ids}"
                    )

        now_iso = datetime.now(timezone.utc).isoformat()
        po_id = f"po_{int(datetime.now(timezone.utc).timestamp())}_{po_reference.replace(' ', '_').lower()}"

        total_qty = 0.0
        total_amt = 0.0
        lines: list[PortalPOLineRecord] = []
        raw_lines_data: list[dict[str, Any]] = []

        for rec in approval_records:
            pid = int(rec["product_id"])
            pname = str(rec.get("product_name") or f"Product {pid}")
            pattern = str(rec.get("pattern", "normal"))
            
            # AI recommendation
            ai_qty = float(rec.get("suggested_purchase", rec.get("ai_quantity", 0.0)))
            
            # Planner approved quantity (if edited, use edited_purchase_qty)
            if rec.get("edited_purchase_qty") is not None:
                approved_qty = float(rec["edited_purchase_qty"])
            else:
                approved_qty = float(rec.get("approved_quantity", ai_qty))
                
            # Final PO quantity after supplier constraints
            final_po_qty = float(rec.get("final_po_quantity", rec.get("constrained_purchase_qty", approved_qty)))

            # Safety invariants
            if final_po_qty < 0:
                raise ValueError(f"Negative purchase quantity ({final_po_qty}) not permitted for product {pid}.")
            if (pattern in ("dead_stock", "service_excluded") or rec.get("product_type") in ("service", "consu")) and final_po_qty > 0:
                raise ValueError(f"{pattern or 'Service'} safety violation: Product {pid} cannot have positive purchase quantity.")

            unit_price = float(rec.get("unit_price", 0.0))
            subtotal = round(final_po_qty * unit_price, 2)
            total_qty += final_po_qty
            total_amt += subtotal

            supplier_constraints = rec.get("supplier_constraints")
            constraint_reasons = rec.get("constraint_reasons")
            planner_id = rec.get("planner_id", created_by)

            lines.append(
                PortalPOLineRecord(
                    line_id=None,
                    po_id=po_id,
                    approval_id=str(rec.get("approval_id")) if rec.get("approval_id") else None,
                    product_id=pid,
                    product_name=pname,
                    vendor_id=vendor_id,
                    vendor_name=vendor_name,
                    approved_quantity=approved_qty,
                    unit_price=unit_price,
                    subtotal=subtotal,
                    forecast_snapshot_id=str(rec.get("snapshot_id", "")),
                    forecast_1m=float(rec.get("forecast_1m", 0.0)),
                    forecast_h3=float(rec.get("forecast_h3", 0.0)),
                    target_stock=float(rec.get("target_stock", 0.0)),
                    current_stock=float(rec.get("current_stock", 0.0)),
                    planner_decision=str(rec.get("status", "APPROVED")),
                    status="DRAFT",
                    notes=str(rec.get("planner_comment", "")) or None,
                )
            )

            raw_lines_data.append({
                "po_id": po_id,
                "approval_id": str(rec.get("approval_id")) if rec.get("approval_id") else None,
                "product_id": pid,
                "product_name": pname,
                "vendor_id": vendor_id,
                "vendor_name": vendor_name,
                "approved_quantity": approved_qty,
                "unit_price": unit_price,
                "subtotal": subtotal,
                "forecast_snapshot_id": str(rec.get("snapshot_id", "")),
                "forecast_1m": float(rec.get("forecast_1m", 0.0)),
                "forecast_h3": float(rec.get("forecast_h3", 0.0)),
                "target_stock": float(rec.get("target_stock", 0.0)),
                "current_stock": float(rec.get("current_stock", 0.0)),
                "planner_decision": str(rec.get("status", "APPROVED")),
                "status": "DRAFT",
                "notes": str(rec.get("planner_comment", "")) or None,
                "ai_quantity": ai_qty,
                "final_po_quantity": final_po_qty,
                "supplier_constraints": json.dumps(supplier_constraints) if supplier_constraints else None,
                "constraint_reasons": json.dumps(constraint_reasons) if constraint_reasons else None,
                "planner_id": planner_id,
            })

        total_qty = round(total_qty, 2)
        total_amt = round(total_amt, 2)

        # Persist to POC PostgreSQL database
        insert_po_query = """
        INSERT INTO portal_purchase_orders (
            po_id, po_reference, vendor_id, vendor_name, status,
            total_quantity, total_amount, created_by, created_at, updated_at, notes
        ) VALUES (
            :po_id, :po_reference, :vendor_id, :vendor_name, 'DRAFT',
            :total_quantity, :total_amount, :created_by, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :notes
        ) ON CONFLICT (po_id) DO UPDATE SET
            total_quantity = EXCLUDED.total_quantity,
            total_amount = EXCLUDED.total_amount,
            updated_at = CURRENT_TIMESTAMP;
        """

        insert_line_query = """
        INSERT INTO portal_purchase_order_lines (
            po_id, approval_id, product_id, product_name, vendor_id, vendor_name,
            approved_quantity, unit_price, subtotal, forecast_snapshot_id,
            forecast_1m, forecast_h3, target_stock, current_stock,
            planner_decision, status, notes,
            ai_quantity, final_po_quantity, supplier_constraints, constraint_reasons, planner_id
        ) VALUES (
            :po_id, :approval_id, :product_id, :product_name, :vendor_id, :vendor_name,
            :approved_quantity, :unit_price, :subtotal, :forecast_snapshot_id,
            :forecast_1m, :forecast_h3, :target_stock, :current_stock,
            :planner_decision, :status, :notes,
            :ai_quantity, :final_po_quantity, :supplier_constraints, :constraint_reasons, :planner_id
        );
        """

        with self.db_engine.begin() as conn:
            conn.execute(
                text(insert_po_query),
                {
                    "po_id": po_id,
                    "po_reference": po_reference,
                    "vendor_id": vendor_id,
                    "vendor_name": vendor_name,
                    "total_quantity": total_qty,
                    "total_amount": total_amt,
                    "created_by": created_by,
                    "notes": notes,
                },
            )
            for line_data in raw_lines_data:
                conn.execute(text(insert_line_query), line_data)

        return PortalPORecord(
            po_id=po_id,
            po_reference=po_reference,
            vendor_id=vendor_id,
            vendor_name=vendor_name,
            status="DRAFT",
            total_quantity=total_qty,
            total_amount=total_amt,
            created_by=created_by,
            created_at=now_iso,
            updated_at=now_iso,
            notes=notes,
            lines=lines,
        )

    def update_po_status(
        self,
        po_id: str,
        new_status: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Updates status of a portal PO (DRAFT, CANCELLED, APPROVED_FOR_EXTERNAL_SYNC)."""
        if new_status not in ALLOWED_PO_STATUSES:
            raise ValueError(f"Invalid PO status '{new_status}'. Allowed: {ALLOWED_PO_STATUSES}")

        update_query = """
        UPDATE portal_purchase_orders
        SET status = :status,
            updated_at = CURRENT_TIMESTAMP,
            notes = COALESCE(:notes, notes)
        WHERE po_id = :po_id
        RETURNING po_id, po_reference, status;
        """
        update_lines_query = """
        UPDATE portal_purchase_order_lines
        SET status = :status
        WHERE po_id = :po_id;
        """

        with self.db_engine.begin() as conn:
            res = conn.execute(text(update_query), {"po_id": po_id, "status": new_status, "notes": notes}).mappings().first()
            if not res:
                raise KeyError(f"Portal PO '{po_id}' not found.")
            conn.execute(text(update_lines_query), {"po_id": po_id, "status": new_status})

        return dict(res)

    def get_portal_po(self, po_id: str) -> dict[str, Any] | None:
        """Fetches a portal PO and its lines from POC database."""
        po_query = "SELECT * FROM portal_purchase_orders WHERE po_id = :po_id;"
        lines_query = "SELECT * FROM portal_purchase_order_lines WHERE po_id = :po_id ORDER BY line_id ASC;"

        with self.db_engine.connect() as conn:
            po_row = conn.execute(text(po_query), {"po_id": po_id}).mappings().first()
            if not po_row:
                return None
            lines_rows = conn.execute(text(lines_query), {"po_id": po_id}).mappings().fetchall()

        res = dict(po_row)
        res["lines"] = [dict(r) for r in lines_rows]
        return res
