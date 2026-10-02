import sys
from pathlib import Path

import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.inventory.recommendation_engine import build_recommendation


def main():
    input_path = BACKEND_ROOT / "data" / "poc_forecasts.csv"

    df = pd.read_csv(input_path)

    print("=" * 80)
    print("POC INVENTORY INTELLIGENCE")
    print("=" * 80)

    for _, row in df.iterrows():
        recommendation = build_recommendation(row.to_dict())

        print()
        print("-" * 80)
        print(
            f"{row['product_name']} "
            f"(ID: {int(row['product_id'])})"
        )
        print(f"Scenario       : {row['scenario']}")
        print(f"Forecast       : {row['next_month_forecast']}")
        print(f"Stock          : {row['stock_on_hand']}")
        print(f"Reorder point  : {row['reorder_point']}")
        print(
            f"Buffered target: "
            f"{recommendation['buffered_target_stock']}"
        )
        print(f"Action         : {recommendation['action'].upper()}")
        print(f"Priority       : {recommendation['priority'].upper()}")

        print(
            f"Suggested qty  : "
            f"{recommendation['suggested_purchase_qty']}"
        )

        print(
            f"Confidence     : {row.get('confidence')}"
        )

        print(
            "Reasons        : "
            + ", ".join(recommendation["reason_codes"])
        )


if __name__ == "__main__":
    main()