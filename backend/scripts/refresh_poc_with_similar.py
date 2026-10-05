import json
from pathlib import Path

import pandas as pd

from app.db.repository import save_forecasts, save_recommendations
from app.forecasting.engine_adapter import (
    load_existing_engine,
    load_forecasting_inputs,
)
from app.inventory.recommendation_engine import build_recommendation


DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
POC_PRODUCTS = DATA_ROOT / "poc_products.csv"


def json_safe(value):
    """Convert lists/dicts to JSON strings for PostgreSQL persistence."""
    if value is None:
        return None

    if isinstance(value, (dict, list)):
        return json.dumps(value)

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    return value


def main() -> None:
    print("Loading forecasting inputs...")
    inputs = load_forecasting_inputs()

    engine = load_existing_engine()

    poc = pd.read_csv(POC_PRODUCTS)
    product_ids = poc["product_id"].astype(int).tolist()

    print(f"Running forecast for {len(product_ids)} POC products...")

    results = engine["forecast_all_products"](
        inputs["monthly_df"],
        test_size=6,
        season_length=12,
        category_map=inputs["category_map"],
        stock_map=inputs["stock_map"],
        similar_candidates=inputs["similar_candidates"],
        product_ids=product_ids,
    )

    results = results.merge(
        poc[["scenario", "product_id"]],
        on="product_id",
        how="left",
    )

    # Always attach current stock from Odoo for every product.
    results["stock_on_hand"] = results.apply(
        lambda row: inputs["stock_map"].get(
            int(row["product_id"]),
            0.0,
        )
        if pd.isna(row.get("stock_on_hand"))
        else row["stock_on_hand"],
        axis=1,
    )

    recommendation_rows = []

    for _, row in results.iterrows():
        row_data = row.to_dict()

        recommendation = build_recommendation(row_data)
        recommendation["scenario"] = row.get("scenario")
        recommendation["product_id"] = int(row["product_id"])
        recommendation["product_name"] = row.get("product_name")

        recommendation_rows.append(recommendation)

    recommendations = pd.DataFrame(recommendation_rows)

    recommendation_columns = [
        "scenario",
        "product_id",
        "product_name",
        "action",
        "priority",
        "next_month_forecast",
        "current_stock",
        "reorder_point",
        "buffered_target_stock",
        "stock_gap",
        "coverage_ratio",
        "suggested_purchase_qty",
        "reason_codes",
    ]

    recommendations = recommendations[
        [c for c in recommendation_columns if c in recommendations.columns]
    ]

    # Convert Python lists/dicts into database-safe strings.
    for column in results.columns:
        results[column] = results[column].map(json_safe)

    # Store reason_codes in the same brace format expected by
    # repository.py when reading PostgreSQL results.
    if "reason_codes" in recommendations.columns:
        recommendations["reason_codes"] = recommendations[
            "reason_codes"
        ].map(
            lambda value: (
                "{" + ",".join(str(item) for item in value) + "}"
                if isinstance(value, list)
                else value
            )
        )

    print("Saving forecasts to POC PostgreSQL...")
    save_forecasts(results)

    print("Saving recommendations to POC PostgreSQL...")
    save_recommendations(recommendations)

    results.to_csv(DATA_ROOT / "poc_forecasts.csv", index=False)

    recommendations.to_csv(DATA_ROOT / "poc_recommendations.csv", index=False)

    print("Done.")
    print("Odoo was read-only.")
    print("Only the separate POC PostgreSQL database was updated.")


if __name__ == "__main__":
    main()