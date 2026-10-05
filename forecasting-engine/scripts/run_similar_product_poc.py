"""Run the similar-product forecast for the existing local 10-product POC.

This script only reads the local Odoo database.  Forecast output is saved as
CSV under ``data/``; no PostgreSQL/Odoo table is written.
"""

from pathlib import Path

import pandas as pd

from src.pipeline import forecast_all_products
from src.sales_data import (
    fetch_sales_data,
    create_monthly_sales,
    fetch_product_categories,
    fetch_stock_on_hand,
)
from src.similar_products import load_similarity_candidates


ROOT = Path(__file__).resolve().parents[1]
POC_PRODUCTS = ROOT / "data" / "poc_products.csv"
CANDIDATES = ROOT / "data" / "historical_similar_product_candidates.csv"
OUTPUT = ROOT / "data" / "similar_product_poc_forecasts.csv"


def main() -> None:
    poc = pd.read_csv(POC_PRODUCTS)
    product_ids = poc["product_id"].astype(int).tolist()

    print("Fetching sales data from local Odoo (read-only)...")
    sales_df = fetch_sales_data()
    monthly_df = create_monthly_sales(sales_df)
    monthly_df["month"] = pd.to_datetime(monthly_df["month"])

    print("Fetching categories (read-only)...")
    category_map = fetch_product_categories()

    print("Fetching current stock (read-only)...")
    stock_df = fetch_stock_on_hand()
    stock_map = dict(zip(stock_df["product_id"], stock_df["stock_on_hand"]))

    candidates = load_similarity_candidates(CANDIDATES)

    print(f"Running similar-product forecast for {len(product_ids)} POC products...")
    # monthly_df = monthly_df[monthly_df["product_id"].isin(product_ids)].copy()
    results = forecast_all_products(
        monthly_df=monthly_df,
        test_size=6,
        season_length=12,
        category_map=category_map,
        stock_map=stock_map,
        similar_candidates=candidates,
        product_ids=product_ids,
    )

    results = results.merge(
        poc[["scenario", "product_id"]],
        on="product_id",
        how="left",
    )
    results.to_csv(OUTPUT, index=False)

    print("\nPOC forecast result:")
    columns = [
        "scenario",
        "product_id",
        "product_name",
        "status",
        "next_month_forecast",
        "confidence",
        "analogue_count",
        "analogue_products",
    ]
    print(results[[c for c in columns if c in results.columns]].to_string(index=False))
    print(f"\nSaved local result: {OUTPUT}")
    print("No PostgreSQL/Odoo table was written or changed.")


if __name__ == "__main__":
    main()
