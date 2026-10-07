"""
Human Planner Approval Governance Module for Step 11.

Provides:
- Data model for planner decisions stored exclusively in POC PostgreSQL database.
- State transitions: PENDING, APPROVED, REJECTED, EDITED, CANCELLED.
- Strict safety validation (non-negative, dead-stock protection, mandatory reasons).
- Complete immutable audit trails (AI recommendations never silently overwritten).
- Strictly isolated governance with ZERO Odoo writes and ZERO PO creation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from dataclasses import asdict, dataclass
import pandas as pd
from sqlalchemy import text, Engine

from app.db.connection import get_poc_engine


ALLOWED_APPROVAL_STATUSES = [
    "PENDING",
    "APPROVED",
    "REJECTED",
    "EDITED",
    "CANCELLED",
]

RISKY_EXCEPTION_CATEGORIES = [
    "rising_product_risk",
    "intermittent_uncertainty",
    "batch_moq_constraint_required",
    "unusually_large_forecast_change",
    "major_target_reduction",
    "major_target_increase",
]


class PlannerApprovalService:
    """
    Manages human planner governance, approvals, overrides, and audit trails.
    Operates strictly on the separate POC PostgreSQL database.
    """

    def __init__(self, db_engine: Engine | None = None):
        self.db_engine = db_engine or get_poc_engine()
        self.init_approval_tables()

    def init_approval_tables(self) -> None:
        """Initializes approval and audit tables in POC PostgreSQL database."""
        ddl = """
        CREATE TABLE IF NOT EXISTS planner_approvals (
            approval_id VARCHAR(128) PRIMARY KEY,
            snapshot_id VARCHAR(64) NOT NULL,
            product_id INT NOT NULL,
            product_name VARCHAR(255),
            pattern VARCHAR(50) NOT NULL,
            forecast_1m NUMERIC(12, 2) NOT NULL,
            forecast_h3 NUMERIC(12, 2) NOT NULL,
            safety_buffer NUMERIC(12, 2) NOT NULL,
            service_level NUMERIC(5, 2) NOT NULL,
            target_stock NUMERIC(12, 2) NOT NULL,
            current_stock NUMERIC(12, 2) NOT NULL,
            suggested_purchase NUMERIC(12, 2) NOT NULL,
            legacy_target NUMERIC(12, 2),
            target_delta NUMERIC(12, 2),
            exception_category VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
            planner_comment TEXT,
            edited_target_stock NUMERIC(12, 2),
            edited_purchase_qty NUMERIC(12, 2),
            planner_id VARCHAR(64),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP WITH TIME ZONE,
            audit_metadata JSONB,
            CONSTRAINT chk_approval_status CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'EDITED', 'CANCELLED')),
            CONSTRAINT chk_target_non_negative CHECK (target_stock >= 0),
            CONSTRAINT chk_purchase_non_negative CHECK (suggested_purchase >= 0)
        );

        CREATE TABLE IF NOT EXISTS planner_approval_audit_trail (
            id SERIAL PRIMARY KEY,
            approval_id VARCHAR(128) NOT NULL REFERENCES planner_approvals(approval_id) ON DELETE CASCADE,
            action VARCHAR(32) NOT NULL,
            previous_status VARCHAR(32),
            new_status VARCHAR(32) NOT NULL,
            original_values JSONB NOT NULL,
            edited_values JSONB,
            planner_id VARCHAR(64) NOT NULL,
            reason_or_comment TEXT,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_approval_snapshot ON planner_approvals(snapshot_id);
        CREATE INDEX IF NOT EXISTS idx_approval_status ON planner_approvals(status);
        CREATE INDEX IF NOT EXISTS idx_approval_product ON planner_approvals(product_id);
        CREATE INDEX IF NOT EXISTS idx_approval_exc ON planner_approvals(exception_category);
        CREATE INDEX IF NOT EXISTS idx_approval_audit_id ON planner_approval_audit_trail(approval_id);
        """
        try:
            with self.db_engine.begin() as conn:
                conn.execute(text(ddl))
        except Exception as exc:
            print(f"[PlannerApprovalService] Notice: DB initialization skipped: {exc}")

    def sync_from_snapshot(self, snapshot_id: str | None = None) -> int:
        """
        Populates planner_approvals from shadow_product_comparisons for a given snapshot.
        If snapshot_id is not specified, uses the latest snapshot.
        Only inserts items that do not already have an approval record.
        """
        with self.db_engine.begin() as conn:
            if not snapshot_id:
                latest_q = text("SELECT snapshot_id FROM shadow_snapshots ORDER BY created_at DESC LIMIT 1")
                snapshot_id = conn.execute(latest_q).scalar()
                if not snapshot_id:
                    return 0

            # Find comparisons for this snapshot that are not yet in planner_approvals
            select_q = text("""
                SELECT c.snapshot_id, c.product_id, c.product_name, c.pattern,
                       c.forecast_1m, c.forecast_h3, c.safety_buffer, c.service_level_target,
                       c.target_stock, c.current_stock, c.suggested_purchase,
                       c.legacy_reorder_target, c.target_delta, c.primary_exception,
                       c.reason_for_difference, c.risk_classification
                FROM shadow_product_comparisons c
                LEFT JOIN planner_approvals a
                  ON a.approval_id = ('appr_' || c.snapshot_id || '_' || CAST(c.product_id AS TEXT))
                WHERE c.snapshot_id = :snapshot_id AND a.approval_id IS NULL
            """)
            rows = conn.execute(select_q, {"snapshot_id": snapshot_id}).mappings().all()
            if not rows:
                return 0

            inserted_count = 0
            for r in rows:
                appr_id = f"appr_{r['snapshot_id']}_{r['product_id']}"
                meta = {
                    "reason_for_difference": r["reason_for_difference"],
                    "risk_classification": r["risk_classification"],
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                }
                insert_q = text("""
                    INSERT INTO planner_approvals (
                        approval_id, snapshot_id, product_id, product_name, pattern,
                        forecast_1m, forecast_h3, safety_buffer, service_level,
                        target_stock, current_stock, suggested_purchase,
                        legacy_target, target_delta, exception_category,
                        status, audit_metadata
                    ) VALUES (
                        :appr_id, :snap_id, :pid, :pname, :pattern,
                        :fc_1m, :fc_h3, :buf, :sl,
                        :tgt, :cur, :buy,
                        :leg_tgt, :delta, :exc,
                        'PENDING', :meta
                    ) ON CONFLICT (approval_id) DO NOTHING
                """)
                conn.execute(insert_q, {
                    "appr_id": appr_id,
                    "snap_id": r["snapshot_id"],
                    "pid": r["product_id"],
                    "pname": r["product_name"],
                    "pattern": r["pattern"],
                    "fc_1m": r["forecast_1m"],
                    "fc_h3": r["forecast_h3"],
                    "buf": r["safety_buffer"],
                    "sl": r["service_level_target"],
                    "tgt": r["target_stock"],
                    "cur": r["current_stock"],
                    "buy": r["suggested_purchase"],
                    "leg_tgt": r["legacy_reorder_target"],
                    "delta": r["target_delta"],
                    "exc": r["primary_exception"],
                    "meta": json.dumps(meta),
                })

                # Initial audit record
                orig_vals = {
                    "forecast_1m": float(r["forecast_1m"]),
                    "forecast_h3": float(r["forecast_h3"]),
                    "target_stock": float(r["target_stock"]),
                    "suggested_purchase": float(r["suggested_purchase"]),
                    "pattern": r["pattern"],
                }
                audit_q = text("""
                    INSERT INTO planner_approval_audit_trail (
                        approval_id, action, previous_status, new_status,
                        original_values, planner_id, reason_or_comment
                    ) VALUES (
                        :appr_id, 'CREATED', NULL, 'PENDING',
                        :orig_vals, 'system_canary_shadow', 'Created pending recommendation from canary snapshot'
                    )
                """)
                conn.execute(audit_q, {
                    "appr_id": appr_id,
                    "orig_vals": json.dumps(orig_vals),
                })
                inserted_count += 1

            return inserted_count

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        """Retrieves a single approval record with its full audit trail."""
        with self.db_engine.connect() as conn:
            q = text("SELECT * FROM planner_approvals WHERE approval_id = :id")
            row = conn.execute(q, {"id": approval_id}).mappings().first()
            if not row:
                return None

            audit_q = text("""
                SELECT id, action, previous_status, new_status, original_values,
                       edited_values, planner_id, reason_or_comment, timestamp
                FROM planner_approval_audit_trail
                WHERE approval_id = :id
                ORDER BY timestamp ASC, id ASC
            """)
            audit_rows = conn.execute(audit_q, {"id": approval_id}).mappings().all()

            res = dict(row)
            res["audit_trail"] = [dict(a) for a in audit_rows]
            return res

    def list_approvals(
        self,
        snapshot_id: str | None = None,
        status: str | None = None,
        exception_category: str | None = None,
        pattern: str | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Queries approval records with rich multi-attribute filtering."""
        with self.db_engine.connect() as conn:
            filters = []
            params: dict[str, Any] = {"limit": limit, "offset": offset}

            if snapshot_id:
                filters.append("snapshot_id = :snapshot_id")
                params["snapshot_id"] = snapshot_id

            if status and status != "all":
                filters.append("status = :status")
                params["status"] = status.upper()

            if exception_category and exception_category != "all":
                filters.append("exception_category = :exc")
                params["exc"] = exception_category

            if pattern and pattern != "all":
                filters.append("pattern = :pat")
                params["pat"] = pattern

            if search and search.strip():
                filters.append("(product_name ILIKE :search OR CAST(product_id AS TEXT) LIKE :search)")
                params["search"] = f"%{search.strip()}%"

            where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""

            count_q = text(f"SELECT count(*) FROM planner_approvals {where_sql}")
            total = conn.execute(count_q, params).scalar() or 0

            data_q = text(f"""
                SELECT * FROM planner_approvals
                {where_sql}
                ORDER BY created_at DESC, abs(target_delta) DESC NULLS LAST
                LIMIT :limit OFFSET :offset
            """)
            rows = conn.execute(data_q, params).mappings().all()

            return {
                "total": total,
                "items": [dict(r) for r in rows],
                "limit": limit,
                "offset": offset,
            }

    def get_summary(self, snapshot_id: str | None = None) -> dict[str, Any]:
        """Provides status and exception queue summary counts."""
        with self.db_engine.connect() as conn:
            params = {}
            where_snap = ""
            if snapshot_id:
                where_snap = "WHERE snapshot_id = :snapshot_id"
                params["snapshot_id"] = snapshot_id

            status_q = text(f"""
                SELECT status, count(*) FROM planner_approvals
                {where_snap}
                GROUP BY status
            """)
            status_rows = conn.execute(status_q, params).fetchall()
            status_counts = {s: 0 for s in ALLOWED_APPROVAL_STATUSES}
            for s, c in status_rows:
                status_counts[s] = int(c)

            exc_q = text(f"""
                SELECT exception_category, count(*) FROM planner_approvals
                {where_snap}
                GROUP BY exception_category
            """)
            exc_rows = conn.execute(exc_q, params).fetchall()
            exc_counts = {}
            for e, c in exc_rows:
                exc_counts[e] = int(c)

            total_q = text(f"SELECT count(*) FROM planner_approvals {where_snap}")
            total = conn.execute(total_q, params).scalar() or 0

            return {
                "total_items": total,
                "status_counts": status_counts,
                "exception_counts": exc_counts,
                "disclaimer": "AI RECOMMENDATION — REQUIRES PLANNER APPROVAL",
            }

    def approve_recommendation(
        self,
        approval_id: str,
        planner_id: str,
        comment: str | None = None,
        warning_acknowledged: bool = False,
    ) -> dict[str, Any]:
        """
        Approves an AI recommendation without modifying original figures.
        Enforces safety validation before approval.
        """
        if not planner_id or not str(planner_id).strip():
            raise ValueError("Planner ID is required to approve a recommendation.")

        with self.db_engine.begin() as conn:
            q = text("SELECT * FROM planner_approvals WHERE approval_id = :id FOR UPDATE")
            row = conn.execute(q, {"id": approval_id}).mappings().first()
            if not row:
                raise ValueError(f"Approval record '{approval_id}' not found.")

            prev_status = row["status"]
            if prev_status == "APPROVED":
                raise ValueError(f"Recommendation '{approval_id}' is already APPROVED.")

            # Safety Validation
            target = float(row["edited_target_stock"] if row["edited_target_stock"] is not None else row["target_stock"])
            purchase = float(row["edited_purchase_qty"] if row["edited_purchase_qty"] is not None else row["suggested_purchase"])
            pattern = row["pattern"]
            exc_cat = row["exception_category"]

            if target < 0.0 or purchase < 0.0:
                raise ValueError("Safety violation: Target and purchase quantities must be non-negative.")

            if pattern == "dead_stock":
                if target != 0.0 or purchase != 0.0:
                    raise ValueError("Safety violation: Dead stock products must have strictly 0.0 target and purchase quantities.")

            # Risky Category Governance Check
            if exc_cat in RISKY_EXCEPTION_CATEGORIES:
                if not warning_acknowledged and not (comment and len(comment.strip()) >= 5):
                    raise ValueError(
                        f"Item '{row['product_name']}' is in high-risk exception category '{exc_cat}'. "
                        "Planner must acknowledge the warning or provide an explanatory comment."
                    )

            now_iso = datetime.now(timezone.utc)

            # Update status
            upd_q = text("""
                UPDATE planner_approvals
                SET status = 'APPROVED',
                    planner_id = :planner_id,
                    planner_comment = :comment,
                    reviewed_at = :reviewed_at
                WHERE approval_id = :id
            """)
            conn.execute(upd_q, {
                "id": approval_id,
                "planner_id": planner_id.strip(),
                "comment": comment.strip() if comment else "Approved without modification.",
                "reviewed_at": now_iso,
            })

            # Audit Trail
            orig_vals = {
                "target_stock": float(row["target_stock"]),
                "suggested_purchase": float(row["suggested_purchase"]),
                "forecast_1m": float(row["forecast_1m"]),
                "pattern": row["pattern"],
            }
            audit_q = text("""
                INSERT INTO planner_approval_audit_trail (
                    approval_id, action, previous_status, new_status,
                    original_values, edited_values, planner_id, reason_or_comment, timestamp
                ) VALUES (
                    :id, 'APPROVED', :prev_status, 'APPROVED',
                    :orig_vals, NULL, :planner_id, :comment, :ts
                )
            """)
            conn.execute(audit_q, {
                "id": approval_id,
                "prev_status": prev_status,
                "orig_vals": json.dumps(orig_vals),
                "planner_id": planner_id.strip(),
                "comment": comment.strip() if comment else "Approved without modification.",
                "ts": now_iso,
            })

        return self.get_approval(approval_id) # type: ignore

    def reject_recommendation(
        self,
        approval_id: str,
        planner_id: str,
        reason: str,
    ) -> dict[str, Any]:
        """
        Rejects an AI recommendation. Requires an explicit reason string.
        Preserves all AI recommendations without modification.
        """
        if not planner_id or not str(planner_id).strip():
            raise ValueError("Planner ID is required to reject a recommendation.")

        if not reason or len(str(reason).strip()) < 3:
            raise ValueError("A clear rejection reason (minimum 3 characters) is required.")

        with self.db_engine.begin() as conn:
            q = text("SELECT * FROM planner_approvals WHERE approval_id = :id FOR UPDATE")
            row = conn.execute(q, {"id": approval_id}).mappings().first()
            if not row:
                raise ValueError(f"Approval record '{approval_id}' not found.")

            prev_status = row["status"]
            now_iso = datetime.now(timezone.utc)

            upd_q = text("""
                UPDATE planner_approvals
                SET status = 'REJECTED',
                    planner_id = :planner_id,
                    planner_comment = :reason,
                    reviewed_at = :reviewed_at
                WHERE approval_id = :id
            """)
            conn.execute(upd_q, {
                "id": approval_id,
                "planner_id": planner_id.strip(),
                "reason": reason.strip(),
                "reviewed_at": now_iso,
            })

            orig_vals = {
                "target_stock": float(row["target_stock"]),
                "suggested_purchase": float(row["suggested_purchase"]),
                "pattern": row["pattern"],
            }
            audit_q = text("""
                INSERT INTO planner_approval_audit_trail (
                    approval_id, action, previous_status, new_status,
                    original_values, edited_values, planner_id, reason_or_comment, timestamp
                ) VALUES (
                    :id, 'REJECTED', :prev_status, 'REJECTED',
                    :orig_vals, NULL, :planner_id, :reason, :ts
                )
            """)
            conn.execute(audit_q, {
                "id": approval_id,
                "prev_status": prev_status,
                "orig_vals": json.dumps(orig_vals),
                "planner_id": planner_id.strip(),
                "reason": reason.strip(),
                "ts": now_iso,
            })

        return self.get_approval(approval_id) # type: ignore

    def edit_recommendation(
        self,
        approval_id: str,
        planner_id: str,
        edited_target: float,
        edited_purchase: float,
        reason: str,
    ) -> dict[str, Any]:
        """
        Overrides recommended quantities.
        PRESERVES original AI recommendations intact while storing edited figures.
        Requires planner reason. Enforces non-negative and dead-stock protections.
        """
        if not planner_id or not str(planner_id).strip():
            raise ValueError("Planner ID is required to edit a recommendation.")

        if not reason or len(str(reason).strip()) < 3:
            raise ValueError("A clear explanation/reason is required when editing quantities.")

        edited_tgt = float(edited_target)
        edited_buy = float(edited_purchase)

        if edited_tgt < 0.0 or edited_buy < 0.0:
            raise ValueError("Safety violation: Edited target and purchase quantities cannot be negative.")

        with self.db_engine.begin() as conn:
            q = text("SELECT * FROM planner_approvals WHERE approval_id = :id FOR UPDATE")
            row = conn.execute(q, {"id": approval_id}).mappings().first()
            if not row:
                raise ValueError(f"Approval record '{approval_id}' not found.")

            # Dead-stock safety invariant
            if row["pattern"] == "dead_stock":
                if edited_tgt != 0.0 or edited_buy != 0.0:
                    raise ValueError("Safety invariant violation: Dead stock products cannot have positive targets or purchases.")

            prev_status = row["status"]
            now_iso = datetime.now(timezone.utc)

            upd_q = text("""
                UPDATE planner_approvals
                SET status = 'EDITED',
                    edited_target_stock = :tgt,
                    edited_purchase_qty = :buy,
                    planner_id = :planner_id,
                    planner_comment = :reason,
                    reviewed_at = :reviewed_at
                WHERE approval_id = :id
            """)
            conn.execute(upd_q, {
                "id": approval_id,
                "tgt": round(edited_tgt, 2),
                "buy": round(edited_buy, 2),
                "planner_id": planner_id.strip(),
                "reason": reason.strip(),
                "reviewed_at": now_iso,
            })

            orig_vals = {
                "target_stock": float(row["target_stock"]),
                "suggested_purchase": float(row["suggested_purchase"]),
                "pattern": row["pattern"],
            }
            edited_vals = {
                "edited_target_stock": round(edited_tgt, 2),
                "edited_purchase_qty": round(edited_buy, 2),
            }
            audit_q = text("""
                INSERT INTO planner_approval_audit_trail (
                    approval_id, action, previous_status, new_status,
                    original_values, edited_values, planner_id, reason_or_comment, timestamp
                ) VALUES (
                    :id, 'EDITED', :prev_status, 'EDITED',
                    :orig_vals, :edited_vals, :planner_id, :reason, :ts
                )
            """)
            conn.execute(audit_q, {
                "id": approval_id,
                "prev_status": prev_status,
                "orig_vals": json.dumps(orig_vals),
                "edited_vals": json.dumps(edited_vals),
                "planner_id": planner_id.strip(),
                "reason": reason.strip(),
                "ts": now_iso,
            })

        return self.get_approval(approval_id) # type: ignore
