import math
from typing import Any


BUFFER_PCT = 0.10
EXCESS_MULTIPLIER = 2.0

def build_recommendation(row: dict[str, Any]) -> dict[str, Any]:
    """
    Convert forecast + inventory signals into a deterministic
    inventory recommendation.

    Phase 2 Task 4:
    Inventory Position = Usable Stock + Incoming Stock - Committed Customer Demand
    Cut pieces are excluded unless explicitly classified as usable.
    """

    forecast = float(row.get("next_month_forecast") or 0.0)
    stock_on_hand = float(
        row.get("stock_on_hand")
        if row.get("stock_on_hand") is not None
        else (row.get("current_stock") or 0.0)
    )

    usable_stock = float(
        row.get("usable_stock")
        if row.get("usable_stock") is not None
        else (
            row.get("usable_qty")
            if row.get("usable_qty") is not None
            else stock_on_hand
        )
    )

    cut_piece_stock = float(
        row.get("cut_piece_stock")
        if row.get("cut_piece_stock") is not None
        else (row.get("cut_piece_qty") or 0.0)
    )

    incoming_stock = float(
        row.get("incoming_stock")
        if row.get("incoming_stock") is not None
        else (row.get("incoming_qty") or 0.0)
    )

    committed_stock = float(
        row.get("committed_stock")
        if row.get("committed_stock") is not None
        else (
            row.get("outgoing_qty")
            if row.get("outgoing_qty") is not None
            else (row.get("committed_qty") or 0.0)
        )
    )

    # ---------------------------------------------------------
    # Canonical Inventory Position (Phase 2 Task 4)
    # ---------------------------------------------------------
    inventory_position = usable_stock + incoming_stock - committed_stock

    confidence = row.get("confidence")
    trend = row.get("trend")

    dead_stock_value = row.get("dead_stock", False)
    dead_stock = (
        dead_stock_value is True
        or (
            isinstance(dead_stock_value, str)
            and dead_stock_value.strip().lower() == "true"
        )
        or dead_stock_value == 1
    )

    # ---------------------------------------------------------
    # Forecast-Driven Operational Horizon Requirement (Phase 2 Task 5)
    # Demand over Lead Time (3 months) + Review Period (1 month)
    # ---------------------------------------------------------
    lead_time_months = float(row.get("lead_time_months") or 3.0)
    review_period_months = float(row.get("review_period_months") or 1.0)
    operational_horizon_months = lead_time_months + review_period_months

    if row.get("forecasted_horizon_demand") is not None:
        forecasted_horizon_demand = float(row.get("forecasted_horizon_demand") or 0.0)
        lead_time_demand = float(
            row.get("lead_time_demand")
            if row.get("lead_time_demand") is not None
            else (forecasted_horizon_demand * (lead_time_months / operational_horizon_months))
        )
        review_period_demand = float(
            row.get("review_period_demand")
            if row.get("review_period_demand") is not None
            else (forecasted_horizon_demand * (review_period_months / operational_horizon_months))
        )
    elif row.get("lead_time_demand") is not None or row.get("review_period_demand") is not None:
        lead_time_demand = float(row.get("lead_time_demand") or 0.0)
        review_period_demand = float(row.get("review_period_demand") or 0.0)
        forecasted_horizon_demand = lead_time_demand + review_period_demand
    elif row.get("reorder_point") is not None:
        # Explicit target parameter support (e.g. unit tests)
        forecasted_horizon_demand = float(row.get("reorder_point") or 0.0)
        lead_time_demand = forecasted_horizon_demand * (lead_time_months / operational_horizon_months)
        review_period_demand = forecasted_horizon_demand * (review_period_months / operational_horizon_months)
    else:
        # Derived from forecast over operational horizon
        lead_time_demand = forecast * lead_time_months
        review_period_demand = forecast * review_period_months
        forecasted_horizon_demand = lead_time_demand + review_period_demand

    if dead_stock:
        forecasted_horizon_demand = 0.0
        lead_time_demand = 0.0
        review_period_demand = 0.0

    demand_pattern = row.get("demand_pattern") or row.get("pattern") or "normal"
    service_level = row.get("service_level")
    sigma_error = row.get("sigma_error") if row.get("sigma_error") is not None else row.get("forecast_error_std")

    from app.inventory.safety_stock_service import (
        calculate_error_based_safety_stock,
        get_z_score,
    )

    if row.get("safety_stock") is not None:
        # Explicit caller override
        safety_stock = float(row.get("safety_stock") or 0.0)
        ss_info = {
            "safety_stock": safety_stock,
            "service_level": float(service_level) if service_level is not None else 0.75,
            "z_score": get_z_score(float(service_level) if service_level is not None else 0.75),
            "sigma_error_1m": float(sigma_error) if sigma_error is not None else 0.0,
            "sigma_horizon": (float(sigma_error) if sigma_error is not None else 0.0) * math.sqrt(operational_horizon_months),
            "safety_stock_method": "explicit_override",
            "fallback_used": False,
        }
    elif sigma_error is not None or row.get("demand_pattern") is not None or row.get("pattern") is not None:
        ss_info = calculate_error_based_safety_stock(
            forecasted_horizon_demand=forecasted_horizon_demand,
            lead_time_months=lead_time_months,
            review_period_months=review_period_months,
            demand_pattern=demand_pattern,
            service_level=service_level,
            sigma_error=sigma_error,
            dead_stock=dead_stock,
        )
        safety_stock = ss_info["safety_stock"]
    else:
        # Baseline legacy 10% fallback when neither error nor pattern is provided
        safety_stock = 0.0 if dead_stock else round(forecasted_horizon_demand * BUFFER_PCT, 4)
        ss_info = {
            "safety_stock": safety_stock,
            "service_level": 0.75,
            "z_score": 0.6745,
            "sigma_error_1m": 0.0,
            "sigma_horizon": 0.0,
            "safety_stock_method": "legacy_fixed_fallback",
            "fallback_used": True,
        }

    reorder_point = round(forecasted_horizon_demand, 2)
    target_stock = round(forecasted_horizon_demand + safety_stock, 4)
    buffered_target = target_stock

    stock_gap = max(round(target_stock - inventory_position, 4), 0.0)

    coverage_ratio = (
        inventory_position / target_stock
        if target_stock > 0
        else None
    )

    suggested_purchase_qty = math.ceil(stock_gap)

    reason_codes = []

    # ---------------------------------------------------------
    # 1. Dead stock takes precedence.
    # ---------------------------------------------------------

    if dead_stock:
        action = "dead_stock"
        reason_codes.append("dead_stock_detected")

        if stock_on_hand > 0:
            reason_codes.append("stock_remains_without_recent_demand")

        suggested_purchase_qty = 0

    # ---------------------------------------------------------
    # 2. Inventory position far above target (Excess).
    # ---------------------------------------------------------

    elif (
        target_stock > 0
        and inventory_position >= target_stock * EXCESS_MULTIPLIER
    ):
        action = "excess_stock"
        reason_codes.append("stock_far_above_target")

        if forecast <= 0:
            reason_codes.append("zero_forecast")

        suggested_purchase_qty = 0

    # ---------------------------------------------------------
    # 3. Inventory position below target (Needs Replenishment).
    # ---------------------------------------------------------

    elif inventory_position < target_stock:
        reason_codes.append("stock_below_target")

        if incoming_stock > 0:
            reason_codes.append("partial_incoming_coverage")

        if committed_stock > 0:
            reason_codes.append("committed_customer_demand_deducted")

        if forecast > 0:
            reason_codes.append("positive_forecast")

        if trend == "rising":
            reason_codes.append("rising_demand")

        action = "purchase"

    # ---------------------------------------------------------
    # 4. Inventory position meets or exceeds target.
    # ---------------------------------------------------------

    else:
        action = "hold"
        suggested_purchase_qty = 0
        reason_codes.append("stock_meets_target")

        if incoming_stock > 0:
            reason_codes.append("covered_by_incoming_stock")

        if forecast <= 0:
            reason_codes.append("zero_forecast")

    # ---------------------------------------------------------
    # Priority
    # ---------------------------------------------------------

    if action == "purchase":
        if target_stock > 0:
            gap_pct = stock_gap / target_stock
        else:
            gap_pct = 0

        if gap_pct >= 0.50:
            priority = "high"
        else:
            priority = "medium"

    elif action == "review":
        priority = "high"

    elif action == "dead_stock":
        priority = "medium"

    elif action == "excess_stock":
        priority = "low"

    else:
        priority = "low"

    # ---------------------------------------------------------
    # Zero-Purchase Explanation Construction (Phase 2 Task 11)
    # ---------------------------------------------------------
    zero_purchase_explanation = None
    if suggested_purchase_qty == 0:
        if dead_stock:
            zero_purchase_explanation = "Target stock is 0.00 because product group is classified as dead stock (no recent customer demand)."
        elif action == "excess_stock":
            zero_purchase_explanation = f"Inventory position ({inventory_position:.2f}) far exceeds target stock ({target_stock:.2f}) by excess multiplier (>= 2.0x)."
        elif action == "hold" and incoming_stock > 0 and (usable_stock + incoming_stock - committed_stock) >= target_stock:
            zero_purchase_explanation = f"Inventory position ({inventory_position:.2f}) meets target stock ({target_stock:.2f}); incoming stock ({incoming_stock:.2f}) covers replenishment requirement."
        elif target_stock == 0.0:
            zero_purchase_explanation = "Forecasted horizon demand (0.00) and safety stock (0.00) are both zero. Target stock is 0.00."
        elif inventory_position >= target_stock:
            zero_purchase_explanation = f"Inventory position ({inventory_position:.2f}) already covers target stock ({target_stock:.2f}). No purchase gap remaining."
        else:
            zero_purchase_explanation = "No purchase gap remaining after accounting for inventory position and target stock."

    # ---------------------------------------------------------
    # Calculation Breakdown (Phase 2 Task 11)
    # ---------------------------------------------------------
    mf = row.get("forecast_multistep_values")
    if not mf or len(mf) < 4:
        single_fc = float(forecast or 0.0)
        mf_4 = [round(single_fc, 2)] * 4
    else:
        mf_4 = [round(float(v), 2) for v in mf[:4]]

    history_m = row.get("history_months") if row.get("history_months") is not None else row.get("months_available")
    usable_obs = row.get("usable_observations") if row.get("usable_observations") is not None else row.get("months_available")
    is_short_hist = row.get("is_short_history", bool(usable_obs and usable_obs < 14))

    forecast_breakdown = {
        "monthly_forecasts": mf_4,
        "forecasted_horizon_demand": round(forecasted_horizon_demand, 2),
        "selected_model": row.get("best_model") or row.get("selected_model"),
        "selection_reason": row.get("selection_reason"),
        "history_months": history_m,
        "usable_observations": usable_obs,
        "stockout_suppressed_months": row.get("stockout_suppressed_months", 0),
        "demand_pattern": demand_pattern,
        "is_short_history": is_short_hist,
        "short_history_fallback_used": row.get("short_history_fallback_used", is_short_hist),
        "confidence": confidence,
        "wape": row.get("wape"),
        "mase": row.get("mase"),
        "rmse": row.get("rmse") if row.get("rmse") is not None else ss_info.get("sigma_error_1m"),
        "observation_count": row.get("observation_count") or row.get("evaluation_observations"),
        "warnings": row.get("warnings", []),
    }

    safety_stock_breakdown = {
        "lead_time_months": lead_time_months,
        "review_period_months": review_period_months,
        "operational_horizon_months": operational_horizon_months,
        "service_level": ss_info.get("service_level"),
        "z_score": ss_info.get("z_score"),
        "sigma_error_1m": ss_info.get("sigma_error_1m"),
        "horizon_scale_factor": ss_info.get("horizon_scale_factor", 2.0),
        "sigma_horizon": ss_info.get("sigma_horizon"),
        "raw_safety_stock": ss_info.get("raw_safety_stock"),
        "cap_applied": ss_info.get("cap_applied", False),
        "cap_value": ss_info.get("cap_value"),
        "final_safety_stock": round(safety_stock, 2),
        "safety_stock_method": ss_info.get("safety_stock_method"),
        "dead_stock_safeguard": ss_info.get("dead_stock_safeguard", False),
    }

    inventory_position_breakdown = {
        "usable_stock": round(usable_stock, 2),
        "incoming_stock": round(incoming_stock, 2),
        "committed_stock": round(committed_stock, 2),
        "cut_piece_stock_excluded": round(cut_piece_stock, 2),
        "inventory_position": round(inventory_position, 2),
        "formula": "Inventory Position = Usable Stock + Incoming Stock - Committed Customer Demand",
    }

    target_and_purchase_breakdown = {
        "forecasted_horizon_demand": round(forecasted_horizon_demand, 2),
        "safety_stock": round(safety_stock, 2),
        "target_stock": round(target_stock, 2),
        "inventory_position": round(inventory_position, 2),
        "stock_gap": round(stock_gap, 2),
        "suggested_purchase_qty": suggested_purchase_qty,
        "action": action,
        "reason_codes": reason_codes,
        "zero_purchase_explanation": zero_purchase_explanation,
        "formulas": {
            "target_stock": "Target Stock = Forecasted Horizon Demand + Safety Stock",
            "stock_gap": "Stock Gap = max(Target Stock - Inventory Position, 0)",
            "suggested_purchase_qty": "Suggested Purchase Quantity = ceil(Stock Gap)",
        },
    }

    calculation_breakdown = {
        "forecast_breakdown": forecast_breakdown,
        "safety_stock_breakdown": safety_stock_breakdown,
        "inventory_position_breakdown": inventory_position_breakdown,
        "target_and_purchase_breakdown": target_and_purchase_breakdown,
        "zero_purchase_explanation": zero_purchase_explanation,
    }

    return {
        "action": action,
        "priority": priority,
        "next_month_forecast": forecast,
        "lead_time_months": lead_time_months,
        "review_period_months": review_period_months,
        "lead_time_demand": round(lead_time_demand, 2),
        "review_period_demand": round(review_period_demand, 2),
        "forecasted_horizon_demand": round(forecasted_horizon_demand, 2),
        "current_stock": stock_on_hand,
        "usable_stock": round(usable_stock, 2),
        "cut_piece_stock": round(cut_piece_stock, 2),
        "incoming_stock": round(incoming_stock, 2),
        "committed_stock": round(committed_stock, 2),
        "inventory_position": round(inventory_position, 2),
        "reorder_point": reorder_point,
        "safety_stock": round(safety_stock, 2),
        "service_level": ss_info.get("service_level"),
        "z_score": ss_info.get("z_score"),
        "sigma_error_1m": ss_info.get("sigma_error_1m"),
        "sigma_horizon": ss_info.get("sigma_horizon"),
        "raw_safety_stock": ss_info.get("raw_safety_stock"),
        "cap_applied": ss_info.get("cap_applied", False),
        "cap_value": ss_info.get("cap_value"),
        "safety_stock_method": ss_info.get("safety_stock_method"),
        "target_stock": round(target_stock, 2),
        "buffered_target_stock": round(buffered_target, 2),
        "stock_gap": round(stock_gap, 2),
        "coverage_ratio": (
            round(coverage_ratio, 3)
            if coverage_ratio is not None
            else None
        ),
        "suggested_purchase_qty": suggested_purchase_qty,
        "reason_codes": reason_codes,
        "zero_purchase_explanation": zero_purchase_explanation,
        "calculation_breakdown": calculation_breakdown,
    }