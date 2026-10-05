import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import text

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


def validate_environment() -> None:
    """
    Verify all required environment variables for Odoo, POC DB, and forecasting engine.
    """
    required_odoo = [
        "ODOO_DB_HOST",
        "ODOO_DB_PORT",
        "ODOO_DB_NAME",
        "ODOO_DB_USER",
        "ODOO_DB_PASSWORD",
    ]
    required_poc = [
        "POC_DB_HOST",
        "POC_DB_PORT",
        "POC_DB_NAME",
        "POC_DB_USER",
        "POC_DB_PASSWORD",
    ]

    missing_odoo = [key for key in required_odoo if not os.getenv(key)]
    missing_poc = [key for key in required_poc if not os.getenv(key)]

    if missing_odoo or missing_poc:
        err_parts = []
        if missing_odoo:
            err_parts.append(f"Missing Odoo variables: {', '.join(missing_odoo)}")
        if missing_poc:
            err_parts.append(f"Missing POC DB variables: {', '.join(missing_poc)}")
        raise RuntimeError("Environment configuration error:\n" + "\n".join(err_parts))

    # Verify FORECAST_ENGINE_ROOT
    from app.forecasting.engine_adapter import get_forecasting_engine_root
    get_forecasting_engine_root()


def validate_odoo_connection() -> None:
    """
    Preflight check: verifies read-only access to the configured Odoo database
    by querying the primary tables required by the forecasting engine.
    """
    try:
        from app.odoo.product_group_service import _get_odoo_engine
        engine = _get_odoo_engine()

        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM product_product LIMIT 1;"))
            conn.execute(text("SELECT 1 FROM product_template LIMIT 1;"))
            conn.execute(text("SELECT 1 FROM sale_order LIMIT 1;"))
            conn.execute(text("SELECT 1 FROM stock_quant LIMIT 1;"))
    except Exception as exc:
        raise RuntimeError(
            "Odoo connection failed.\n"
            "Check ODOO_DB_HOST, ODOO_DB_PORT, ODOO_DB_NAME, ODOO_DB_USER and ODOO_DB_PASSWORD."
        ) from exc


def setup_poc_database() -> str:
    """
    Idempotently initialize/verify the POC PostgreSQL database and application tables.
    """
    try:
        from scripts.setup_poc_db import (
            get_poc_config,
            verify_poc_database,
            initialize_application_tables,
            validate_poc_database,
        )
        from app.db.connection import get_poc_engine

        poc_config = get_poc_config()
        db_status = verify_poc_database(poc_config)

        engine = get_poc_engine()
        initialize_application_tables(engine)
        validate_poc_database(engine)

        return db_status
    except Exception as exc:
        raise RuntimeError(
            f"POC database setup failed.\n"
            f"Check POC_DB_HOST, POC_DB_PORT, POC_DB_NAME, POC_DB_USER and POC_DB_PASSWORD.\n"
            f"Details: {exc}"
        ) from exc


def refresh_product_intelligence() -> int:
    """
    Run the existing individual-product forecast/recommendation refresh path.
    Returns the number of products refreshed.
    """
    try:
        from scripts.refresh_poc_with_similar import main as refresh_poc_main

        # Determine product count from POC product set
        poc_csv = BACKEND_ROOT / "data" / "poc_products.csv"
        if poc_csv.exists():
            df_poc = pd.read_csv(poc_csv)
            product_count = len(df_poc)
        else:
            product_count = 10

        refresh_poc_main()
        return product_count
    except Exception as exc:
        raise RuntimeError(
            f"Product forecast/recommendation refresh failed.\n"
            f"Stage: product forecast & recommendation refresh\n"
            f"Details: {exc}"
        ) from exc


def refresh_group_intelligence() -> int:
    """
    Run the existing main-product group forecast/recommendation refresh path.
    Returns the number of main-product groups refreshed.
    """
    try:
        from scripts.refresh_group_poc import refresh_groups, DEFAULT_TEMPLATE_IDS

        forecasts_cnt, recs_cnt, skipped_cnt = refresh_groups(list(DEFAULT_TEMPLATE_IDS))
        return forecasts_cnt
    except Exception as exc:
        raise RuntimeError(
            f"Main-product group forecast/recommendation refresh failed.\n"
            f"Stage: group forecast & recommendation refresh\n"
            f"Details: {exc}"
        ) from exc


def validate_initial_data() -> None:
    """
    Validate that forecast, recommendation, and group rows were written
    and that repository APIs can query the data.
    """
    from app.db.connection import get_poc_engine
    from app.db.repository import get_recommendations, get_all_draft_pos
    from app.db.group_repository import get_all_group_recommendations

    engine = get_poc_engine()
    with engine.connect() as conn:
        f_count = conn.execute(text("SELECT COUNT(*) FROM forecast_results;")).scalar()
        r_count = conn.execute(text("SELECT COUNT(*) FROM inventory_recommendations;")).scalar()
        gf_count = conn.execute(text("SELECT COUNT(*) FROM group_forecast_results;")).scalar()
        gr_count = conn.execute(text("SELECT COUNT(*) FROM group_inventory_recommendations;")).scalar()

    if f_count == 0 or r_count == 0:
        raise RuntimeError(
            f"Validation error: Expected individual product forecast/recommendation rows, "
            f"got forecast_results={f_count}, inventory_recommendations={r_count}."
        )

    if gf_count == 0 or gr_count == 0:
        raise RuntimeError(
            f"Validation error: Expected main-product group forecast/recommendation rows, "
            f"got group_forecast_results={gf_count}, group_inventory_recommendations={gr_count}."
        )

    # Test repository API queries
    recs = get_recommendations()
    if not recs:
        raise RuntimeError("Validation error: get_recommendations() returned empty list.")

    group_recs = get_all_group_recommendations()
    if not group_recs:
        raise RuntimeError("Validation error: get_all_group_recommendations() returned empty list.")

    # draft PO query test (can be empty, but must not error)
    get_all_draft_pos()


def main() -> int:
    try:
        # Step 1: Environment
        load_environment()
        validate_environment()

        # Step 2: Odoo Read-only Connection
        validate_odoo_connection()

        # Step 3: POC Database Setup
        setup_poc_database()

        # Step 4: Product Intelligence Refresh
        product_count = refresh_product_intelligence()

        # Step 5: Main-product Group Intelligence Refresh
        group_count = refresh_group_intelligence()

        # Step 6: Validation
        validate_initial_data()

        # Print clean, concise summary output
        print("=" * 50)
        print(" Inventory Intelligence — Initial Data Setup")
        print("=" * 50)
        print()
        print("[1/6] Environment .................. OK")
        print("[2/6] Odoo connection .............. OK")
        print("[3/6] POC database ................. OK")
        print(f"[4/6] Product intelligence ......... {product_count} products")
        print(f"[5/6] Main-product intelligence .... {group_count} groups")
        print("[6/6] Validation ................... OK")
        print()
        print("Initial data setup completed successfully.")

        return 0

    except Exception as exc:
        print("=" * 50, file=sys.stderr)
        print(" Inventory Intelligence — Initial Setup Failed", file=sys.stderr)
        print("=" * 50, file=sys.stderr)
        print(f"\nError: {exc}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
