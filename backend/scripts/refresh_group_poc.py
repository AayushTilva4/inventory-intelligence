import argparse
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.connection import get_poc_engine
from app.db.group_repository import (
    create_group_tables,
    upsert_group_forecast,
    upsert_group_recommendation,
)
from app.forecasting.group_forecast_service import get_group_forecast
from app.inventory.group_recommendation_service import get_group_recommendation
from app.odoo.product_group_service import _get_odoo_engine


DEFAULT_TEMPLATE_IDS = (405, 1544, 1562, 1584, 7353, 10673)


def discover_canonical_multi_member_groups() -> list[int]:
    engine = _get_odoo_engine()
    try:
        with engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT canonical.id
                FROM product_template canonical
                JOIN product_template member
                    ON member.main_product = canonical.id
                WHERE canonical.main_product = canonical.id
                GROUP BY canonical.id
                HAVING COUNT(DISTINCT member.id) > 1
                ORDER BY canonical.id
            """)).scalars().all()
        return [int(value) for value in rows]
    finally:
        engine.dispose()


def _invalid_forecast_record(
    recommendation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "blocked_invalid_group",
        "forecast_scope": "canonical_main_product_group_total_demand",
        "main_product_template_id": recommendation["main_product_template_id"],
        "main_product_name": recommendation["main_product_name"],
        "group_size": recommendation["group_size"],
        "months_available": None,
        "history_start": None,
        "history_end": None,
        "next_month_forecast": None,
        "best_model": None,
        "confidence": None,
        "mae": None,
        "wape": None,
        "mase": None,
        "avg_monthly_demand": None,
    }


def refresh_groups(
    main_product_template_ids: list[int],
    *,
    only_valid_multi_member: bool = False,
) -> tuple[int, int, int]:
    poc_engine = get_poc_engine()
    forecast_count = 0
    recommendation_count = 0
    skipped_count = 0
    try:
        create_group_tables(poc_engine)

        for template_id in main_product_template_ids:
            recommendation = get_group_recommendation(template_id)
            if recommendation is None:
                print(f"Skipping {template_id}: no Odoo product/group found")
                skipped_count += 1
                continue

            if only_valid_multi_member and (
                not recommendation["group_valid"]
                or recommendation["group_size"] < 2
            ):
                skipped_count += 1
                continue

            if recommendation["group_valid"]:
                forecast = get_group_forecast(template_id)
                if forecast is None:
                    raise RuntimeError(
                        f"Group forecast missing for template {template_id}"
                    )
            else:
                forecast = _invalid_forecast_record(recommendation)

            recommendation["forecast_status"] = forecast["status"]
            upsert_group_forecast(forecast, engine=poc_engine)
            upsert_group_recommendation(recommendation, engine=poc_engine)
            forecast_count += 1
            recommendation_count += 1
            print(
                f"Persisted template {template_id}: "
                f"forecast={forecast['status']}, "
                f"recommendation={recommendation['status']}"
            )

        return forecast_count, recommendation_count, skipped_count
    finally:
        poc_engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh dedicated POC main-product group intelligence tables."
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--main-product-template-ids",
        help="Comma-separated canonical template IDs (defaults to six POC groups).",
    )
    selection.add_argument(
        "--all-valid-groups",
        action="store_true",
        help="Refresh all valid canonical groups with multiple templates.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.all_valid_groups:
        template_ids = discover_canonical_multi_member_groups()
        only_valid_multi_member = True
        print(f"Discovered {len(template_ids)} canonical multi-member groups.")
    elif args.main_product_template_ids:
        template_ids = [
            int(value.strip())
            for value in args.main_product_template_ids.split(",")
            if value.strip()
        ]
        only_valid_multi_member = False
    else:
        template_ids = list(DEFAULT_TEMPLATE_IDS)
        only_valid_multi_member = False

    forecasts, recommendations, skipped = refresh_groups(
        template_ids,
        only_valid_multi_member=only_valid_multi_member,
    )
    print(
        f"Refresh complete: forecasts={forecasts}, "
        f"recommendations={recommendations}, skipped={skipped}. "
        "Odoo was read-only; only dedicated POC group tables were upserted."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())