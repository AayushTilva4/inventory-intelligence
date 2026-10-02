import math
from typing import Any


BUFFER_PCT = 0.10
EXCESS_MULTIPLIER = 2.0

LOW_CONFIDENCE_LEVELS = {
    "low",
    "very_low",
}


def build_recommendation(row: dict[str, Any]) -> dict[str, Any]:
    """
    Convert forecast + inventory signals into a deterministic
    inventory recommendation.

    Claude is intentionally not involved here.
    """

    forecast = float(row.get("next_month_forecast") or 0.0)
    stock = float(row.get("stock_on_hand") or 0.0)
    reorder_point = float(row.get("reorder_point") or 0.0)

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

    # Existing engine's reorder point represents approximately
    # 3 months lead time + 1 month safety stock.
    buffered_target = reorder_point * (1.0 + BUFFER_PCT)

    stock_gap = max(buffered_target - stock, 0.0)

    coverage_ratio = (
        stock / buffered_target
        if buffered_target > 0
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

        if stock > 0:
            reason_codes.append("stock_remains_without_recent_demand")

        suggested_purchase_qty = 0

    # ---------------------------------------------------------
    # 2. Very large stock relative to target.
    # ---------------------------------------------------------

    elif (
        buffered_target > 0
        and stock >= buffered_target * EXCESS_MULTIPLIER
    ):
        action = "excess_stock"

        reason_codes.append("stock_far_above_target")

        if forecast <= 0:
            reason_codes.append("zero_forecast")

        suggested_purchase_qty = 0

    # ---------------------------------------------------------
    # 3. Stock below target.
    # ---------------------------------------------------------

    elif stock < buffered_target:

        reason_codes.append("stock_below_target")

        if forecast > 0:
            reason_codes.append("positive_forecast")

        if trend == "rising":
            reason_codes.append("rising_demand")

        if confidence in LOW_CONFIDENCE_LEVELS:
            action = "review"
            reason_codes.append("low_forecast_confidence")
        else:
            action = "purchase"

    # ---------------------------------------------------------
    # 4. Stock is sufficient.
    # ---------------------------------------------------------

    else:
        action = "hold"
        suggested_purchase_qty = 0
        reason_codes.append("stock_meets_target")

        if forecast <= 0:
            reason_codes.append("zero_forecast")

    # ---------------------------------------------------------
    # Priority
    # ---------------------------------------------------------

    if action == "purchase":
        if buffered_target > 0:
            gap_pct = stock_gap / buffered_target
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

    return {
        "action": action,
        "priority": priority,
        "next_month_forecast": forecast,
        "current_stock": stock,
        "reorder_point": reorder_point,
        "buffered_target_stock": round(buffered_target, 2),
        "stock_gap": round(stock_gap, 2),
        "coverage_ratio": (
            round(coverage_ratio, 3)
            if coverage_ratio is not None
            else None
        ),
        "suggested_purchase_qty": suggested_purchase_qty,
        "reason_codes": reason_codes,
    }