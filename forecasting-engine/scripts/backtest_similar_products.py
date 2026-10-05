"""Exploratory backtest for the historical-analogue cold-start method.

IMPORTANT:
- Reads Odoo only through existing SELECT-only data loaders.
- Never writes to PostgreSQL/Odoo.
- Writes the backtest result only to a local CSV file.

This is an experiment, not a production accuracy report.  The current Odoo
relationship snapshot is treated as fixed while we test whether the linked
older-product histories contain useful predictive information.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from src.sales_data import (
    fetch_sales_data,
    create_monthly_sales,
    fetch_product_categories,
)
from src.similar_products import (
    fetch_historical_similarity_candidates,
    historical_analogue_forecast,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "similar_product_backtest.csv"
MIN_AGE = 1
MAX_AGE = 5


def continuous_series(group: pd.DataFrame, end_month: pd.Timestamp) -> pd.Series:
    group = group.copy()
    group["month"] = pd.to_datetime(group["month"])
    group = group.sort_values("month")
    full = pd.date_range(group["month"].min(), end_month, freq="MS")
    return (
        group.set_index("month")["total_quantity"]
        .reindex(full)
        .fillna(0.0)
        .astype(float)
        .reset_index(drop=True)
    )


def category_baseline(
    product_id: int,
    truncated_monthly: pd.DataFrame,
    category_map: dict,
) -> float:
    category = category_map.get(product_id)
    if category is None:
        return 0.0

    peer_ids = [pid for pid, cat in category_map.items() if cat == category]
    peers = truncated_monthly[truncated_monthly["product_id"].isin(peer_ids)]
    if peers.empty:
        return 0.0

    return float(peers.groupby("month")["total_quantity"].sum().mean())


def mae(actual: np.ndarray, forecast: np.ndarray) -> float:
    return float(np.mean(np.abs(actual - forecast))) if len(actual) else float("nan")


def main() -> None:
    print("Fetching sales data from Odoo (read-only)...")
    sales_df = fetch_sales_data()
    monthly_df = create_monthly_sales(sales_df)
    monthly_df["month"] = pd.to_datetime(monthly_df["month"])
    global_end = monthly_df["month"].max()

    print("Fetching categories (read-only)...")
    category_map = fetch_product_categories()

    print("Fetching historical analogue links (read-only)...")
    candidates = fetch_historical_similarity_candidates(
        recent_months=12,
        min_old_selling_months=6,
    )

    recent_new_ids = candidates["new_product_id"].dropna().astype(int).unique()
    rows = []

    for product_id in recent_new_ids:
        group = monthly_df[monthly_df["product_id"] == product_id].copy()
        if group.empty:
            continue

        full = continuous_series(group, global_end)
        product_start = pd.to_datetime(group["month"].min())

        max_age = min(MAX_AGE, len(full) - 1)
        if max_age < MIN_AGE:
            continue

        for age in range(MIN_AGE, max_age + 1):
            cutoff_month = product_start + pd.DateOffset(months=age - 1)
            target_pos = age
            if target_pos >= len(full):
                continue

            observed_end = cutoff_month
            observed_monthly = monthly_df[monthly_df["month"] <= observed_end].copy()
            product_observed = group[group["month"] <= observed_end].copy()
            product_observed = product_observed.sort_values("month").reset_index(drop=True)
            product_observed["total_quantity"] = product_observed["total_quantity"].astype(float)

            # Ensure the observed product series is continuous from its first
            # sale through the cutoff, without exposing target/future months.
            observed_full_months = pd.date_range(
                product_start,
                observed_end,
                freq="MS",
            )
            product_observed = (
                product_observed.set_index("month")["total_quantity"]
                .reindex(observed_full_months)
                .fillna(0.0)
                .rename_axis("month")
                .reset_index()
            )
            product_observed["product_id"] = product_id

            analogue = historical_analogue_forecast(
                product_id=product_id,
                product_df=product_observed,
                monthly_df=observed_monthly,
                similarity_candidates=candidates,
            )

            analogue_forecast = (
                float(analogue["next_month_forecast"])
                if analogue["status"] == "cold_start_historical_analogue"
                else np.nan
            )

            own_forecast = float(product_observed["total_quantity"].tail(min(3, age)).mean())
            category_forecast = category_baseline(product_id, observed_monthly, category_map)
            actual = float(full.iloc[target_pos])

            rows.append(
                {
                    "product_id": product_id,
                    "product_name": group["product_name"].dropna().iloc[0]
                    if not group["product_name"].dropna().empty
                    else str(product_id),
                    "forecast_age_months": age,
                    "cutoff_month": observed_end,
                    "target_month": product_start + pd.DateOffset(months=age),
                    "actual": actual,
                    "analogue_forecast": analogue_forecast,
                    "own_recent_avg": own_forecast,
                    "category_baseline": category_forecast,
                    "analogue_count": analogue.get("analogue_count", 0),
                    "analogue_status": analogue["status"],
                }
            )

    result = pd.DataFrame(rows)
    if result.empty:
        print("No backtest rows were generated.")
        return

    result.to_csv(OUTPUT, index=False)

    print("\n" + "=" * 70)
    print("SIMILAR-PRODUCT BACKTEST")
    print("=" * 70)
    print(f"Rows tested: {len(result)}")
    print(f"Products tested: {result['product_id'].nunique()}")
    print(
        f"Rows with usable historical analogue: "
        f"{result['analogue_forecast'].notna().sum()} / {len(result)}"
    )

    usable = result[result["analogue_forecast"].notna()].copy()
    if not usable.empty:
        actual = usable["actual"].to_numpy(float)
        print(f"Analogue MAE:       {mae(actual, usable['analogue_forecast'].to_numpy(float)):.3f}")
        print(f"Own recent avg MAE:  {mae(actual, usable['own_recent_avg'].to_numpy(float)):.3f}")
        print(f"Category baseline MAE:{mae(actual, usable['category_baseline'].to_numpy(float)):.3f}")

    print(f"\nSaved local backtest CSV: {OUTPUT}")
    print("No PostgreSQL/Odoo table was written or changed.")


if __name__ == "__main__":
    main()
