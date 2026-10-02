import sys
from pathlib import Path

import pandas as pd


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.repository import save_forecasts, save_recommendations
from app.inventory.recommendation_engine import build_recommendation


def main():
    forecast_path = BACKEND_ROOT / "data" / "poc_forecasts.csv"

    forecasts = pd.read_csv(forecast_path)

    recommendation_rows = []

    for _, row in forecasts.iterrows():
        recommendation = build_recommendation(
            row.to_dict()
        )

        recommendation_rows.append(
            {
                "scenario": row["scenario"],
                "product_id": int(row["product_id"]),
                "product_name": row["product_name"],
                **recommendation,
            }
        )

    recommendations = pd.DataFrame(
        recommendation_rows
    )

    save_forecasts(forecasts)
    save_recommendations(recommendations)

    print("=" * 60)
    print("POC SNAPSHOT SAVED")
    print("=" * 60)
    print(f"Forecast rows       : {len(forecasts)}")
    print(f"Recommendation rows : {len(recommendations)}")


if __name__ == "__main__":
    main()