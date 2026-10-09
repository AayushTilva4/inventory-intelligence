import argparse
import logging
import sys
import time
from typing import Any

from sqlalchemy import text

from app.db.connection import get_poc_engine
from app.db.group_repository import (
    create_group_tables,
    upsert_group_forecast,
    upsert_group_recommendation,
)
from app.db.planning_run_repository import (
    apply_retention_policy,
    complete_planning_run,
    create_planning_run,
    fail_planning_run,
)
from app.forecasting.group_forecast_service import get_group_forecast
from app.inventory.group_recommendation_service import get_group_recommendation
from app.odoo.product_group_service import _get_odoo_engine

logger = logging.getLogger("planning_cycle")

DEFAULT_TEMPLATE_IDS = (405, 1544, 1562, 1584, 7353, 10673)


def discover_canonical_multi_member_groups() -> list[int]:
    """Read-only discovery of canonical groups from Odoo database."""
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


def execute_planning_cycle(
    template_ids: list[int],
    *,
    run_id: str | None = None,
    only_valid_multi_member: bool = False,
    retention_limit: int = 30,
) -> str:
    """
    Executes a complete planning cycle for the provided main-product template IDs.
    Encapsulated within an explicit planning-run lifecycle with status tracking and atomic persistence.
    """
    poc_engine = get_poc_engine()
    create_group_tables(poc_engine)

    config_meta = {
        "python_version": sys.version,
        "template_count": len(template_ids),
        "only_valid_multi_member": only_valid_multi_member,
        "retention_limit": retention_limit,
    }

    # 1. Initialize Planning Run ('running')
    active_run_id = create_planning_run(
        run_id=run_id,
        config_metadata=config_meta,
        engine=poc_engine,
    )

    start_time = time.time()
    forecast_count = 0
    recommendation_count = 0
    skipped_count = 0
    errors: list[str] = []

    try:
        for template_id in template_ids:
            recommendation = get_group_recommendation(template_id)
            if recommendation is None:
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

            # Persist against current active run_id
            upsert_group_forecast(forecast, run_id=active_run_id, engine=poc_engine)
            upsert_group_recommendation(recommendation, run_id=active_run_id, engine=poc_engine)

            forecast_count += 1
            recommendation_count += 1

        elapsed = round(time.time() - start_time, 2)
        summary = {
            "forecasts_persisted": forecast_count,
            "recommendations_persisted": recommendation_count,
            "skipped_groups": skipped_count,
            "duration_seconds": elapsed,
        }

        # 2. Complete Planning Run ('completed')
        complete_planning_run(
            run_id=active_run_id,
            num_groups=forecast_count,
            num_products=forecast_count,
            execution_summary=summary,
            engine=poc_engine,
        )

        # 3. Apply retention policy
        pruned = apply_retention_policy(
            retention_limit=retention_limit,
            engine=poc_engine,
        )
        print(
            f"Planning run {active_run_id} completed successfully in {elapsed}s: "
            f"forecasts={forecast_count}, recommendations={recommendation_count}, "
            f"skipped={skipped_count}, pruned_old_runs={pruned}."
        )
        return active_run_id

    except Exception as exc:
        elapsed = round(time.time() - start_time, 2)
        error_msg = str(exc)
        summary = {
            "forecasts_persisted": forecast_count,
            "recommendations_persisted": recommendation_count,
            "duration_seconds": elapsed,
            "error": error_msg,
        }
        fail_planning_run(
            run_id=active_run_id,
            error_message=error_msg,
            execution_summary=summary,
            engine=poc_engine,
        )
        print(f"Planning run {active_run_id} FAILED after {elapsed}s: {error_msg}", file=sys.stderr)
        raise RuntimeError(f"Planning run {active_run_id} failed: {error_msg}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute Inventory Intelligence reproducible planning cycle."
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--main-product-template-ids",
        help="Comma-separated canonical template IDs (defaults to POC template set).",
    )
    selection.add_argument(
        "--all-valid-groups",
        action="store_true",
        help="Execute planning run for all valid canonical multi-member groups.",
    )
    parser.add_argument(
        "--run-id",
        help="Optional explicit run ID to assign to this planning run.",
    )
    parser.add_argument(
        "--retention-limit",
        type=int,
        default=30,
        help="Maximum completed planning runs to retain (default: 30).",
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

    try:
        run_id = execute_planning_cycle(
            template_ids=template_ids,
            run_id=args.run_id,
            only_valid_multi_member=only_valid_multi_member,
            retention_limit=args.retention_limit,
        )
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())
