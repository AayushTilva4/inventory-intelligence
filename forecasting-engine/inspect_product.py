import pandas as pd
import matplotlib.pyplot as plt

from src.sales_data import fetch_sales_data, create_monthly_sales, complete_product_series
from src.evaluation import build_actual_vs_forecast_table

# ---- Change this to inspect a different product ----
SELECTED_PRODUCT_ID = 1544
TEST_SIZE = 6
SEASON_LENGTH = 12


def main():
    print("Fetching sales data...")
    sales_df = fetch_sales_data()
    monthly_df = create_monthly_sales(sales_df)

    product_df = monthly_df[monthly_df["product_id"] == SELECTED_PRODUCT_ID].copy()
    if product_df.empty:
        raise ValueError(f"No sales data found for product {SELECTED_PRODUCT_ID}.")

    product_df = complete_product_series(product_df)
    product_df["month"] = pd.to_datetime(product_df["month"])
    product_df = product_df.sort_values("month").reset_index(drop=True)

    product_name = product_df["product_name"].dropna().iloc[0]
    print(f"\nProduct: {product_name} (ID {SELECTED_PRODUCT_ID})")
    print(f"Months of history: {len(product_df)}")

    comparison = build_actual_vs_forecast_table(
        product_df, test_size=TEST_SIZE, season_length=SEASON_LENGTH
    )

    print("\nActual vs forecast (test period):")
    print(comparison.to_string(index=False))

    print("\nModel evaluation:")
    print(comparison.attrs["evaluation"].to_string(index=False))

    best_model = comparison.attrs["best_model"]
    print(f"\nBest model: {best_model} (ranked by {comparison.attrs['ranked_by']})")

    # ---- Plot ----
    plt.figure(figsize=(12, 6))
    plt.plot(product_df["month"], product_df["total_quantity"], marker="o", label="Actual (full history)")

    for col in comparison.columns:
        if col in ("month", "actual"):
            continue
        width = 3 if col == best_model else 1
        label = f"{col} (BEST)" if col == best_model else col
        plt.plot(comparison["month"], comparison[col], marker="o", linewidth=width, label=label)

    plt.title(f"Forecast vs Actual — {product_name}")
    plt.xlabel("Month")
    plt.ylabel("Quantity Sold")
    plt.xticks(rotation=45)
    plt.legend()
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()