import pandas as pd

from src.similar_products import historical_analogue_forecast, load_similarity_candidates


def test_historical_analogue_forecast_uses_explicit_candidates(tmp_path):
    candidates = pd.DataFrame(
        [
            {
                "new_product_id": 100,
                "old_product_id": 200,
                "old_product_name": "OLD-200",
                "old_selling_months": 12,
                "link_sources": "similar_relation",
            },
            {
                "new_product_id": 100,
                "old_product_id": 201,
                "old_product_name": "OLD-201",
                "old_selling_months": 3,
                "link_sources": "similar_relation",
            },
        ]
    )

    monthly = pd.DataFrame(
        [
            {"month": "2025-01-01", "product_id": 100, "product_name": "NEW-100", "total_quantity": 10},
            {"month": "2025-02-01", "product_id": 100, "product_name": "NEW-100", "total_quantity": 20},
            {"month": "2024-01-01", "product_id": 200, "product_name": "OLD-200", "total_quantity": 5},
            {"month": "2024-02-01", "product_id": 200, "product_name": "OLD-200", "total_quantity": 10},
            {"month": "2024-03-01", "product_id": 200, "product_name": "OLD-200", "total_quantity": 20},
            {"month": "2024-04-01", "product_id": 200, "product_name": "OLD-200", "total_quantity": 40},
        ]
    )
    monthly["month"] = pd.to_datetime(monthly["month"])

    product_df = monthly[monthly["product_id"] == 100].copy()

    result = historical_analogue_forecast(
        product_id=100,
        product_df=product_df,
        monthly_df=monthly,
        similarity_candidates=candidates,
    )

    assert result["status"] == "cold_start_historical_analogue"
    assert result["analogue_count"] == 1
    assert result["analogue_products"] == ["OLD-200"]
    assert result["next_month_forecast"] >= 0


def test_similarity_csv_loader(tmp_path):
    path = tmp_path / "candidates.csv"
    pd.DataFrame(
        [
            {"new_product_id": 1, "old_product_id": 2, "old_selling_months": 6},
        ]
    ).to_csv(path, index=False)

    loaded = load_similarity_candidates(path)
    assert list(loaded.columns) == [
        "new_product_id",
        "old_product_id",
        "old_selling_months",
    ]
