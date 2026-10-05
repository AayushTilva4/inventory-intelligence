import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import psycopg2
from sqlalchemy import inspect, text


# Ensure UTF-8 output when supported
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# Add backend root to Python path so internal app modules can be imported
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def load_environment() -> Path:
    """
    Load environment variables from backend/.env or .env file.
    """
    dotenv_candidates = [
        BACKEND_ROOT / ".env",
        Path.cwd() / ".env",
        Path.cwd() / "backend" / ".env",
    ]
    for candidate in dotenv_candidates:
        if candidate.is_file():
            load_dotenv(dotenv_path=candidate, override=False)
            return candidate

    load_dotenv(override=False)
    return BACKEND_ROOT / ".env"


def get_poc_config() -> dict[str, Any]:
    """
    Read and validate POC database connection configuration.
    """
    host = os.getenv("POC_DB_HOST")
    port = os.getenv("POC_DB_PORT", "5432")
    database = os.getenv("POC_DB_NAME")
    user = os.getenv("POC_DB_USER")
    password = os.getenv("POC_DB_PASSWORD")

    missing = []
    if not host:
        missing.append("POC_DB_HOST")
    if not port:
        missing.append("POC_DB_PORT")
    if not database:
        missing.append("POC_DB_NAME")
    if not user:
        missing.append("POC_DB_USER")
    if password is None:
        missing.append("POC_DB_PASSWORD")

    if missing:
        raise RuntimeError(
            "Missing required POC database configuration in environment / .env:\n"
            + "\n".join(f"  - {key}" for key in missing)
        )

    return {
        "host": host,
        "port": int(port),
        "database": database,
        "user": user,
        "password": password,
    }


def verify_poc_database(poc_config: dict[str, Any]) -> str:
    """
    Directly verify that the POC database exists and can be connected to using POC credentials.
    Fails with a clear message if the database cannot be connected to.
    """
    try:
        conn = psycopg2.connect(
            host=poc_config["host"],
            port=poc_config["port"],
            dbname=poc_config["database"],
            user=poc_config["user"],
            password=poc_config["password"],
            connect_timeout=5,
        )
        conn.close()
        return "EXISTS"
    except Exception as exc:
        db_name = poc_config.get("database", "POC database")
        raise RuntimeError(
            f"POC database '{db_name}' must already exist. "
            f"Create the empty PostgreSQL database first, then rerun setup.ps1.\n"
            f"Connection error: {exc}"
        ) from exc


def ensure_database_and_role(poc_config: dict[str, Any], *args, **kwargs) -> str:
    """
    Compatibility wrapper for verify_poc_database.
    """
    return verify_poc_database(poc_config)


def initialize_application_tables(engine) -> None:
    """
    Create all application-owned tables idempotently using explicit DDL.
    """
    ddl_statements = [
        # 1. Users table (for authentication)
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        # 2. Draft Purchase Orders table
        """
        CREATE TABLE IF NOT EXISTS draft_purchase_orders (
            id SERIAL PRIMARY KEY,
            po_number VARCHAR(255) NOT NULL UNIQUE,
            product_id INT NOT NULL,
            product_name VARCHAR(255),
            quantity NUMERIC NOT NULL,
            status VARCHAR(50) DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        # 3. Dedicated Canonical Main Product Group tables
        """
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
        );
        """,
        """
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
        );
        """,
        # 4. Forecast Benchmark V2 tables
        """
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
        """,
        """
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
        """,
        """
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
        """,
        """
        ALTER TABLE benchmark_forecasts ADD COLUMN IF NOT EXISTS as_of_origin_pattern VARCHAR(50);
        ALTER TABLE benchmark_forecasts ADD COLUMN IF NOT EXISTS current_pattern VARCHAR(50);
        ALTER TABLE benchmark_forecasts ADD COLUMN IF NOT EXISTS mase_scale NUMERIC(12, 4);
        ALTER TABLE benchmark_forecasts ADD COLUMN IF NOT EXISTS scaled_error NUMERIC(12, 4);
        ALTER TABLE benchmark_metrics ADD COLUMN IF NOT EXISTS macro_wape_product NUMERIC(12, 4);
        ALTER TABLE benchmark_metrics ADD COLUMN IF NOT EXISTS macro_wape_horizon NUMERIC(12, 4);
        CREATE INDEX IF NOT EXISTS idx_bm_forecasts_run ON benchmark_forecasts(run_id, product_id, horizon);
        CREATE INDEX IF NOT EXISTS idx_bm_forecasts_model ON benchmark_forecasts(run_id, model, horizon);
        CREATE INDEX IF NOT EXISTS idx_bm_metrics_run ON benchmark_metrics(run_id, aggregation_level, model);
        """,
        # 5. Forecast Results & Inventory Recommendations schema placeholders
        """
        CREATE TABLE IF NOT EXISTS forecast_results (
            status TEXT,
            best_model TEXT,
            ranked_by TEXT,
            "MAE" DOUBLE PRECISION,
            "WAPE" DOUBLE PRECISION,
            "MASE" DOUBLE PRECISION,
            confidence TEXT,
            next_month_forecast DOUBLE PRECISION,
            months_available BIGINT,
            trend TEXT,
            trend_pct_change DOUBLE PRECISION,
            reorder_point DOUBLE PRECISION,
            avg_monthly_demand DOUBLE PRECISION,
            dead_stock BOOLEAN,
            dead_stock_reason TEXT,
            suggested_discount_pct DOUBLE PRECISION,
            months_since_last_sale DOUBLE PRECISION,
            stock_on_hand DOUBLE PRECISION,
            product_id BIGINT,
            product_name TEXT,
            analogue_count DOUBLE PRECISION,
            analogue_products TEXT,
            analogue_details TEXT,
            scenario TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS inventory_recommendations (
            scenario TEXT,
            product_id BIGINT,
            product_name TEXT,
            action TEXT,
            priority TEXT,
            next_month_forecast DOUBLE PRECISION,
            current_stock DOUBLE PRECISION,
            reorder_point DOUBLE PRECISION,
            buffered_target_stock DOUBLE PRECISION,
            stock_gap DOUBLE PRECISION,
            coverage_ratio DOUBLE PRECISION,
            suggested_purchase_qty BIGINT,
            reason_codes TEXT,
            approval_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            approval_updated_at TIMESTAMP NULL
        );
        """,
        # 6. Ensure approval status columns exist on inventory_recommendations
        """
        ALTER TABLE inventory_recommendations
        ADD COLUMN IF NOT EXISTS approval_status VARCHAR(20)
            NOT NULL DEFAULT 'pending';

        ALTER TABLE inventory_recommendations
        ADD COLUMN IF NOT EXISTS approval_updated_at TIMESTAMP NULL;
        """,
    ]

    with engine.begin() as conn:
        for stmt in ddl_statements:
            conn.execute(text(stmt))


def validate_poc_database(engine) -> list[str]:
    """
    Validates that expected tables exist and can be inspected.
    """
    expected_tables = [
        "users",
        "draft_purchase_orders",
        "group_forecast_results",
        "group_inventory_recommendations",
        "benchmark_runs",
        "benchmark_forecasts",
        "benchmark_metrics",
        "forecast_results",
        "inventory_recommendations",
    ]

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    missing = [t for t in expected_tables if t not in existing_tables]
    if missing:
        raise RuntimeError(
            f"Validation failed: The following expected tables are missing: {', '.join(missing)}"
        )

    return sorted(list(existing_tables))


def main() -> int:
    try:
        # Load environment
        load_environment()

        poc_config = get_poc_config()

        # Verify POC database connection
        db_status = verify_poc_database(poc_config)

        # Connect to POC database using POC engine
        from app.db.connection import get_poc_engine
        engine = get_poc_engine()

        # Initialize application tables
        initialize_application_tables(engine)

        # Validate setup
        validate_poc_database(engine)

        # Clear, formatted console output
        print("=" * 50)
        print(" Inventory Intelligence — POC Database Setup")
        print("=" * 50)
        print()
        print(f"[1/4] PostgreSQL connection ........ OK")
        print(f"[2/4] POC database ................. {db_status}")
        print(f"[3/4] Application tables ........... READY")
        print(f"[4/4] Validation ................... OK")
        print()
        print(f"POC database: {poc_config['database']}")

        return 0

    except Exception as exc:
        print("=" * 50, file=sys.stderr)
        print(" Inventory Intelligence — Setup Failed", file=sys.stderr)
        print("=" * 50, file=sys.stderr)
        print(f"\nError: {exc}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
