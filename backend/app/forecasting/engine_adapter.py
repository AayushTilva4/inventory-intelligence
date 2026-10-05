import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

POC_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

def get_forecasting_engine_root() -> Path:
    """Resolve and validate the configured forecasting engine directory."""
    env_path = POC_ROOT / ".env"
    load_dotenv(env_path)

    configured_root = os.getenv("FORECAST_ENGINE_ROOT") or "../forecasting-engine"

    engine_root = Path(configured_root).expanduser()
    if not engine_root.is_absolute():
        engine_root = POC_ROOT / engine_root
    engine_root = engine_root.resolve()

    if not engine_root.is_dir():
        raise RuntimeError(
            f"Forecasting engine directory does not exist: {engine_root} "
            f"(configured by FORECAST_ENGINE_ROOT in {env_path})"
        )

    return engine_root


def load_poc_environment() -> None:
    """Load the POC .env and map its Odoo settings to the legacy engine's
    expected environment variable names.
    """
    env_path = POC_ROOT / ".env"

    load_dotenv(env_path)

    required = [
        "ODOO_DB_HOST",
        "ODOO_DB_PORT",
        "ODOO_DB_NAME",
        "ODOO_DB_USER",
        "ODOO_DB_PASSWORD",
    ]

    missing = [key for key in required if not os.getenv(key)]

    if missing:
        raise RuntimeError(
            f"Missing Odoo configuration in {env_path}: {', '.join(missing)}"
        )

    # Existing engine expects DB_* names.
    os.environ["DB_HOST"] = os.environ["ODOO_DB_HOST"]
    os.environ["DB_PORT"] = os.environ["ODOO_DB_PORT"]
    os.environ["DB_NAME"] = os.environ["ODOO_DB_NAME"]
    os.environ["DB_USER"] = os.environ["ODOO_DB_USER"]
    os.environ["DB_PASSWORD"] = os.environ["ODOO_DB_PASSWORD"]


# ---------------------------------------------------------------------------
# Existing engine
# ---------------------------------------------------------------------------

def load_existing_engine():
    """Make the existing forecasting project importable without modifying it."""
    load_poc_environment()

    engine_root = str(get_forecasting_engine_root())

    if engine_root not in sys.path:
        sys.path.insert(0, engine_root)

    from src.pipeline import forecast_all_products
    from src.similar_products import load_similarity_candidates
    from src.sales_data import (
        create_monthly_sales,
        fetch_product_categories,
        fetch_sales_data,
        fetch_stock_on_hand,
    )

    return {
        "forecast_all_products": forecast_all_products,
        "create_monthly_sales": create_monthly_sales,
        "fetch_product_categories": fetch_product_categories,
        "fetch_sales_data": fetch_sales_data,
        "fetch_stock_on_hand": fetch_stock_on_hand,
	"load_similarity_candidates": load_similarity_candidates,
    }


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------

def load_forecasting_inputs():
    """Fetch the raw Odoo inputs required by the existing forecasting engine."""

    engine = load_existing_engine()

    sales_df = engine["fetch_sales_data"]()
    monthly_df = engine["create_monthly_sales"](sales_df)

    category_map = engine["fetch_product_categories"]()

    stock_df = engine["fetch_stock_on_hand"]()
    similar_candidates_path = (
        get_forecasting_engine_root()
        / "data"
        / "historical_similar_product_candidates.csv"
    )
    if similar_candidates_path.exists():
        similar_candidates = engine["load_similarity_candidates"](
            similar_candidates_path
        )
    else:
        similar_candidates = pd.DataFrame()
    if stock_df.empty:
        stock_map = {}
    else:
        stock_map = dict(
            zip(
                stock_df["product_id"],
                stock_df["stock_on_hand"],
            )
        )

    return {
        "sales_df": sales_df,
        "monthly_df": monthly_df,
        "category_map": category_map,
        "stock_df": stock_df,
        "stock_map": stock_map,
        "similar_candidates": similar_candidates,
    }


# ---------------------------------------------------------------------------
# Forecast execution
# ---------------------------------------------------------------------------

def run_forecast(
    test_size: int = 6,
    season_length: int = 12,
):
    """Run the existing forecasting engine against current Odoo data."""

    engine = load_existing_engine()

    inputs = load_forecasting_inputs()

    results_df = engine["forecast_all_products"](
        inputs["monthly_df"],
        test_size=test_size,
        season_length=season_length,
        category_map=inputs["category_map"],
        stock_map=inputs["stock_map"],
        similar_candidates=inputs["similar_candidates"],
    )

    return results_df