import sys
import time
from pathlib import Path

import pandas as pd


# Allow imports from the POC backend.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))


from app.forecasting.engine_adapter import run_forecast


def main():
    print("=" * 60)
    print("FULL CATALOGUE FORECAST")
    print("=" * 60)

    started_at = time.perf_counter()

    print("Starting forecast...")
    results = run_forecast(
        test_size=6,
        season_length=12,
    )

    elapsed = time.perf_counter() - started_at

    print()
    print("=" * 60)
    print("FORECAST COMPLETE")
    print("=" * 60)

    print(f"Rows returned: {len(results):,}")
    print(f"Time taken:    {elapsed / 60:.2f} minutes")

    if "status" in results.columns:
        print()
        print("Status distribution:")
        print(results["status"].value_counts(dropna=False))

    if "best_model" in results.columns:
        print()
        print("Best model distribution:")
        print(results["best_model"].value_counts(dropna=False))

    if "confidence" in results.columns:
        print()
        print("Confidence distribution:")
        print(results["confidence"].value_counts(dropna=False))

    print()
    print("Sample:")
    print(
        results[
            [
                "product_id",
                "product_name",
                "status",
                "best_model",
                "next_month_forecast",
                "avg_monthly_demand",
                "reorder_point",
                "stock_on_hand",
                "trend",
            ]
        ].head(10).to_string(index=False)
    )

    output_dir = BACKEND_ROOT / "data"
    output_dir.mkdir(exist_ok=True)

    output_path = output_dir / "forecast_snapshot.csv"
    results.to_csv(output_path, index=False)

    print()
    print(f"Snapshot saved to: {output_path}")


if __name__ == "__main__":
    main()