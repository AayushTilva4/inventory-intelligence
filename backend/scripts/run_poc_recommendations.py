import sys
from pathlib import Path

import pandas as pd


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.inventory.recommendation_engine import build_recommendation


def main():
    input_path = BACKEND_ROOT / "data" / "poc_forecasts.csv"
    output_path = BACKEND_ROOT / "data" / "poc_recommendations.csv"

    if not input_path.exists():
        raise FileNotFoundError(
            f"Forecast file not found: {input_path}"
        )

    df = pd.read_csv(input_path)

    results = []

    for _, row in df.iterrows():
        recommendation = build_recommendation(
            row.to_dict()
        )

        results.append(
            {
                "scenario": row["scenario"],
                "product_id": int(row["product_id"]),
                "product_name": row["product_name"],
                "status": row.get("status"),
                "best_model": row.get("best_model"),
                "forecast": row.get("next_month_forecast"),
                "stock_on_hand": row.get("stock_on_hand"),
                "reorder_point": row.get("reorder_point"),
                "trend": row.get("trend"),
                "confidence": row.get("confidence"),
                **recommendation,
            }
        )

    result_df = pd.DataFrame(results)

    result_df.to_csv(
        output_path,
        index=False,
    )

    print("=" * 70)
    print("POC RECOMMENDATIONS")
    print("=" * 70)

    print(
        result_df[
            [
                "scenario",
                "product_id",
                "product_name",
                "action",
                "priority",
                "forecast",
                "stock_on_hand",
                "buffered_target_stock",
                "suggested_purchase_qty",
                "confidence",
            ]
        ].to_string(index=False)
    )

    print()
    print("Action distribution:")
    print(
        result_df["action"]
        .value_counts()
        .to_string()
    )

    print()
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()