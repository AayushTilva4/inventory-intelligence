import sys
import time
from pathlib import Path

import pandas as pd


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.forecasting.engine_adapter import load_forecasting_inputs, load_existing_engine


def main():
    print("=" * 70)
    print("POC FORECAST RUN")
    print("=" * 70)

    poc_file = BACKEND_ROOT / "data" / "poc_products.csv"

    if not poc_file.exists():
        raise FileNotFoundError(f"POC product file not found: {poc_file}")

    poc_products = pd.read_csv(poc_file)

    inputs = load_forecasting_inputs()
    engine = load_existing_engine()

    monthly_df = inputs["monthly_df"]
    category_map = inputs["category_map"]
    stock_map = inputs["stock_map"]

    from src.sales_data import complete_product_series
    from src.pipeline import forecast_product, cold_start_fallback

    global_end_month = pd.to_datetime(monthly_df["month"]).max()

    results = []

    started = time.perf_counter()

    for _, selected in poc_products.iterrows():
        product_id = int(selected["product_id"])
        scenario = selected["scenario"]

        print(f"\n[{scenario}] product_id={product_id}")

        product_df = monthly_df[
            monthly_df["product_id"] == product_id
        ].copy()

        if product_df.empty:
            print("  ERROR: product not found in monthly sales data")
            continue

        product_series = complete_product_series(
            product_df,
            end_date=global_end_month,
        )

        product_series["month"] = pd.to_datetime(
            product_series["month"]
        )

        product_series = (
            product_series
            .sort_values("month")
            .reset_index(drop=True)
        )

        stock_on_hand = float(
            stock_map.get(product_id, 0.0)
        )

        result = forecast_product(
            product_series,
            test_size=6,
            season_length=12,
            stock_on_hand=stock_on_hand,
        )

        # Use the existing category fallback for insufficient history.
        if result["status"] == "insufficient_history":
            fallback = cold_start_fallback(
                product_id,
                monthly_df,
                category_map,
            )
            result.update(fallback)

            # Preserve inventory information that the legacy
            # cold-start fallback does not return.
            result["stock_on_hand"] = stock_on_hand

        name_series = product_df["product_name"].dropna()

        product_name = (
            name_series.iloc[0]
            if not name_series.empty
            else None
        )

        results.append(
            {
                "scenario": scenario,
                "product_id": product_id,
                "product_name": product_name,
                **result,
            }
        )

        print(f"  status:   {result.get('status')}")
        print(f"  model:    {result.get('best_model')}")
        print(f"  forecast: {result.get('next_month_forecast')}")
        print(f"  stock:    {result.get('stock_on_hand')}")
        print(f"  reorder:  {result.get('reorder_point')}")

    results_df = pd.DataFrame(results)

    output_dir = BACKEND_ROOT / "data"
    output_dir.mkdir(exist_ok=True)

    output_path = output_dir / "poc_forecasts.csv"
    results_df.to_csv(output_path, index=False)

    elapsed = time.perf_counter() - started

    print()
    print("=" * 70)
    print("POC FORECAST COMPLETE")
    print("=" * 70)

    print(f"Products forecast: {len(results_df)}")
    print(f"Time taken:        {elapsed:.2f} seconds")
    print(f"Saved to:          {output_path}")

    print()
    print(
        results_df[
            [
                "scenario",
                "product_id",
                "product_name",
                "status",
                "best_model",
                "next_month_forecast",
                "stock_on_hand",
                "reorder_point",
                "trend",
                "confidence",
                "dead_stock",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()