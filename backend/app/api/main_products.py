from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    CreateGroupPoRequest,
    GroupPoResponse,
    MainProductDetailResponse,
    MainProductListItem,
    PersistedGroupForecastResponse,
    PersistedGroupRecommendationResponse,
)
from app.db.group_repository import (
    get_all_group_forecasts,
    get_all_group_recommendations,
    get_group_forecast as get_db_group_forecast,
    get_group_recommendation,
)
from app.db.repository import create_group_po_for_template
from app.forecasting.group_forecast_service import get_group_forecast as get_live_group_forecast
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

        members = get_group_members(template_id)
        group_usable = sum(float(m.get("usable_qty") or 0.0) for m in members) if members else None
        group_cut_piece = sum(float(m.get("cut_piece_qty") or 0.0) for m in members) if members else None
        group_forecasted = sum(float(m.get("forecasted_stock") or 0.0) for m in members) if members else None

        results.append(
            {
                "main_product_template_id": template_id,
                "main_product_name": recommendation["main_product_name"],
                "group_size": recommendation["group_size"],
                "group_valid": recommendation["group_valid"],
                "group_current_stock": recommendation["group_current_stock"],
                "group_usable_qty": group_usable,
                "group_cut_piece_qty": group_cut_piece,
                "group_forecasted_stock": group_forecasted,
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


_detail_cache: dict[int, dict[str, Any]] = {}


@router.get(
    "/{main_product_template_id}",
    response_model=MainProductDetailResponse,
)
def persisted_main_product_detail(main_product_template_id: int):
    if main_product_template_id in _detail_cache:
        return _detail_cache[main_product_template_id]

    db_forecast = get_db_group_forecast(main_product_template_id)
    recommendation = get_group_recommendation(main_product_template_id)
    if db_forecast is None or recommendation is None:
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
    canonical_m = canonical_members[0] if canonical_members else live_group["group_members"][0]

    main_product = {
        "template_id": main_product_template_id,
        "product_id": canonical_m.get("product_id"),
        "name": live_group["main_product_name"],
        "is_main_similar": canonical_m.get("is_main_similar"),
        "current_stock": sum(member["current_stock"] for member in canonical_members) if canonical_members else None,
        "usable_qty": sum(member.get("usable_qty", 0.0) for member in canonical_members) if canonical_members else None,
        "cut_piece_qty": sum(member.get("cut_piece_qty", 0.0) for member in canonical_members) if canonical_members else None,
        "forecasted_stock": sum(member.get("forecasted_stock", 0.0) for member in canonical_members) if canonical_members else None,
        "incoming_qty": sum(member.get("incoming_qty", 0.0) for member in canonical_members) if canonical_members else None,
        "outgoing_qty": sum(member.get("outgoing_qty", 0.0) for member in canonical_members) if canonical_members else None,
    }

    # Live 3-month forecast calculation
    live_fc = get_live_group_forecast(main_product_template_id)
    forecast_3_months = live_fc.get("forecast_3_months") if live_fc else []

    db_forecast["forecast_scope"] = "canonical_main_product_group_total_demand"
    db_forecast["forecast_3_months"] = forecast_3_months
    recommendation["recommendation_scope"] = "canonical_main_product_group"

    group_members_list = live_group["group_members"]
    total_current_stock = sum(float(m.get("current_stock") or 0.0) for m in group_members_list)
    total_usable_qty = sum(float(m.get("usable_qty") or 0.0) for m in group_members_list)
    total_cut_piece_qty = sum(float(m.get("cut_piece_qty") or 0.0) for m in group_members_list)
    total_forecasted_stock = sum(float(m.get("forecasted_stock") or 0.0) for m in group_members_list)
    total_incoming_qty = sum(float(m.get("incoming_qty") or 0.0) for m in group_members_list)
    total_outgoing_qty = sum(float(m.get("outgoing_qty") or 0.0) for m in group_members_list)

    detail_res = {
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
            "total_current_stock": total_current_stock,
            "total_usable_qty": total_usable_qty,
            "total_cut_piece_qty": total_cut_piece_qty,
            "total_forecasted_stock": total_forecasted_stock,
            "total_incoming_qty": total_incoming_qty,
            "total_outgoing_qty": total_outgoing_qty,
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
                    "usable_qty": member.get("usable_qty", 0.0),
                    "cut_piece_qty": member.get("cut_piece_qty", 0.0),
                    "forecasted_stock": member.get("forecasted_stock", 0.0),
                    "incoming_qty": member.get("incoming_qty", 0.0),
                    "outgoing_qty": member.get("outgoing_qty", 0.0),
                }
                for member in group_members_list
            ],
        },
        "forecast": db_forecast,
        "recommendation": recommendation,
    }
    _detail_cache[main_product_template_id] = detail_res
    return detail_res


@router.post(
    "/{main_product_template_id}/create-po",
    response_model=GroupPoResponse,
)
def create_group_purchase_order(
    main_product_template_id: int,
    payload: CreateGroupPoRequest,
):
    try:
        po_info = create_group_po_for_template(
            main_product_template_id,
            payload.quantity,
        )
        _detail_cache.pop(main_product_template_id, None)
        return po_info
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{main_product_template_id}/forecast",
    response_model=PersistedGroupForecastResponse,
)
def persisted_group_forecast(main_product_template_id: int):
    result = get_db_group_forecast(main_product_template_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No persisted group forecast for main product template "
                f"{main_product_template_id}"
            ),
        )
    live_fc = get_live_group_forecast(main_product_template_id)
    result["forecast_3_months"] = live_fc.get("forecast_3_months") if live_fc else []
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