"""
Database management for Forecast Benchmark V2.
Stores benchmark runs, forecasts, and metrics in the separate POC PostgreSQL database.
"""

import json
from typing import Any, Sequence
import pandas as pd
from sqlalchemy import text, Engine

from app.db.connection import get_poc_engine


def init_benchmark_tables(engine: Engine | None = None) -> None:
    """
    Creates the required benchmark tables and indexes in the POC PostgreSQL database if they do not exist.
    """
    if engine is None:
        engine = get_poc_engine()

    ddl = """
    CREATE TABLE IF NOT EXISTS benchmark_runs (
        run_id VARCHAR(64) PRIMARY KEY,
        run_name VARCHAR(255) NOT NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'running',
        num_products INT NOT NULL DEFAULT 0,
        models JSONB NOT NULL,
        horizons JSONB NOT NULL,
        num_origins INT NOT NULL DEFAULT 0,
        total_evaluations INT NOT NULL DEFAULT 0,
        best_overall_model VARCHAR(100),
        runtime_seconds NUMERIC(10, 2),
        config JSONB,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS benchmark_forecasts (
        id SERIAL PRIMARY KEY,
        run_id VARCHAR(64) NOT NULL REFERENCES benchmark_runs(run_id) ON DELETE CASCADE,
        product_id INT NOT NULL,
        product_name VARCHAR(255),
        demand_pattern VARCHAR(50),
        as_of_origin_pattern VARCHAR(50),
        current_pattern VARCHAR(50),
        origin_date DATE NOT NULL,
        target_date DATE NOT NULL,
        horizon INT NOT NULL,
        model VARCHAR(100) NOT NULL,
        actual NUMERIC(12, 2) NOT NULL,
        forecast NUMERIC(12, 2) NOT NULL,
        error NUMERIC(12, 2) NOT NULL,
        abs_error NUMERIC(12, 2) NOT NULL,
        sq_error NUMERIC(16, 2) NOT NULL,
        mase_scale NUMERIC(12, 4),
        scaled_error NUMERIC(12, 4),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS benchmark_metrics (
        id SERIAL PRIMARY KEY,
        run_id VARCHAR(64) NOT NULL REFERENCES benchmark_runs(run_id) ON DELETE CASCADE,
        aggregation_level VARCHAR(50) NOT NULL,
        product_id INT,
        product_name VARCHAR(255),
        demand_pattern VARCHAR(50),
        model VARCHAR(100),
        horizon INT,
        sample_count INT NOT NULL,
        mae NUMERIC(12, 4),
        wape NUMERIC(12, 4),
        macro_wape_product NUMERIC(12, 4),
        macro_wape_horizon NUMERIC(12, 4),
        mase NUMERIC(12, 4),
        rmse NUMERIC(12, 4),
        bias NUMERIC(12, 4),
        under_forecast_rate NUMERIC(6, 4),
        over_forecast_rate NUMERIC(6, 4),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Schema migrations for existing tables
    ALTER TABLE benchmark_forecasts ADD COLUMN IF NOT EXISTS as_of_origin_pattern VARCHAR(50);
    ALTER TABLE benchmark_forecasts ADD COLUMN IF NOT EXISTS current_pattern VARCHAR(50);
    ALTER TABLE benchmark_forecasts ADD COLUMN IF NOT EXISTS mase_scale NUMERIC(12, 4);
    ALTER TABLE benchmark_forecasts ADD COLUMN IF NOT EXISTS scaled_error NUMERIC(12, 4);
    ALTER TABLE benchmark_metrics ADD COLUMN IF NOT EXISTS macro_wape_product NUMERIC(12, 4);
    ALTER TABLE benchmark_metrics ADD COLUMN IF NOT EXISTS macro_wape_horizon NUMERIC(12, 4);

    CREATE INDEX IF NOT EXISTS idx_bm_forecasts_run ON benchmark_forecasts(run_id, product_id, horizon);
    CREATE INDEX IF NOT EXISTS idx_bm_forecasts_model ON benchmark_forecasts(run_id, model, horizon);
    CREATE INDEX IF NOT EXISTS idx_bm_metrics_run ON benchmark_metrics(run_id, aggregation_level, model);
    """

    with engine.begin() as conn:
        conn.execute(text(ddl))


def save_benchmark_run(run_data: dict[str, Any], engine: Engine | None = None) -> None:
    """
    Inserts or updates a benchmark run record in benchmark_runs.
    """
    if engine is None:
        engine = get_poc_engine()

    query = text("""
        INSERT INTO benchmark_runs (
            run_id, run_name, status, num_products, models, horizons,
            num_origins, total_evaluations, best_overall_model,
            runtime_seconds, config, created_at
        ) VALUES (
            :run_id, :run_name, :status, :num_products, :models, :horizons,
            :num_origins, :total_evaluations, :best_overall_model,
            :runtime_seconds, :config, CURRENT_TIMESTAMP
        )
        ON CONFLICT (run_id) DO UPDATE SET
            status = EXCLUDED.status,
            total_evaluations = EXCLUDED.total_evaluations,
            best_overall_model = EXCLUDED.best_overall_model,
            runtime_seconds = EXCLUDED.runtime_seconds,
            config = EXCLUDED.config;
    """)

    with engine.begin() as conn:
        conn.execute(
            query,
            {
                "run_id": run_data["run_id"],
                "run_name": run_data["run_name"],
                "status": run_data.get("status", "completed"),
                "num_products": run_data["num_products"],
                "models": json.dumps(run_data["models"]),
                "horizons": json.dumps(run_data["horizons"]),
                "num_origins": run_data["num_origins"],
                "total_evaluations": run_data.get("total_evaluations", 0),
                "best_overall_model": run_data.get("best_overall_model"),
                "runtime_seconds": run_data.get("runtime_seconds"),
                "config": json.dumps(run_data.get("config", {})),
            },
        )


def save_benchmark_forecasts(
    forecast_rows: Sequence[dict[str, Any]],
    engine: Engine | None = None,
) -> None:
    """
    Bulk saves benchmark forecast evaluations into benchmark_forecasts.
    """
    if not forecast_rows:
        return

    if engine is None:
        engine = get_poc_engine()

    df = pd.DataFrame(forecast_rows)
    df.to_sql("benchmark_forecasts", engine, if_exists="append", index=False)


def save_benchmark_metrics(
    metric_rows: Sequence[dict[str, Any]],
    engine: Engine | None = None,
) -> None:
    """
    Bulk saves precomputed benchmark metrics into benchmark_metrics.
    """
    if not metric_rows:
        return

    if engine is None:
        engine = get_poc_engine()

    df = pd.DataFrame(metric_rows)
    df.to_sql("benchmark_metrics", engine, if_exists="append", index=False)
