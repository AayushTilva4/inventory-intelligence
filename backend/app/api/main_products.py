from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    MainProductDetailResponse,
    MainProductListItem,
    PersistedGroupForecastResponse,
    PersistedGroupRecommendationResponse,
)
from app.db.group_repository import (
    get_all_group_forecasts,
    get_all_group_recommendations,
    get_group_forecast,
    get_group_recommendation,
)
from app.odoo.product_group_service import (
    get_group_members,
    get_product_group,
)


router = APIRouter(
    prefix="/api/main-products",
    tags=["Main Product Groups"],
)


@router.get("", response_model=list[MainProductListItem])
def persisted_main_products():
    forecasts = {
        row["main_product_template_id"]: row
        for row in get_all_group_forecasts()
    }
    recommendations = get_all_group_recommendations()

    priority_order = {"high": 0, "medium": 1, "low": 2}
    results = []
    for recommendation in recommendations:
        template_id = recommendation["main_product_template_id"]
        forecast = forecasts.get(template_id)
        if forecast is None:
            continue

        results.append(
            {
                "main_product_template_id": template_id,
                "main_product_name": recommendation["main_product_name"],
                "group_size": recommendation["group_size"],
                "group_valid": recommendation["group_valid"],
                "group_current_stock": recommendation["group_current_stock"],
                "group_next_month_forecast": recommendation[
                    "group_next_month_forecast"
                ],
                "best_model": recommendation["best_model"],
                "confidence": recommendation["confidence"],
                "group_reorder_point": recommendation["group_reorder_point"],
                "group_buffered_target_stock": recommendation[
                    "group_buffered_target_stock"
                ],
                "group_stock_gap": recommendation["group_stock_gap"],
                "group_suggested_purchase_qty": recommendation[
                    "group_suggested_purchase_qty"
                ],
                "action": recommendation["action"],
                "priority": recommendation["priority"],
                "approval_status": recommendation["approval_status"],
                "forecast_status": forecast["forecast_status"],
                "recommendation_scope": "canonical_main_product_group",
                "forecast_scope": "canonical_main_product_group_total_demand",
            }
        )

    return sorted(
        results,
        key=lambda item: (
            priority_order.get(item["priority"], 3),
            item["main_product_template_id"],
        ),
    )


@router.get(
    "/{main_product_template_id}",
    response_model=MainProductDetailResponse,
)
def persisted_main_product_detail(main_product_template_id: int):
    forecast = get_group_forecast(main_product_template_id)
    recommendation = get_group_recommendation(main_product_template_id)
    if forecast is None or recommendation is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No persisted group intelligence for main product template "
                f"{main_product_template_id}"
            ),
        )

    step1_members = get_group_members(main_product_template_id)
    if not step1_members:
        raise HTTPException(
            status_code=404,
            detail=f"No live Odoo group for template {main_product_template_id}",
        )

    live_group = get_product_group(int(step1_members[0]["product_id"]))
    if (
        live_group is None
        or live_group["main_product_template_id"] != main_product_template_id
    ):
        raise HTTPException(
            status_code=404,
            detail=f"No live Odoo group for template {main_product_template_id}",
        )

    canonical_members = [
        member
        for member in live_group["group_members"]
        if member["template_id"] == main_product_template_id
    ]
    main_product = {
        "template_id": main_product_template_id,
        "name": live_group["main_product_name"],
        "is_main_similar": (
            canonical_members[0]["is_main_similar"]
            if canonical_members
            else None
        ),
        "current_stock": (
            sum(member["current_stock"] for member in canonical_members)
            if canonical_members
            else None
        ),
    }

    forecast["forecast_scope"] = "canonical_main_product_group_total_demand"
    recommendation["recommendation_scope"] = "canonical_main_product_group"

    return {
        "main_product": main_product,
        "group": {
            "group_valid": live_group["group_valid"],
            "group_size": live_group["template_count"],
            "validation_issues": live_group["validation_issues"],
            "validation_warnings": live_group["validation_warnings"],
            "persisted_group_valid": recommendation["group_valid"],
            "persisted_validation_issues": recommendation[
                "validation_issues"
            ],
            "persisted_validation_warnings": recommendation[
                "validation_warnings"
            ],
            "members": [
                {
                    "product_id": member["product_id"],
                    "template_id": member["template_id"],
                    "name": member["product_name"],
                    "is_main_similar": member["is_main_similar"],
                    "main_product_template_id": member[
                        "main_product_template_id"
                    ],
                    "current_stock": member["current_stock"],
                }
                for member in live_group["group_members"]
            ],
        },
        "forecast": forecast,
        "recommendation": recommendation,
    }


@router.get(
    "/{main_product_template_id}/forecast",
    response_model=PersistedGroupForecastResponse,
)
def persisted_group_forecast(main_product_template_id: int):
    result = get_group_forecast(main_product_template_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No persisted group forecast for main product template "
                f"{main_product_template_id}"
            ),
        )
    result["forecast_scope"] = "canonical_main_product_group_total_demand"
    return result


@router.get(
    "/{main_product_template_id}/recommendation",
    response_model=PersistedGroupRecommendationResponse,
)
def persisted_group_recommendation(main_product_template_id: int):
    result = get_group_recommendation(main_product_template_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No persisted group recommendation for main product template "
                f"{main_product_template_id}"
            ),
        )
    result["recommendation_scope"] = "canonical_main_product_group"
    return result