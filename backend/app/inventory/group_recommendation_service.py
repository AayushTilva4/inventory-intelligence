import calendar
import datetime
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
    group_usable_stock: float = 0.0,
    group_cut_piece_stock: float = 0.0,
    group_incoming_stock: float = 0.0,
    group_committed_stock: float = 0.0,
    group_inventory_position: float = 0.0,
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
        "group_usable_stock": group_usable_stock,
        "group_cut_piece_stock": group_cut_piece_stock,
        "group_incoming_stock": group_incoming_stock,
        "group_committed_stock": group_committed_stock,
        "group_inventory_position": group_inventory_position,
        "group_next_month_forecast": None,
        "group_lead_time_demand": None,
        "group_review_period_demand": None,
        "group_forecasted_horizon_demand": None,
        "best_model": None,
        "confidence": None,
        "group_reorder_point": None,
        "group_safety_stock": None,
        "group_service_level": None,
        "group_sigma_error": None,
        "group_safety_stock_method": None,
        "group_target_stock": None,
        "group_buffered_target_stock": None,
        "group_stock_gap": None,
        "group_coverage_ratio": None,
        "group_suggested_purchase_qty": 0,
        "action": "review",
        "priority": "high",
        "reason_codes": [],
        "dead_stock": None,
        "dead_stock_reason": None,
        "cold_start_diagnostic": None,
    }


def get_group_recommendation(product_id: int) -> dict[str, Any] | None:
    group = _get_group_context(product_id)
    if group is None:
        return None

    group_current_stock = sum(
        float(member.get("current_stock") or 0.0)
        for member in group["group_members"]
    )
    group_usable_stock = sum(
        float(
            member.get("usable_qty")
            if member.get("usable_qty") is not None
            else (member.get("current_stock") or 0.0)
        )
        for member in group["group_members"]
    )
    group_cut_piece_stock = sum(
        float(member.get("cut_piece_qty") or 0.0)
        for member in group["group_members"]
    )
    group_incoming_stock = sum(
        float(member.get("incoming_qty") or 0.0)
        for member in group["group_members"]
    )
    group_committed_stock = sum(
        float(member.get("outgoing_qty") or 0.0)
        for member in group["group_members"]
    )
    group_inventory_position = (
        group_usable_stock + group_incoming_stock - group_committed_stock
    )

    response = _base_response(
        group,
        group_current_stock=group_current_stock,
        group_usable_stock=group_usable_stock,
        group_cut_piece_stock=group_cut_piece_stock,
        group_incoming_stock=group_incoming_stock,
        group_committed_stock=group_committed_stock,
        group_inventory_position=group_inventory_position,
    )

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
                "cold_start_diagnostic": forecast.get("cold_start_diagnostic"),
            }
        )
        return response

    sales = pd.Series(
        [month["actual"] for month in demand["months"]],
        dtype=float,
    ).reset_index(drop=True)

    load_existing_engine()
    from src.dead_stock import detect_dead_stock, months_since_last_sale
    from src.trend import detect_trend

    trend = detect_trend(sales)
    months_without_sale = months_since_last_sale(
        pd.DataFrame({"total_quantity": sales})
    )
    dead_stock = detect_dead_stock(
        group_current_stock,
        float(forecast.get("next_month_forecast") or 0.0),
        months_without_sale,
    )

    # ---------------------------------------------------------
    # Operational Demand Calculation over Lead Time + Review Period
    # Partial days weighting for current month (Phase 2 Task 5)
    # ---------------------------------------------------------
    today = datetime.date.today()
    d = today.day
    _, total_days = calendar.monthrange(today.year, today.month)
    w0 = max(0.0, min(1.0, (total_days - d) / total_days))

    mf = forecast.get("forecast_multistep_values")
    if not mf or len(mf) < 5:
        single_fc = float(forecast.get("next_month_forecast") or 0.0)
        mf = [single_fc] * 5

    group_lead_time_demand = (w0 * mf[0]) + mf[1] + mf[2] + ((1.0 - w0) * mf[3])
    group_review_period_demand = (w0 * mf[3]) + ((1.0 - w0) * mf[4])
    group_forecasted_horizon_demand = group_lead_time_demand + group_review_period_demand

    from app.forecasting.benchmark_v2.classification import classify_demand_pattern
    from app.inventory.safety_stock_service import compute_historical_forecast_error

    group_pattern = classify_demand_pattern(sales, stock_on_hand=group_current_stock)["pattern"]
    group_sigma_error, _ = compute_historical_forecast_error(
        sales,
        model_name=forecast.get("best_model") or "trimmed_mean_3",
    )

    from app.odoo.stockout_service import classify_group_monthly_stockouts
    stockouts = classify_group_monthly_stockouts(
        demand.get("main_product_template_id", product_id),
        demand.get("months", []),
    )
    stockout_suppressed_cnt = sum(
        1 for m in stockouts if m.get("stockout_status") == "STOCKOUT_SUPPRESSED"
    )

    recommendation = build_recommendation(
        {
            "next_month_forecast": forecast["next_month_forecast"],
            "forecast_multistep_values": mf,
            "lead_time_demand": group_lead_time_demand,
            "review_period_demand": group_review_period_demand,
            "forecasted_horizon_demand": group_forecasted_horizon_demand,
            "stock_on_hand": group_current_stock,
            "usable_stock": group_usable_stock,
            "cut_piece_stock": group_cut_piece_stock,
            "incoming_stock": group_incoming_stock,
            "committed_stock": group_committed_stock,
            "confidence": forecast["confidence"],
            "trend": trend["trend"],
            "dead_stock": dead_stock["dead_stock"],
            "demand_pattern": group_pattern,
            "sigma_error": group_sigma_error,
            "best_model": forecast.get("best_model"),
            "selection_reason": forecast.get("selection_reason"),
            "history_months": len(demand.get("months", [])),
            "usable_observations": len(sales),
            "stockout_suppressed_months": stockout_suppressed_cnt,
            "is_short_history": len(sales) < 14,
            "short_history_fallback_used": len(sales) < 14,
            "wape": forecast.get("wape"),
            "mase": forecast.get("mase"),
            "rmse": forecast.get("rmse") or group_sigma_error,
            "evaluation_observations": forecast.get("evaluation_observations"),
        }
    )

    response.update(
        {
            "status": "ok",
            "group_next_month_forecast": forecast["next_month_forecast"],
            "group_lead_time_demand": recommendation["lead_time_demand"],
            "group_review_period_demand": recommendation["review_period_demand"],
            "group_forecasted_horizon_demand": recommendation[
                "forecasted_horizon_demand"
            ],
            "best_model": forecast["best_model"],
            "confidence": forecast["confidence"],
            "group_reorder_point": recommendation["reorder_point"],
            "group_safety_stock": recommendation["safety_stock"],
            "group_service_level": recommendation.get("service_level"),
            "group_sigma_error": recommendation.get("sigma_error_1m"),
            "group_safety_stock_method": recommendation.get("safety_stock_method"),
            "group_target_stock": recommendation["target_stock"],
            "group_buffered_target_stock": recommendation[
                "buffered_target_stock"
            ],
            "group_stock_gap": recommendation["stock_gap"],
            "group_coverage_ratio": recommendation["coverage_ratio"],
            "group_suggested_purchase_qty": recommendation[
                "suggested_purchase_qty"
            ],
            "group_inventory_position": recommendation["inventory_position"],
            "action": recommendation["action"],
            "priority": recommendation["priority"],
            "reason_codes": recommendation["reason_codes"],
            "dead_stock": dead_stock["dead_stock"],
            "dead_stock_reason": dead_stock["dead_stock_reason"],
            "z_score": recommendation.get("z_score"),
            "sigma_horizon": recommendation.get("sigma_horizon"),
            "raw_safety_stock": recommendation.get("raw_safety_stock"),
            "cap_applied": recommendation.get("cap_applied", False),
            "cap_value": recommendation.get("cap_value"),
            "zero_purchase_explanation": recommendation.get("zero_purchase_explanation"),
            "calculation_breakdown": recommendation.get("calculation_breakdown"),
        }
    )
    return response