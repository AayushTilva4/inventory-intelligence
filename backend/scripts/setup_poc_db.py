import os
import sys
from pathlib import Path
from typing import Any, Tuple

from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
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


def get_admin_config(poc_config: dict[str, Any]) -> dict[str, Any]:
    """
    Read optional PostgreSQL administrator credentials.
    Defaults host and port to the POC configuration and maintenance DB to 'postgres'.
    """
    host = os.getenv("PG_ADMIN_HOST") or poc_config["host"]
    port = os.getenv("PG_ADMIN_PORT") or str(poc_config["port"])
    database = os.getenv("PG_ADMIN_DB", "postgres")
    user = os.getenv("PG_ADMIN_USER", "postgres")
    password = os.getenv("PG_ADMIN_PASSWORD") or os.getenv("POSTGRES_PASSWORD") or os.getenv("PGPASSWORD")

    return {
        "host": host,
        "port": int(port),
        "database": database,
        "user": user,
        "password": password,
    }


def _check_db_and_role_exists(cursor, db_name: str, role_name: str) -> Tuple[bool, bool]:
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s;", (role_name,))
    role_exists = cursor.fetchone() is not None

    cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (db_name,))
    db_exists = cursor.fetchone() is not None

    return db_exists, role_exists


def ensure_database_and_role(
    poc_config: dict[str, Any],
    admin_config: dict[str, Any],
) -> str:
    """
    Ensures that the POC database and user role exist without dropping any existing database.
    Returns: 'EXISTS' or 'CREATED'.
    """
    # 1. First test if we can directly connect to the target POC database with POC credentials
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
    except psycopg2.OperationalError as op_err:
        err_msg = str(op_err)
        # Check if server is completely unreachable
        if "could not connect to server" in err_msg.lower() or "connection refused" in err_msg.lower():
            raise RuntimeError(
                f"Cannot connect to PostgreSQL server at {poc_config['host']}:{poc_config['port']}.\n"
                "Please verify that the PostgreSQL service is running and accepting connections."
            ) from op_err

    # 2. Database or role does not exist or requires creation.
    # Try connecting to the maintenance database ('postgres' or admin db) to inspect/create.
    maintenance_conn = None
    is_admin = False

    # Attempt A: Try with POC credentials on maintenance db (e.g. if POC user has CREATEDB)
    try:
        maintenance_conn = psycopg2.connect(
            host=poc_config["host"],
            port=poc_config["port"],
            dbname="postgres",
            user=poc_config["user"],
            password=poc_config["password"],
            connect_timeout=5,
        )
    except psycopg2.Error:
        maintenance_conn = None

    # Attempt B: If POC credentials did not work, try admin credentials
    if maintenance_conn is None and admin_config.get("password") is not None:
        try:
            maintenance_conn = psycopg2.connect(
                host=admin_config["host"],
                port=admin_config["port"],
                dbname=admin_config["database"],
                user=admin_config["user"],
                password=admin_config["password"],
                connect_timeout=5,
            )
            is_admin = True
        except psycopg2.Error:
            maintenance_conn = None

    # Attempt C: Try admin user with no password if not set
    if maintenance_conn is None and admin_config.get("password") is None:
        try:
            maintenance_conn = psycopg2.connect(
                host=admin_config["host"],
                port=admin_config["port"],
                dbname=admin_config["database"],
                user=admin_config["user"],
                connect_timeout=5,
            )
            is_admin = True
        except psycopg2.Error:
            maintenance_conn = None

    if maintenance_conn is None:
        raise RuntimeError(
            f"Cannot connect to the POC database '{poc_config['database']}' or create it.\n\n"
            "If this is the first-time setup and the database/user has not been created yet,\n"
            "please set PostgreSQL administrator credentials in your environment or backend/.env:\n"
            "  PG_ADMIN_USER=postgres\n"
            "  PG_ADMIN_PASSWORD=<your_postgres_admin_password>\n"
            "  PG_ADMIN_HOST=localhost (optional, defaults to POC_DB_HOST)\n"
            "  PG_ADMIN_PORT=5432 (optional, defaults to POC_DB_PORT)\n"
            "  PG_ADMIN_DB=postgres (optional, defaults to 'postgres')"
        )

    try:
        maintenance_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        with maintenance_conn.cursor() as cur:
            db_exists, role_exists = _check_db_and_role_exists(
                cur,
                poc_config["database"],
                poc_config["user"],
            )

            # Create missing role if using admin connection
            if not role_exists:
                if not is_admin:
                    raise RuntimeError(
                        f"Role '{poc_config['user']}' does not exist and current connection lacks "
                        "admin permissions to create roles. Please provide PG_ADMIN_PASSWORD."
                    )
                create_role_stmt = sql.SQL(
                    "CREATE ROLE {} WITH LOGIN PASSWORD {};"
                ).format(
                    sql.Identifier(poc_config["user"]),
                    sql.Literal(poc_config["password"]),
                )
                cur.execute(create_role_stmt)

            # Create missing database
            if not db_exists:
                create_db_stmt = sql.SQL(
                    "CREATE DATABASE {} OWNER {};"
                ).format(
                    sql.Identifier(poc_config["database"]),
                    sql.Identifier(poc_config["user"]),
                )
                cur.execute(create_db_stmt)
                return "CREATED"
            else:
                return "EXISTS"
    finally:
        maintenance_conn.close()


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
        admin_config = get_admin_config(poc_config)

        # Ensure database & user role exist
        db_status = ensure_database_and_role(poc_config, admin_config)

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
