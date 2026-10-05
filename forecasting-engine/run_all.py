import warnings
from statsmodels.tools.sm_exceptions import ConvergenceWarning
from src.evaluation import build_catalog_actual_vs_forecast
from src.db import get_engine
from src.sales_data import (
    fetch_sales_data,
    create_monthly_sales,
    fetch_product_categories,
    fetch_stock_on_hand,
)
from src.pipeline import forecast_all_products, save_forecasts

warnings.filterwarnings("ignore", category=ConvergenceWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning, module="statsmodels")


def main():
    print("Fetching sales data from PostgreSQL...")
    sales_df = fetch_sales_data()
    print(f"Raw shape: {sales_df.shape}")

    print("\nBuilding monthly sales table...")
    monthly_df = create_monthly_sales(sales_df)
    print(f"Monthly shape: {monthly_df.shape}")
    print(f"Number of products: {monthly_df['product_id'].nunique()}")

    print("\nFetching product categories for cold-start fallback...")
    category_map = fetch_product_categories()
    print(f"Categories found for {len(category_map)} products")

    print("\nFetching stock on hand...")
    stock_df = fetch_stock_on_hand()
    stock_map = dict(zip(stock_df["product_id"], stock_df["stock_on_hand"]))
    print(f"Stock data found for {len(stock_map)} products")

    print("\nRunning forecasts for all products...")
    results_df = forecast_all_products(
        monthly_df,
        test_size=6,
        season_length=12,
        category_map=category_map,
        stock_map=stock_map,
    )
    print("\n" + "="*60)
    print("FORECAST ACCURACY SUMMARY")
    print("="*60)

    ok_df = results_df[results_df["status"] == "ok"].copy()
    real_forecast_df = ok_df[
        (ok_df.get("dead_stock") != True) &
        (ok_df.get("confidence") != "trivial_zero")
    ]
    print(f"\nProducts with a real forecast attempt: {len(ok_df)} / {len(results_df)}")
    print(f"Products excluded (flagged dead stock): {len(ok_df) - len(real_forecast_df)}")

    print("\nMASE distribution (lower is better, <1.0 beats naive guess):")
    print(real_forecast_df["MASE"].describe())

    print("\nAccuracy tiers (% of forecasted products):")
    total = len(real_forecast_df)
    if total > 0:
        excellent = (real_forecast_df["MASE"] < 0.5).sum()
        good = ((real_forecast_df["MASE"] >= 0.5) & (real_forecast_df["MASE"] < 1.0)).sum()
        weak = ((real_forecast_df["MASE"] >= 1.0) & (real_forecast_df["MASE"] < 1.5)).sum()
        poor = (real_forecast_df["MASE"] >= 1.5).sum()

        print(f"  Excellent (MASE < 0.5):        {excellent:5d}  ({excellent/total*100:.1f}%)")
        print(f"  Good      (0.5 <= MASE < 1.0): {good:5d}  ({good/total*100:.1f}%)")
        print(f"  Weak      (1.0 <= MASE < 1.5): {weak:5d}  ({weak/total*100:.1f}%)")
        print(f"  Poor      (MASE >= 1.5):       {poor:5d}  ({poor/total*100:.1f}%)")

    print("\nOverall WAPE distribution (for reference):")
    print(real_forecast_df["WAPE"].describe())

    print("\nConfidence label breakdown (full catalog):")
    print(results_df["confidence"].value_counts(dropna=False))
    print("\nMonths-since-last-sale distribution (products with stock > 0):")
    has_stock = results_df[results_df["stock_on_hand"] > 0]
    print(has_stock["months_since_last_sale"].describe())

    print("\nStatus breakdown:")
    print(results_df["status"].value_counts())

    print("\nDead stock candidates:")
    dead_stock_df = results_df[results_df["dead_stock"] == True]
    print(f"{len(dead_stock_df)} products flagged as dead stock")
    print(dead_stock_df.head(10).to_string(index=False))

    engine = get_engine()
    print("\nBuilding actual-vs-forecast comparison table...")
    comparison_df = build_catalog_actual_vs_forecast(
        monthly_df, test_size=6, season_length=12
    )
    print(f"Comparison rows: {len(comparison_df)} (across {comparison_df['product_id'].nunique()} products)")
    print("\nSample of actual vs forecast:")
    print(comparison_df.head(15).to_string(index=False))

    comparison_df.to_sql("forecast_vs_actual", engine, if_exists="replace", index=False)
    print("Saved comparison table to 'forecast_vs_actual'.")
    save_forecasts(results_df, engine)


if __name__ == "__main__":
    main()
