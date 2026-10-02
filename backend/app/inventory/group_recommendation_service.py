from typing import Any

import pandas as pd

from app.forecasting.engine_adapter import load_existing_engine
from app.forecasting.group_forecast_service import get_group_forecast
from app.inventory.recommendation_engine import build_recommendation
from app.odoo.group_demand_service import get_group_demand_history
from app.odoo.product_group_service import (
    get_group_members,
    get_product_group,
)


RECOMMENDATION_SCOPE = "canonical_main_product_group"


def _get_group_context(product_id: int) -> dict[str, Any] | None:
    group = get_product_group(product_id)
    if group is not None:
        return group

    # Step 2 also supports an Odoo template ID when it is not a variant ID.
    demand = get_group_demand_history(product_id)
    if demand is None:
        return None

    members = get_group_members(int(demand["main_product_template_id"]))
    if not members:
        return None

    return get_product_group(int(members[0]["product_id"]))


def _base_response(
    group: dict[str, Any],
    group_current_stock: float,
) -> dict[str, Any]:
    return {
        "recommendation_scope": RECOMMENDATION_SCOPE,
        "main_product_template_id": group["main_product_template_id"],
        "main_product_name": group["main_product_name"],
        "group_size": group["template_count"],
        "group_valid": group["group_valid"],
        "validation_issues": group["validation_issues"],
        "validation_warnings": group["validation_warnings"],
        "group_current_stock": group_current_stock,
        "group_next_month_forecast": None,
        "best_model": None,
        "confidence": None,
        "group_reorder_point": None,
        "group_buffered_target_stock": None,
        "group_stock_gap": None,
        "group_coverage_ratio": None,
        "group_suggested_purchase_qty": 0,
        "action": "review",
        "priority": "high",
        "reason_codes": [],
        "dead_stock": None,
        "dead_stock_reason": None,
    }


def get_group_recommendation(product_id: int) -> dict[str, Any] | None:
    group = _get_group_context(product_id)
    if group is None:
        return None

    group_current_stock = sum(
        float(member["current_stock"] or 0.0)
        for member in group["group_members"]
    )
    response = _base_response(group, group_current_stock)

    if not group["group_valid"]:
        response.update(
            {
                "status": "blocked_invalid_group",
                "reason_codes": ["group_validation_failed"],
            }
        )
        return response

    demand = get_group_demand_history(product_id)
    forecast = get_group_forecast(product_id)
    if demand is None or forecast is None:
        return None

    if forecast["status"] != "ok":
        response.update(
            {
                "status": forecast["status"],
                "reason_codes": ["group_forecast_unavailable"],
            }
        )
        return response

    sales = pd.Series(
        [month["actual"] for month in demand["months"]],
        dtype=float,
    ).reset_index(drop=True)

    load_existing_engine()
    from src.dead_stock import detect_dead_stock, months_since_last_sale
    from src.reorder import calculate_reorder_point
    from src.trend import detect_trend

    reorder = calculate_reorder_point(sales)
    trend = detect_trend(sales)
    months_without_sale = months_since_last_sale(
        pd.DataFrame({"total_quantity": sales})
    )
    dead_stock = detect_dead_stock(
        group_current_stock,
        reorder["avg_monthly_demand"],
        months_without_sale,
    )

    recommendation = build_recommendation(
        {
            "next_month_forecast": forecast["next_month_forecast"],
            "stock_on_hand": group_current_stock,
            "reorder_point": reorder["reorder_point"],
            "confidence": forecast["confidence"],
            "trend": trend["trend"],
            "dead_stock": dead_stock["dead_stock"],
        }
    )

    response.update(
        {
            "status": "ok",
            "group_next_month_forecast": forecast["next_month_forecast"],
            "best_model": forecast["best_model"],
            "confidence": forecast["confidence"],
            "group_reorder_point": recommendation["reorder_point"],
            "group_buffered_target_stock": recommendation[
                "buffered_target_stock"
            ],
            "group_stock_gap": recommendation["stock_gap"],
            "group_coverage_ratio": recommendation["coverage_ratio"],
            "group_suggested_purchase_qty": recommendation[
                "suggested_purchase_qty"
            ],
            "action": recommendation["action"],
            "priority": recommendation["priority"],
            "reason_codes": recommendation["reason_codes"],
            "dead_stock": dead_stock["dead_stock"],
            "dead_stock_reason": dead_stock["dead_stock_reason"],
        }
    )
    return response