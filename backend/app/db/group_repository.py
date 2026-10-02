import json
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import Engine, text

from app.db.connection import get_poc_engine


@contextmanager
def _using_engine(engine: Engine | None = None) -> Iterator[Engine]:
    owns_engine = engine is None
    active_engine = engine or get_poc_engine()
    try:
        yield active_engine
    finally:
        if owns_engine:
            active_engine.dispose()


def create_group_tables(engine: Engine | None = None) -> None:
    forecast_ddl = """
        CREATE TABLE IF NOT EXISTS group_forecast_results (
            id BIGSERIAL PRIMARY KEY,
            main_product_template_id BIGINT NOT NULL UNIQUE,
            main_product_name TEXT NOT NULL,
            group_size INTEGER NOT NULL,
            months_available INTEGER,
            history_start TEXT,
            history_end TEXT,
            next_month_forecast NUMERIC,
            best_model TEXT,
            confidence TEXT,
            mae NUMERIC,
            wape NUMERIC,
            mase NUMERIC,
            avg_monthly_demand NUMERIC,
            forecast_status TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """
    recommendation_ddl = """
        CREATE TABLE IF NOT EXISTS group_inventory_recommendations (
            id BIGSERIAL PRIMARY KEY,
            main_product_template_id BIGINT NOT NULL UNIQUE,
            main_product_name TEXT NOT NULL,
            group_size INTEGER NOT NULL,
            group_valid BOOLEAN NOT NULL,
            group_current_stock NUMERIC,
            group_next_month_forecast NUMERIC,
            best_model TEXT,
            confidence TEXT,
            group_reorder_point NUMERIC,
            group_buffered_target_stock NUMERIC,
            group_stock_gap NUMERIC,
            group_coverage_ratio NUMERIC,
            group_suggested_purchase_qty NUMERIC NOT NULL DEFAULT 0,
            action TEXT NOT NULL,
            priority TEXT NOT NULL,
            reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
            validation_issues JSONB NOT NULL DEFAULT '[]'::jsonb,
            validation_warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
            dead_stock BOOLEAN,
            dead_stock_reason TEXT,
            recommendation_status TEXT NOT NULL,
            forecast_status TEXT,
            approval_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (approval_status IN ('pending', 'approved', 'rejected')),
            approval_updated_at TIMESTAMP NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """

    with _using_engine(engine) as active_engine:
        with active_engine.begin() as connection:
            connection.execute(text(forecast_ddl))
            connection.execute(text(recommendation_ddl))


def upsert_group_forecast(
    result: dict[str, Any],
    engine: Engine | None = None,
) -> None:
    query = text("""
        INSERT INTO group_forecast_results (
            main_product_template_id, main_product_name, group_size,
            months_available, history_start, history_end,
            next_month_forecast, best_model, confidence, mae, wape, mase,
            avg_monthly_demand, forecast_status
        ) VALUES (
            :main_product_template_id, :main_product_name, :group_size,
            :months_available, :history_start, :history_end,
            :next_month_forecast, :best_model, :confidence, :mae, :wape, :mase,
            :avg_monthly_demand, :forecast_status
        )
        ON CONFLICT (main_product_template_id) DO UPDATE SET
            main_product_name = EXCLUDED.main_product_name,
            group_size = EXCLUDED.group_size,
            months_available = EXCLUDED.months_available,
            history_start = EXCLUDED.history_start,
            history_end = EXCLUDED.history_end,
            next_month_forecast = EXCLUDED.next_month_forecast,
            best_model = EXCLUDED.best_model,
            confidence = EXCLUDED.confidence,
            mae = EXCLUDED.mae,
            wape = EXCLUDED.wape,
            mase = EXCLUDED.mase,
            avg_monthly_demand = EXCLUDED.avg_monthly_demand,
            forecast_status = EXCLUDED.forecast_status,
            updated_at = CURRENT_TIMESTAMP
    """)
    params = {
        "main_product_template_id": result["main_product_template_id"],
        "main_product_name": result.get("main_product_name") or "",
        "group_size": result["group_size"],
        "months_available": result.get("months_available"),
        "history_start": result.get("history_start"),
        "history_end": result.get("history_end"),
        "next_month_forecast": result.get("next_month_forecast"),
        "best_model": result.get("best_model"),
        "confidence": result.get("confidence"),
        "mae": result.get("mae"),
        "wape": result.get("wape"),
        "mase": result.get("mase"),
        "avg_monthly_demand": result.get("avg_monthly_demand"),
        "forecast_status": result.get("status") or result.get("forecast_status"),
    }
    with _using_engine(engine) as active_engine:
        with active_engine.begin() as connection:
            connection.execute(query, params)


def save_group_forecast(
    result: dict[str, Any],
    engine: Engine | None = None,
) -> None:
    upsert_group_forecast(result, engine=engine)


def upsert_group_recommendation(
    result: dict[str, Any],
    engine: Engine | None = None,
) -> None:
    query = text("""
        INSERT INTO group_inventory_recommendations (
            main_product_template_id, main_product_name, group_size, group_valid,
            group_current_stock, group_next_month_forecast, best_model, confidence,
            group_reorder_point, group_buffered_target_stock, group_stock_gap,
            group_coverage_ratio, group_suggested_purchase_qty, action, priority,
            reason_codes, validation_issues, validation_warnings, dead_stock,
            dead_stock_reason, recommendation_status, forecast_status
        ) VALUES (
            :main_product_template_id, :main_product_name, :group_size, :group_valid,
            :group_current_stock, :group_next_month_forecast, :best_model, :confidence,
            :group_reorder_point, :group_buffered_target_stock, :group_stock_gap,
            :group_coverage_ratio, :group_suggested_purchase_qty, :action, :priority,
            CAST(:reason_codes AS JSONB), CAST(:validation_issues AS JSONB),
            CAST(:validation_warnings AS JSONB), :dead_stock, :dead_stock_reason,
            :recommendation_status, :forecast_status
        )
        ON CONFLICT (main_product_template_id) DO UPDATE SET
            main_product_name = EXCLUDED.main_product_name,
            group_size = EXCLUDED.group_size,
            group_valid = EXCLUDED.group_valid,
            group_current_stock = EXCLUDED.group_current_stock,
            group_next_month_forecast = EXCLUDED.group_next_month_forecast,
            best_model = EXCLUDED.best_model,
            confidence = EXCLUDED.confidence,
            group_reorder_point = EXCLUDED.group_reorder_point,
            group_buffered_target_stock = EXCLUDED.group_buffered_target_stock,
            group_stock_gap = EXCLUDED.group_stock_gap,
            group_coverage_ratio = EXCLUDED.group_coverage_ratio,
            group_suggested_purchase_qty = EXCLUDED.group_suggested_purchase_qty,
            action = EXCLUDED.action,
            priority = EXCLUDED.priority,
            reason_codes = EXCLUDED.reason_codes,
            validation_issues = EXCLUDED.validation_issues,
            validation_warnings = EXCLUDED.validation_warnings,
            dead_stock = EXCLUDED.dead_stock,
            dead_stock_reason = EXCLUDED.dead_stock_reason,
            recommendation_status = EXCLUDED.recommendation_status,
            forecast_status = EXCLUDED.forecast_status,
            updated_at = CURRENT_TIMESTAMP
    """)
    params = {
        "main_product_template_id": result["main_product_template_id"],
        "main_product_name": result.get("main_product_name") or "",
        "group_size": result["group_size"],
        "group_valid": result["group_valid"],
        "group_current_stock": result.get("group_current_stock"),
        "group_next_month_forecast": result.get("group_next_month_forecast"),
        "best_model": result.get("best_model"),
        "confidence": result.get("confidence"),
        "group_reorder_point": result.get("group_reorder_point"),
        "group_buffered_target_stock": result.get("group_buffered_target_stock"),
        "group_stock_gap": result.get("group_stock_gap"),
        "group_coverage_ratio": result.get("group_coverage_ratio"),
        "group_suggested_purchase_qty": result.get(
            "group_suggested_purchase_qty", 0
        ),
        "action": result["action"],
        "priority": result["priority"],
        "reason_codes": json.dumps(result.get("reason_codes") or []),
        "validation_issues": json.dumps(result.get("validation_issues") or []),
        "validation_warnings": json.dumps(result.get("validation_warnings") or []),
        "dead_stock": result.get("dead_stock"),
        "dead_stock_reason": result.get("dead_stock_reason"),
        "recommendation_status": result.get("status") or "ok",
        "forecast_status": result.get("forecast_status"),
    }
    with _using_engine(engine) as active_engine:
        with active_engine.begin() as connection:
            connection.execute(query, params)


def save_group_recommendation(
    result: dict[str, Any],
    engine: Engine | None = None,
) -> None:
    upsert_group_recommendation(result, engine=engine)


def update_group_approval_status(
    main_product_template_id: int,
    status: str,
    engine: Engine | None = None,
) -> bool:
    if status not in {"pending", "approved", "rejected"}:
        raise ValueError("Approval status must be pending, approved, or rejected")

    with _using_engine(engine) as active_engine:
        with active_engine.begin() as connection:
            result = connection.execute(
                text("""
                    UPDATE group_inventory_recommendations
                    SET approval_status = :status,
                        approval_updated_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE main_product_template_id = :main_product_template_id
                """),
                {
                    "status": status,
                    "main_product_template_id": main_product_template_id,
                },
            )
    return result.rowcount > 0


def _get_one(
    table_name: str,
    main_product_template_id: int,
    engine: Engine | None = None,
) -> dict[str, Any] | None:
    if table_name not in {
        "group_forecast_results",
        "group_inventory_recommendations",
    }:
        raise ValueError("Unsupported group persistence table")

    with _using_engine(engine) as active_engine:
        with active_engine.connect() as connection:
            row = connection.execute(
                text(
                    f"SELECT * FROM {table_name} "
                    "WHERE main_product_template_id = :main_product_template_id"
                ),
                {"main_product_template_id": main_product_template_id},
            ).mappings().first()
            return dict(row) if row else None


def _get_all(table_name: str, engine: Engine | None = None) -> list[dict[str, Any]]:
    if table_name not in {
        "group_forecast_results",
        "group_inventory_recommendations",
    }:
        raise ValueError("Unsupported group persistence table")

    with _using_engine(engine) as active_engine:
        with active_engine.connect() as connection:
            rows = connection.execute(
                text(
                    f"SELECT * FROM {table_name} "
                    "ORDER BY main_product_template_id"
                )
            ).mappings().all()
            return [dict(row) for row in rows]


def get_group_forecast(
    main_product_template_id: int,
    engine: Engine | None = None,
) -> dict[str, Any] | None:
    return _get_one(
        "group_forecast_results",
        main_product_template_id,
        engine=engine,
    )


def get_group_recommendation(
    main_product_template_id: int,
    engine: Engine | None = None,
) -> dict[str, Any] | None:
    return _get_one(
        "group_inventory_recommendations",
        main_product_template_id,
        engine=engine,
    )


def get_all_group_forecasts(
    engine: Engine | None = None,
) -> list[dict[str, Any]]:
    return _get_all("group_forecast_results", engine=engine)


def get_all_group_recommendations(
    engine: Engine | None = None,
) -> list[dict[str, Any]]:
    return _get_all("group_inventory_recommendations", engine=engine)