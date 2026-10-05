from typing import Any
import json
from pathlib import Path
import pandas as pd

from app.forecasting.engine_adapter import (
    load_forecasting_inputs,
    load_existing_engine,
)
from app.inventory.recommendation_engine import build_recommendation
from app.odoo.product_group_service import get_product_group

DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
CANDIDATES_CSV = DATA_ROOT / "historical_similar_product_candidates.csv"
NAME_CANDIDATES_CSV = DATA_ROOT / "historical_similar_product_name_candidates.csv"

_candidates_df = None
_name_candidates_df = None


def _load_candidate_dfs():
    global _candidates_df, _name_candidates_df
    if _candidates_df is None:
        if CANDIDATES_CSV.exists():
            _candidates_df = pd.read_csv(CANDIDATES_CSV)
        else:
            _candidates_df = pd.DataFrame()
    if _name_candidates_df is None:
        if NAME_CANDIDATES_CSV.exists():
            _name_candidates_df = pd.read_csv(NAME_CANDIDATES_CSV)
        else:
            _name_candidates_df = pd.DataFrame()
    return _candidates_df, _name_candidates_df


def get_similar_products_for_id(product_id: int) -> list[dict[str, Any]]:
    df1, df2 = _load_candidate_dfs()
    similars = []
    seen_ids = set()

    # 1. Strong recorded similarity link (df1)
    if not df1.empty:
        m1 = df1[(df1["new_product_id"] == product_id) | (df1["old_product_id"] == product_id)]
        for _, row in m1.iterrows():
            is_new = (row["new_product_id"] == product_id)
            other_id = int(row["old_product_id"] if is_new else row["new_product_id"])
            other_name = str(row["old_product_name"] if is_new else row["new_product_name"])
            if other_id not in seen_ids and other_id != product_id:
                seen_ids.add(other_id)
                similars.append({
                    "product_id": other_id,
                    "product_code": other_name,
                    "product_name": other_name,
                    "relationship": "similar_relation"
                })

    # 2. Weak name/category match (df2)
    if not df2.empty:
        m2 = df2[(df2["new_product_id"] == product_id) | (df2["old_product_id"] == product_id)]
        for _, row in m2.iterrows():
            is_new = (row["new_product_id"] == product_id)
            other_id = int(row["old_product_id"] if is_new else row["new_product_id"])
            other_name = str(row["old_product_name"] if is_new else row["new_product_name"])
            if other_id not in seen_ids and other_id != product_id:
                seen_ids.add(other_id)
                similars.append({
                    "product_id": other_id,
                    "product_code": other_name,
                    "product_name": other_name,
                    "relationship": "weak_name_category_match"
                })

    return similars


def get_product_forecast(product_id: int) -> dict[str, Any]:
    """
    Generate the forecasting engine result for one product.

    Uses the full sales dataset so historical analogue products remain
    available when the requested product has insufficient own history.
    """

    inputs = load_forecasting_inputs()

    monthly_df = inputs["monthly_df"]

    product_df = monthly_df[
        monthly_df["product_id"] == product_id
    ].copy()

    if product_df.empty:
        raise ValueError(f"Product {product_id} not found in sales data")

    engine = load_existing_engine()

    results_df = engine["forecast_all_products"](
        monthly_df,
        test_size=6,
        season_length=12,
        category_map=inputs["category_map"],
        stock_map=inputs["stock_map"],
        similar_candidates=inputs["similar_candidates"],
        product_ids=[product_id],
    )

    if results_df.empty:
        raise ValueError(f"Unable to generate forecast for product {product_id}")

    result = results_df.iloc[0].to_dict()

    product_name = product_df["product_name"].dropna()
    result["product_id"] = product_id
    result["product_name"] = (
        product_name.iloc[0]
        if not product_name.empty
        else result.get("product_name")
    )

    # Ensure both status and forecast_status are available
    if "status" in result and "forecast_status" not in result:
        result["forecast_status"] = result["status"]
    elif "forecast_status" in result and "status" not in result:
        result["status"] = result["forecast_status"]

    # Parse and structure analogue fields if present
    val_prods = result.get("analogue_products")
    if isinstance(val_prods, str):
        try:
            result["analogue_products"] = json.loads(val_prods)
        except Exception:
            result["analogue_products"] = [val_prods]
    elif val_prods is None:
        result["analogue_products"] = None

    val_details = result.get("analogue_details")
    if isinstance(val_details, str):
        try:
            result["analogue_details"] = json.loads(val_details)
        except Exception:
            result["analogue_details"] = None
    elif val_details is None:
        result["analogue_details"] = None

    val_count = result.get("analogue_count")
    if val_count is not None and not pd.isna(val_count):
        try:
            result["analogue_count"] = int(val_count)
        except Exception:
            result["analogue_count"] = None
    else:
        result["analogue_count"] = None

    # Build analogue_history dynamically if analogue details exist
    analogue_history = None
    if isinstance(val_details, list) and len(val_details) > 0:
        primary_analogue = val_details[0]
        old_id = primary_analogue.get("old_product_id")
        if old_id is not None:
            analogue_df = monthly_df[monthly_df["product_id"] == old_id].copy()
            if not analogue_df.empty:
                analogue_df["month"] = pd.to_datetime(analogue_df["month"])
                analogue_df = analogue_df.sort_values("month")
                analogue_history = [
                    {
                        "month": (
                            row["month"].strftime("%Y-%m-%d")
                            if hasattr(row["month"], "strftime")
                            else str(row["month"])[:10]
                        ),
                        "sales_quantity": float(row["total_quantity"])
                    }
                    for _, row in analogue_df.iterrows()
                ]

    result["analogue_history"] = analogue_history
    result["similar_products"] = get_similar_products_for_id(product_id)

    recommendation = build_recommendation(result)
    result["buffered_target_stock"] = recommendation["buffered_target_stock"]

    product_group = get_product_group(product_id)
    if product_group is not None:
        individual_stock = next(
            (
                member
                for member in product_group["group_members"]
                if member["product_id"] == product_id
            ),
            None,
        )
        if individual_stock is not None:
            result["current_stock"] = individual_stock["current_stock"]
            result["usable_qty"] = individual_stock["usable_qty"]
            result["cut_piece_qty"] = individual_stock["cut_piece_qty"]

    # Clean NaNs to None for valid JSON serialization
    for k, v in list(result.items()):
        if not isinstance(v, (list, dict)):
            try:
                if pd.isna(v):
                    result[k] = None
            except Exception:
                pass

    return result