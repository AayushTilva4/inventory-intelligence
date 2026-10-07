"""
FastAPI Router for Passive Production Canary Shadow.

Exposes:
- Side-by-side legacy vs shadow comparisons
- Exception queues for human planner review
- Snapshot histories and anomaly metrics
- Product-level audit logging

STRICT CANARY INVARIANTS:
- Read-only operations.
- Zero Odoo writes or PO creation.
- Labeled: PASSIVE SHADOW — NOT LIVE PROCUREMENT.
"""

from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
import pandas as pd

from app.db.connection import get_poc_engine
from app.forecasting.benchmark_v2.canary_shadow import (
    CanaryShadowRunner,
    PLANNER_EXCEPTION_CATEGORIES,
)
from app.forecasting.benchmark_v2.calibration import EmpiricalSafetyCalibrator
from app.forecasting.engine_adapter import load_forecasting_inputs, load_existing_engine

router = APIRouter(
    prefix="/api/shadow",
    tags=["Canary Shadow"],
)


@router.get("/snapshots")
def get_shadow_snapshots(limit: int = 20) -> list[dict[str, Any]]:
    """Lists recent passive canary shadow snapshot executions."""
    engine = get_poc_engine()
    query = text("""
        SELECT snapshot_id, created_at, num_products, runtime_seconds,
               avg_latency_ms, invariant_checks_passed, anomalies_count,
               exception_counts, metadata
        FROM shadow_snapshots
        ORDER BY created_at DESC
        LIMIT :limit
    """)
    try:
        with engine.connect() as conn:
            rows = conn.execute(query, {"limit": limit}).mappings().all()
            return [dict(r) for r in rows]
    except Exception as exc:
        return []


@router.get("/exceptions/summary")
def get_exceptions_summary(snapshot_id: Optional[str] = None) -> dict[str, Any]:
    """Returns aggregated planner exception queue counts."""
    engine = get_poc_engine()
    try:
        with engine.connect() as conn:
            # Find target snapshot
            if not snapshot_id:
                latest_q = text("SELECT snapshot_id FROM shadow_snapshots ORDER BY created_at DESC LIMIT 1")
                latest_res = conn.execute(latest_q).scalar()
                if not latest_res:
                    return {"snapshot_id": None, "categories": {cat: 0 for cat in PLANNER_EXCEPTION_CATEGORIES}, "total": 0}
                snapshot_id = str(latest_res)

            query = text("""
                SELECT primary_exception, count(*) as count
                FROM shadow_product_comparisons
                WHERE snapshot_id = :snapshot_id
                GROUP BY primary_exception
            """)
            rows = conn.execute(query, {"snapshot_id": snapshot_id}).fetchall()
            cat_map = {cat: 0 for cat in PLANNER_EXCEPTION_CATEGORIES}
            total = 0
            for r in rows:
                cat_map[r[0]] = int(r[1])
                total += int(r[1])

            return {
                "snapshot_id": snapshot_id,
                "categories": cat_map,
                "total_products": total,
                "disclaimer": "PASSIVE SHADOW — NOT LIVE PROCUREMENT",
            }
    except Exception as exc:
        return {"error": str(exc), "categories": {cat: 0 for cat in PLANNER_EXCEPTION_CATEGORIES}}


@router.get("/comparisons")
def get_shadow_comparisons(
    snapshot_id: Optional[str] = None,
    exception_category: Optional[str] = None,
    pattern: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """
    Returns side-by-side legacy vs shadow comparisons with filtering.
    """
    engine = get_poc_engine()
    try:
        with engine.connect() as conn:
            # Default to latest snapshot
            if not snapshot_id:
                latest_q = text("SELECT snapshot_id FROM shadow_snapshots ORDER BY created_at DESC LIMIT 1")
                latest_res = conn.execute(latest_q).scalar()
                if not latest_res:
                    return {"items": [], "total": 0, "snapshot_id": None}
                snapshot_id = str(latest_res)

            filters = ["snapshot_id = :snapshot_id"]
            params: dict[str, Any] = {"snapshot_id": snapshot_id, "limit": limit, "offset": offset}

            if exception_category and exception_category != "all":
                filters.append("primary_exception = :exc")
                params["exc"] = exception_category

            if pattern and pattern != "all":
                filters.append("pattern = :pat")
                params["pat"] = pattern

            if search:
                filters.append("(product_name ILIKE :search OR CAST(product_id AS TEXT) LIKE :search)")
                params["search"] = f"%{search}%"

            where_clause = " AND ".join(filters)

            # Total count
            count_q = text(f"SELECT count(*) FROM shadow_product_comparisons WHERE {where_clause}")
            total_count = conn.execute(count_q, params).scalar() or 0

            # Records
            data_q = text(f"""
                SELECT product_id, product_name, pattern,
                       recent_demand_1m, recent_demand_3m, recent_demand_12m,
                       forecast_1m, forecast_h3, safety_buffer, service_level_target,
                       target_stock, current_stock, suggested_purchase,
                       legacy_reorder_target, legacy_forecast, target_delta, target_delta_pct,
                       shadow_coverage_months, legacy_coverage_months,
                       primary_exception, all_exception_flags, risk_classification,
                       confidence_level, reason_for_difference, created_at
                FROM shadow_product_comparisons
                WHERE {where_clause}
                ORDER BY abs(target_delta) DESC NULLS LAST
                LIMIT :limit OFFSET :offset
            """)
            rows = conn.execute(data_q, params).mappings().all()

            return {
                "snapshot_id": snapshot_id,
                "disclaimer": "PASSIVE SHADOW — NOT LIVE PROCUREMENT",
                "total": total_count,
                "items": [dict(r) for r in rows],
            }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database query failed: {exc}")


@router.get("/audit-log/{product_id}")
def get_product_audit_log(product_id: int) -> list[dict[str, Any]]:
    """Returns audit history for a specific product."""
    engine = get_poc_engine()
    query = text("""
        SELECT snapshot_id, product_id, timestamp, model_name,
               forecast_1m, forecast_h3, calibration_policy, target_stock,
               legacy_target, target_delta, primary_exception, reason_for_difference
        FROM shadow_audit_logs
        WHERE product_id = :pid
        ORDER BY timestamp DESC
        LIMIT 50
    """)
    try:
        with engine.connect() as conn:
            rows = conn.execute(query, {"pid": product_id}).mappings().all()
            return [dict(r) for r in rows]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
