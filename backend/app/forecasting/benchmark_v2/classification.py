"""
Demand pattern classification for Forecast Benchmark V2.
Classifies products into 8 distinct demand patterns:
- fast moving
- intermittent
- low demand
- falling
- rising
- dead stock
- cold start
- stable/normal
"""

from typing import Any
import numpy as np
import pandas as pd


def classify_demand_pattern(
    series: pd.Series,
    stock_on_hand: float = 0.0,
    product_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """
    Classifies a product's continuous monthly demand series into one of 8 operational demand patterns.

    Parameters:
    - series: pd.Series of monthly sales quantities (continuous monthly series available up to as-of date)
    - stock_on_hand: inventory level. For historical as-of-origin classification, this MUST be 0.0 (or omitted)
      to avoid lookahead leakage from future/current stock levels. For current-state reporting, pass the
      current stock on hand from stock_quant.
    - product_df: optional DataFrame containing 'month' and 'total_quantity' columns

    Returns:
    - pattern: str (one of the 8 standard demand patterns)
    - metrics: dict of computed operational features
    - description: brief business explanation of the classification
    """
    vals = series.astype(float).values
    total_months = len(vals)

    if total_months == 0:
        return {
            "pattern": "cold_start",
            "description": "No sales history recorded yet.",
            "metrics": {"history_months": 0},
        }

    nonzero_indices = np.where(vals > 0)[0]
    active_months = len(nonzero_indices)
    active_ratio = active_months / total_months if total_months > 0 else 0.0

    # Months since last positive sale
    if active_months > 0:
        last_sale_idx = nonzero_indices[-1]
        months_since_last_sale = total_months - 1 - last_sale_idx
    else:
        months_since_last_sale = total_months

    # Recent 6 months vs previous 6 months averages
    recent_window = min(6, total_months)
    recent_vals = vals[-recent_window:]
    recent_avg = float(np.mean(recent_vals))

    if total_months >= 12:
        prev_vals = vals[-12:-6]
        previous_avg = float(np.mean(prev_vals))
    elif total_months > recent_window:
        prev_vals = vals[:-recent_window]
        previous_avg = float(np.mean(prev_vals))
    else:
        previous_avg = 0.0

    trend_pct = None
    if previous_avg > 0:
        trend_pct = float((recent_avg - previous_avg) / previous_avg)

    # Average Demand Interval (ADI) and CV^2 (Coefficient of Variation squared)
    adi = total_months / active_months if active_months > 0 else float(total_months)
    positive_demands = vals[nonzero_indices] if active_months > 0 else np.array([0.0])
    mean_positive = float(np.mean(positive_demands)) if len(positive_demands) > 0 else 0.0
    std_positive = float(np.std(positive_demands)) if len(positive_demands) > 1 else 0.0
    cv2 = float((std_positive / mean_positive) ** 2) if mean_positive > 0 else 0.0

    metrics = {
        "history_months": int(total_months),
        "active_months": int(active_months),
        "active_ratio": round(float(active_ratio), 3),
        "months_since_last_sale": int(months_since_last_sale),
        "recent_avg": round(float(recent_avg), 2),
        "previous_avg": round(float(previous_avg), 2),
        "trend_pct": round(float(trend_pct), 3) if trend_pct is not None else None,
        "adi": round(float(adi), 2),
        "cv2": round(float(cv2), 3),
        "stock_on_hand": round(float(stock_on_hand), 2),
    }

    # -------------------------------------------------------------
    # Classification Hierarchy
    # -------------------------------------------------------------

    # 1. Cold Start: very limited historical records
    if total_months < 6:
        return {
            "pattern": "cold_start",
            "description": f"Limited history ({total_months} months); relies on category benchmarks.",
            "metrics": metrics,
        }

    # 2. Dead Stock: no demand for 6+ months with inventory on hand or total sales inactivity
    if months_since_last_sale >= 6 and (stock_on_hand > 0 or recent_avg == 0):
        return {
            "pattern": "dead_stock",
            "description": f"No sales for {months_since_last_sale} months with stock on hand ({stock_on_hand} units).",
            "metrics": metrics,
        }

    # 3. Fast Moving: high average volume and consistent activity
    if recent_avg >= 40.0 and active_ratio >= 0.65:
        return {
            "pattern": "fast_moving",
            "description": f"High volume (avg {recent_avg:.1f} units/mo) and regular sales ({active_ratio:.0%} active).",
            "metrics": metrics,
        }

    # 4. Intermittent: sporadic, infrequent purchases (ADI > 1.32 or active_ratio <= 0.35)
    if (active_ratio <= 0.35 or adi >= 1.5) and months_since_last_sale < 6:
        return {
            "pattern": "intermittent",
            "description": f"Sporadic sales pattern with long intervals between orders (ADI {adi:.1f}).",
            "metrics": metrics,
        }

    # 5. Rising: strong upward demand trend
    if previous_avg >= 2.0 and trend_pct is not None and trend_pct >= 0.25:
        return {
            "pattern": "rising",
            "description": f"Demand expanding (+{trend_pct:.0%}) over recent periods.",
            "metrics": metrics,
        }

    # 6. Falling: strong downward demand trend
    if previous_avg >= 2.0 and trend_pct is not None and trend_pct <= -0.25:
        return {
            "pattern": "falling",
            "description": f"Demand declining ({trend_pct:.0%}) over recent periods.",
            "metrics": metrics,
        }

    # 7. Low Demand: low volume, but active recently
    if recent_avg > 0 and recent_avg < 5.0 and active_ratio > 0.35:
        return {
            "pattern": "low_demand",
            "description": f"Continuous low sales rate (avg {recent_avg:.1f} units/mo).",
            "metrics": metrics,
        }

    # 8. Stable/Normal: established product with steady demand
    return {
        "pattern": "stable/normal",
        "description": "Established product with steady, predictable baseline demand.",
        "metrics": metrics,
    }
