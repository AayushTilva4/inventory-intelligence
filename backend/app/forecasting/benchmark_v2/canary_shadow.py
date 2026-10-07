"""
Canary Shadow Module for Step 10: Passive Production Canary Shadow.

Frozen Configuration:
- Central Forecast: trimmed_mean_3
- Safety Policy:
  - fast_moving: 80% empirical CSL
  - stable/normal: 80% empirical CSL
  - rising: 75% empirical CSL
  - falling: 75% empirical CSL
  - intermittent: 75% empirical CSL
  - dead_stock: 0% empirical CSL (strictly hard-clamped to 0 forecast, buffer, and target)
  - cold_start: 75% empirical CSL

Guarantees:
- Strictly Read-Only with zero writes to Odoo.
- Strictly Zero Purchase Orders created.
- Production isolation: Legacy production engine is completely untouched.
- Non-blocking execution with failure isolation.
- Every run enforces strict safety invariants:
  - forecast >= 0
  - target >= 0
  - purchase_qty >= 0
  - dead_stock target == 0
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
import numpy as np
import pandas as pd
from sqlalchemy import text, Engine

from app.db.connection import get_poc_engine
from .classification import classify_demand_pattern
from .models import forecast_multistep
from .calibration import EmpiricalSafetyCalibrator
from .metrics import calculate_mase_scale


# ==============================================================================
# FROZEN CONFIGURATION
# ==============================================================================

FROZEN_MODEL_NAME = "trimmed_mean_3"

FROZEN_SERVICE_LEVEL_POLICIES = {
    "fast_moving": 0.80,
    "stable/normal": 0.80,
    "rising": 0.75,
    "falling": 0.75,
    "intermittent": 0.75,
    "dead_stock": 0.00,
    "cold_start": 0.75,
    "low_demand": 0.75,
}

PLANNER_EXCEPTION_CATEGORIES = [
    "major_target_reduction",
    "major_target_increase",
    "rising_product_risk",
    "intermittent_uncertainty",
    "batch_moq_constraint_required",
    "zero_demand_dormant",
    "unusually_large_forecast_change",
    "standard_monitoring",
]


def _empty_calibrator_record():
    return {
        "model": FROZEN_MODEL_NAME,
        "as_of_origin_pattern": "stable/normal",
        "horizon": 3,
        "actual": 10.0,
        "forecast": 10.0,
        "mase_scale": 1.0,
    }


@dataclass(frozen=True)
class CanaryShadowRecord:
    """Structured record for a single product in passive shadow evaluation."""
    snapshot_id: str
    product_id: int
    product_name: str
    pattern: str
    recent_demand_1m: float
    recent_demand_3m: float
    recent_demand_12m: float
    forecast_1m: float
    forecast_h3: float
    safety_buffer: float
    service_level_target: float
    target_stock: float
    current_stock: float
    suggested_purchase: float
    legacy_reorder_target: float | None
    legacy_forecast: float | None
    target_delta: float | None
    target_delta_pct: float | None
    shadow_coverage_months: float | None
    legacy_coverage_months: float | None
    primary_exception: str
    all_exception_flags: list[str]
    risk_classification: str
    confidence_level: str
    reason_for_difference: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CanaryShadowRunner:
    """
    Executes passive canary shadow evaluations across the catalog.
    Enforces non-blocking execution, failure isolation, and strict invariants.
    """

    def __init__(
        self,
        calibrator: EmpiricalSafetyCalibrator | None = None,
        db_engine: Engine | None = None,
    ):
        self.calibrator = calibrator or EmpiricalSafetyCalibrator()
        self.db_engine = db_engine or get_poc_engine()
        self._init_db_tables()

    def _init_db_tables(self) -> None:
        """Initializes POC PostgreSQL shadow tables if they do not exist."""
        ddl = """
        CREATE TABLE IF NOT EXISTS shadow_snapshots (
            snapshot_id VARCHAR(64) PRIMARY KEY,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            num_products INT NOT NULL,
            runtime_seconds NUMERIC(10, 2) NOT NULL,
            avg_latency_ms NUMERIC(10, 2) NOT NULL,
            invariant_checks_passed BOOLEAN NOT NULL,
            anomalies_count INT NOT NULL DEFAULT 0,
            exception_counts JSONB NOT NULL,
            metadata JSONB
        );

        CREATE TABLE IF NOT EXISTS shadow_product_comparisons (
            id SERIAL PRIMARY KEY,
            snapshot_id VARCHAR(64) NOT NULL REFERENCES shadow_snapshots(snapshot_id) ON DELETE CASCADE,
            product_id INT NOT NULL,
            product_name VARCHAR(255),
            pattern VARCHAR(50) NOT NULL,
            recent_demand_1m NUMERIC(12, 2) NOT NULL,
            recent_demand_3m NUMERIC(12, 2) NOT NULL,
            recent_demand_12m NUMERIC(12, 2) NOT NULL,
            forecast_1m NUMERIC(12, 2) NOT NULL,
            forecast_h3 NUMERIC(12, 2) NOT NULL,
            safety_buffer NUMERIC(12, 2) NOT NULL,
            service_level_target NUMERIC(5, 2) NOT NULL,
            target_stock NUMERIC(12, 2) NOT NULL,
            current_stock NUMERIC(12, 2) NOT NULL,
            suggested_purchase NUMERIC(12, 2) NOT NULL,
            legacy_reorder_target NUMERIC(12, 2),
            legacy_forecast NUMERIC(12, 2),
            target_delta NUMERIC(12, 2),
            target_delta_pct NUMERIC(10, 4),
            shadow_coverage_months NUMERIC(10, 2),
            legacy_coverage_months NUMERIC(10, 2),
            primary_exception VARCHAR(64) NOT NULL,
            all_exception_flags JSONB NOT NULL,
            risk_classification VARCHAR(64) NOT NULL,
            confidence_level VARCHAR(32) NOT NULL,
            reason_for_difference TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS shadow_audit_logs (
            id SERIAL PRIMARY KEY,
            snapshot_id VARCHAR(64) NOT NULL,
            product_id INT NOT NULL,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            model_name VARCHAR(64) NOT NULL,
            forecast_1m NUMERIC(12, 2) NOT NULL,
            forecast_h3 NUMERIC(12, 2) NOT NULL,
            calibration_policy VARCHAR(64) NOT NULL,
            target_stock NUMERIC(12, 2) NOT NULL,
            legacy_target NUMERIC(12, 2),
            target_delta NUMERIC(12, 2),
            primary_exception VARCHAR(64) NOT NULL,
            reason_for_difference TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_shadow_comp_snapshot ON shadow_product_comparisons(snapshot_id);
        CREATE INDEX IF NOT EXISTS idx_shadow_comp_pid ON shadow_product_comparisons(product_id);
        CREATE INDEX IF NOT EXISTS idx_shadow_comp_exception ON shadow_product_comparisons(primary_exception);
        CREATE INDEX IF NOT EXISTS idx_shadow_audit_pid ON shadow_audit_logs(product_id);
        """
        try:
            with self.db_engine.begin() as conn:
                conn.execute(text(ddl))
        except Exception as e:
            # If DB is unavailable or permissions issue, log and continue in-memory
            print(f"[CanaryShadowRunner] Notice: DB initialization skipped: {e}")

    def evaluate_single_product(
        self,
        snapshot_id: str,
        product_id: int,
        product_name: str,
        sales_series: Sequence[float] | pd.Series,
        current_stock: float = 0.0,
        legacy_reorder_target: float | None = None,
        legacy_forecast: float | None = None,
    ) -> CanaryShadowRecord:
        """
        Performs passive shadow evaluation for a single product while strictly
        enforcing safety invariants and generating exception classifications.
        """
        pid = int(product_id)
        pname = str(product_name or f"Product {pid}")
        stock_val = max(0.0, float(current_stock or 0.0))
        s_series = pd.Series(sales_series, dtype=float).reset_index(drop=True)

        # Recent demand metrics
        n_pts = len(s_series)
        rec_1m = float(s_series.iloc[-1]) if n_pts >= 1 else 0.0
        rec_3m = float(s_series.tail(3).sum()) if n_pts >= 1 else 0.0
        rec_12m = float(s_series.tail(12).sum()) if n_pts >= 1 else 0.0

        # 1. Pattern Classification
        cls = classify_demand_pattern(s_series, stock_on_hand=stock_val)
        pattern = cls["pattern"]

        # 2. Safety Policy Lookup
        policy_sl = FROZEN_SERVICE_LEVEL_POLICIES.get(pattern, 0.75)

        # 3. Central Forecast & Dead-stock Hard Clamping
        if pattern == "dead_stock":
            fc_1m = 0.0
            fc_h3 = 0.0
            safety_buf = 0.0
            tgt_stock = 0.0
            suggested_buy = 0.0
            cal_policy_str = "dead_stock_clamped_0%"
            confidence = "high"
        else:
            preds = forecast_multistep(FROZEN_MODEL_NAME, s_series, max_horizon=3)
            fc_1m = max(0.0, round(float(preds[0]), 2)) if len(preds) >= 1 else 0.0
            fc_h3 = max(0.0, round(float(preds[2]), 2)) if len(preds) >= 3 else fc_1m

            # MASE scale
            scale = calculate_mase_scale(s_series, season_length=12)
            if scale is None or scale <= 0.0:
                scale = max(1.0, fc_h3)

            # Empirical Safety Buffer
            cal_res = self.calibrator.calculate_safety_buffer(
                forecast=fc_h3,
                horizon=3,
                pattern=pattern,
                model=FROZEN_MODEL_NAME,
                service_level=policy_sl,
                scale=scale,
            )
            safety_buf = max(0.0, round(cal_res.safety_buffer, 2))
            tgt_stock = max(0.0, round(fc_h3 + safety_buf, 2))
            suggested_buy = max(0.0, round(tgt_stock - stock_val, 2))
            cal_policy_str = f"empirical_{int(policy_sl * 100)}%"

            # Confidence determination
            if pattern == "intermittent" and rec_3m == 0:
                confidence = "low"
            elif pattern in ["fast_moving", "stable/normal"] and n_pts >= 12:
                confidence = "high"
            else:
                confidence = "medium"

        # 4. Strict Safety Invariants Verification
        assert fc_1m >= 0.0, f"Invariant violation: fc_1m < 0 on product {pid}"
        assert fc_h3 >= 0.0, f"Invariant violation: fc_h3 < 0 on product {pid}"
        assert tgt_stock >= 0.0, f"Invariant violation: tgt_stock < 0 on product {pid}"
        assert suggested_buy >= 0.0, f"Invariant violation: suggested_buy < 0 on product {pid}"
        if pattern == "dead_stock":
            assert tgt_stock == 0.0, f"Invariant violation: dead_stock target > 0 on product {pid}"
            assert suggested_buy == 0.0, f"Invariant violation: dead_stock buy > 0 on product {pid}"

        # 5. Legacy Comparison & Coverage
        leg_tgt = float(legacy_reorder_target) if legacy_reorder_target is not None and not np.isnan(legacy_reorder_target) else None
        leg_fc = float(legacy_forecast) if legacy_forecast is not None and not np.isnan(legacy_forecast) else None

        tgt_delta = round(tgt_stock - leg_tgt, 2) if leg_tgt is not None else None
        tgt_delta_pct = round(tgt_delta / max(leg_tgt, 1.0), 4) if leg_tgt is not None else None

        # Coverage months
        demand_rate = max(fc_1m, rec_3m / 3.0, 0.0)
        if demand_rate > 0.0:
            shadow_cov = round(stock_val / demand_rate, 2)
            legacy_cov = round(leg_tgt / demand_rate, 2) if leg_tgt is not None else None
        else:
            shadow_cov = 999.0 if stock_val > 0 else 0.0
            legacy_cov = 999.0 if leg_tgt is not None and leg_tgt > 0 else 0.0

        # 6. Exception Categories & Risk Flags
        exception_flags = []

        is_major_reduction = False
        is_major_increase = False
        if leg_tgt is not None and tgt_delta is not None:
            if leg_tgt > tgt_stock and (tgt_delta <= -20.0 or (tgt_delta_pct is not None and tgt_delta_pct <= -0.50)):
                is_major_reduction = True
                exception_flags.append("major_target_reduction")
            elif tgt_stock > leg_tgt and (tgt_delta >= 20.0 or (tgt_delta_pct is not None and tgt_delta_pct >= 0.50)):
                is_major_increase = True
                exception_flags.append("major_target_increase")

        is_rising_risk = (pattern == "rising")
        if is_rising_risk:
            exception_flags.append("rising_product_risk")

        is_intermittent_uncertain = (pattern == "intermittent" and (rec_3m > 0 or stock_val > 0))
        if is_intermittent_uncertain:
            exception_flags.append("intermittent_uncertainty")

        is_batch_moq = (suggested_buy > 0 and suggested_buy < 50.0) or (pattern in ["fast_moving", "stable/normal"] and suggested_buy > 0)
        if is_batch_moq:
            exception_flags.append("batch_moq_constraint_required")

        is_dormant_with_target = ((pattern == "dead_stock" or rec_12m == 0.0) and (leg_tgt is not None and leg_tgt > 0))
        if is_dormant_with_target:
            exception_flags.append("zero_demand_dormant")

        is_large_fc_change = False
        if leg_fc is not None and leg_fc > 0.0:
            rel_fc = abs(fc_1m - leg_fc) / leg_fc
            if rel_fc >= 0.50:
                is_large_fc_change = True
                exception_flags.append("unusually_large_forecast_change")

        # Determine Primary Exception Category
        if is_dormant_with_target:
            primary_exc = "zero_demand_dormant"
        elif is_rising_risk:
            primary_exc = "rising_product_risk"
        elif is_large_fc_change:
            primary_exc = "unusually_large_forecast_change"
        elif is_major_reduction:
            primary_exc = "major_target_reduction"
        elif is_major_increase:
            primary_exc = "major_target_increase"
        elif is_intermittent_uncertain:
            primary_exc = "intermittent_uncertainty"
        elif is_batch_moq:
            primary_exc = "batch_moq_constraint_required"
        else:
            primary_exc = "standard_monitoring"

        # Risk Classification
        if leg_tgt is not None and tgt_delta is not None and tgt_delta < -20.0 and stock_val < tgt_stock:
            risk_class = "legacy_overstock_potential_stockout"
        elif leg_tgt is not None and tgt_delta is not None and tgt_delta < -20.0:
            risk_class = "legacy_overstock_curtailed"
        elif leg_tgt is not None and tgt_delta is not None and tgt_delta > 20.0:
            risk_class = "shadow_stock_protection"
        elif pattern == "dead_stock":
            risk_class = "dead_stock_frozen"
        else:
            risk_class = "normal_operational"

        # 7. Reason for Difference (Traceable Explanation)
        reason_parts = []
        if pattern == "dead_stock":
            reason_parts.append(f"Product is dead stock (no sales in last 12m). Target hard-clamped to 0.0m.")
            if leg_tgt and leg_tgt > 0:
                reason_parts.append(f"Legacy target of {leg_tgt}m reflected historical lifetime sales and is prevented.")
        elif is_major_reduction:
            reason_parts.append(f"Shadow target ({tgt_stock}m) is lower than legacy ({leg_tgt}m) by {abs(tgt_delta)}m.")
            reason_parts.append(f"Trimmed demand ({fc_h3}m/mo) + {cal_policy_str} buffer ({safety_buf}m) reflects recent velocity.")
        elif is_major_increase:
            reason_parts.append(f"Shadow target ({tgt_stock}m) is higher than legacy ({leg_tgt}m) by {tgt_delta}m.")
            reason_parts.append(f"Buffer increased to protect active demand against stockout risk.")
        elif pattern == "intermittent":
            reason_parts.append(f"Intermittent demand: empirical 75% quantile prevents phantom inventory building.")
        else:
            reason_parts.append(f"Aligned with {pattern} demand using trimmed_mean_3 + {cal_policy_str} safety buffer.")

        reason_str = " ".join(reason_parts)
        now_iso = datetime.now(timezone.utc).isoformat()

        return CanaryShadowRecord(
            snapshot_id=snapshot_id,
            product_id=pid,
            product_name=pname,
            pattern=pattern,
            recent_demand_1m=rec_1m,
            recent_demand_3m=rec_3m,
            recent_demand_12m=rec_12m,
            forecast_1m=fc_1m,
            forecast_h3=fc_h3,
            safety_buffer=safety_buf,
            service_level_target=policy_sl,
            target_stock=tgt_stock,
            current_stock=stock_val,
            suggested_purchase=suggested_buy,
            legacy_reorder_target=leg_tgt,
            legacy_forecast=leg_fc,
            target_delta=tgt_delta,
            target_delta_pct=tgt_delta_pct,
            shadow_coverage_months=shadow_cov,
            legacy_coverage_months=legacy_cov,
            primary_exception=primary_exc,
            all_exception_flags=exception_flags,
            risk_classification=risk_class,
            confidence_level=confidence,
            reason_for_difference=reason_str,
            created_at=now_iso,
        )

    def run_catalog_shadow_snapshot(
        self,
        monthly_df: pd.DataFrame,
        stock_map: Mapping[int, float],
        legacy_predictions_map: Mapping[int, Mapping[str, float]] | None = None,
        product_ids: Sequence[int] | None = None,
        snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Executes a complete passive shadow evaluation across specified products or
        the full catalog. Persists records to POC DB and returns execution summary.
        """
        t0 = time.time()
        now_dt = datetime.now(timezone.utc)
        snap_id = snapshot_id or f"snap_{int(now_dt.timestamp())}_{now_dt.strftime('%Y%m%d_%H%M%S')}"

        legacy_map = legacy_predictions_map or {}
        pids_to_process = list(product_ids) if product_ids is not None else sorted(monthly_df["product_id"].unique().tolist())
        total_pids = len(pids_to_process)

        from src.sales_data import complete_product_series
        global_end = pd.to_datetime(monthly_df["month"]).max()
        global_end = pd.Timestamp(global_end.year, global_end.month, 1)

        records: list[CanaryShadowRecord] = []
        failures: list[dict[str, Any]] = []

        for pid in pids_to_process:
            try:
                p_group = monthly_df[monthly_df["product_id"] == pid].copy()
                if p_group.empty:
                    continue

                pname = p_group["product_name"].dropna().iloc[0] if not p_group["product_name"].dropna().empty else f"Product {pid}"
                stock_val = float(stock_map.get(pid, 0.0))

                full_series = complete_product_series(p_group, end_date=global_end)
                full_series["month"] = pd.to_datetime(full_series["month"])
                full_series = full_series.sort_values("month").reset_index(drop=True)

                leg_info = legacy_map.get(pid, {})
                leg_fc = leg_info.get("production_forecast")
                leg_tgt = leg_info.get("production_target")

                rec = self.evaluate_single_product(
                    snapshot_id=snap_id,
                    product_id=pid,
                    product_name=pname,
                    sales_series=full_series["total_quantity"],
                    current_stock=stock_val,
                    legacy_reorder_target=leg_tgt,
                    legacy_forecast=leg_fc,
                )
                records.append(rec)
            except Exception as exc:
                failures.append({"product_id": pid, "error": str(exc)})

        elapsed = time.time() - t0
        avg_latency_ms = round((elapsed / max(len(records), 1)) * 1000, 2)

        # Exception counts
        exc_counts = {cat: 0 for cat in PLANNER_EXCEPTION_CATEGORIES}
        for r in records:
            exc_counts[r.primary_exception] = exc_counts.get(r.primary_exception, 0) + 1

        # Safety invariant checks
        invariants_passed = True
        anomalies_count = 0
        for r in records:
            if r.forecast_1m < 0 or r.target_stock < 0 or r.suggested_purchase < 0:
                invariants_passed = False
                anomalies_count += 1
            if r.pattern == "dead_stock" and (r.target_stock > 0 or r.suggested_purchase > 0):
                invariants_passed = False
                anomalies_count += 1

        snapshot_summary = {
            "snapshot_id": snap_id,
            "created_at": now_dt.isoformat(),
            "num_products": len(records),
            "num_failures": len(failures),
            "runtime_seconds": round(elapsed, 2),
            "avg_latency_ms": avg_latency_ms,
            "invariant_checks_passed": invariants_passed,
            "anomalies_count": anomalies_count,
            "exception_counts": exc_counts,
            "metadata": {
                "central_model": FROZEN_MODEL_NAME,
                "policies": FROZEN_SERVICE_LEVEL_POLICIES,
                "total_requested": total_pids,
            },
        }

        # Persist to POC PostgreSQL Database
        self._persist_snapshot_to_db(snapshot_summary, records)

        return {
            "summary": snapshot_summary,
            "records": records,
            "failures": failures,
        }

    def _persist_snapshot_to_db(
        self,
        summary: dict[str, Any],
        records: list[CanaryShadowRecord],
    ) -> None:
        """Saves snapshot, comparison rows, and audit logs to POC PostgreSQL."""
        try:
            with self.db_engine.begin() as conn:
                # 1. Insert snapshot
                conn.execute(
                    text("""
                    INSERT INTO shadow_snapshots (
                        snapshot_id, created_at, num_products, runtime_seconds,
                        avg_latency_ms, invariant_checks_passed, anomalies_count,
                        exception_counts, metadata
                    ) VALUES (
                        :snapshot_id, :created_at, :num_products, :runtime_seconds,
                        :avg_latency_ms, :invariant_checks_passed, :anomalies_count,
                        :exception_counts, :metadata
                    ) ON CONFLICT (snapshot_id) DO NOTHING
                    """),
                    {
                        "snapshot_id": summary["snapshot_id"],
                        "created_at": summary["created_at"],
                        "num_products": summary["num_products"],
                        "runtime_seconds": summary["runtime_seconds"],
                        "avg_latency_ms": summary["avg_latency_ms"],
                        "invariant_checks_passed": summary["invariant_checks_passed"],
                        "anomalies_count": summary["anomalies_count"],
                        "exception_counts": json.dumps(summary["exception_counts"]),
                        "metadata": json.dumps(summary["metadata"]),
                    },
                )

                # 2. Bulk insert comparisons & audit logs
                if records:
                    comp_dicts = []
                    audit_dicts = []
                    for r in records:
                        comp_dicts.append({
                            "snapshot_id": r.snapshot_id,
                            "product_id": r.product_id,
                            "product_name": r.product_name,
                            "pattern": r.pattern,
                            "recent_demand_1m": r.recent_demand_1m,
                            "recent_demand_3m": r.recent_demand_3m,
                            "recent_demand_12m": r.recent_demand_12m,
                            "forecast_1m": r.forecast_1m,
                            "forecast_h3": r.forecast_h3,
                            "safety_buffer": r.safety_buffer,
                            "service_level_target": r.service_level_target,
                            "target_stock": r.target_stock,
                            "current_stock": r.current_stock,
                            "suggested_purchase": r.suggested_purchase,
                            "legacy_reorder_target": r.legacy_reorder_target,
                            "legacy_forecast": r.legacy_forecast,
                            "target_delta": r.target_delta,
                            "target_delta_pct": r.target_delta_pct,
                            "shadow_coverage_months": r.shadow_coverage_months,
                            "legacy_coverage_months": r.legacy_coverage_months,
                            "primary_exception": r.primary_exception,
                            "all_exception_flags": json.dumps(r.all_exception_flags),
                            "risk_classification": r.risk_classification,
                            "confidence_level": r.confidence_level,
                            "reason_for_difference": r.reason_for_difference,
                        })

                        audit_dicts.append({
                            "snapshot_id": r.snapshot_id,
                            "product_id": r.product_id,
                            "model_name": FROZEN_MODEL_NAME,
                            "forecast_1m": r.forecast_1m,
                            "forecast_h3": r.forecast_h3,
                            "calibration_policy": f"sl_{int(r.service_level_target * 100)}%",
                            "target_stock": r.target_stock,
                            "legacy_target": r.legacy_reorder_target,
                            "target_delta": r.target_delta,
                            "primary_exception": r.primary_exception,
                            "reason_for_difference": r.reason_for_difference,
                        })

                    # Insert comparisons
                    conn.execute(
                        text("""
                        INSERT INTO shadow_product_comparisons (
                            snapshot_id, product_id, product_name, pattern,
                            recent_demand_1m, recent_demand_3m, recent_demand_12m,
                            forecast_1m, forecast_h3, safety_buffer, service_level_target,
                            target_stock, current_stock, suggested_purchase,
                            legacy_reorder_target, legacy_forecast, target_delta, target_delta_pct,
                            shadow_coverage_months, legacy_coverage_months,
                            primary_exception, all_exception_flags, risk_classification,
                            confidence_level, reason_for_difference
                        ) VALUES (
                            :snapshot_id, :product_id, :product_name, :pattern,
                            :recent_demand_1m, :recent_demand_3m, :recent_demand_12m,
                            :forecast_1m, :forecast_h3, :safety_buffer, :service_level_target,
                            :target_stock, :current_stock, :suggested_purchase,
                            :legacy_reorder_target, :legacy_forecast, :target_delta, :target_delta_pct,
                            :shadow_coverage_months, :legacy_coverage_months,
                            :primary_exception, :all_exception_flags, :risk_classification,
                            :confidence_level, :reason_for_difference
                        )
                        """),
                        comp_dicts,
                    )

                    # Insert audit logs
                    conn.execute(
                        text("""
                        INSERT INTO shadow_audit_logs (
                            snapshot_id, product_id, model_name, forecast_1m, forecast_h3,
                            calibration_policy, target_stock, legacy_target, target_delta,
                            primary_exception, reason_for_difference
                        ) VALUES (
                            :snapshot_id, :product_id, :model_name, :forecast_1m, :forecast_h3,
                            :calibration_policy, :target_stock, :legacy_target, :target_delta,
                            :primary_exception, :reason_for_difference
                        )
                        """),
                        audit_dicts,
                    )
        except Exception as e:
            print(f"[CanaryShadowRunner] Warning: DB persistence failed ({e}), continuing in-memory.")
