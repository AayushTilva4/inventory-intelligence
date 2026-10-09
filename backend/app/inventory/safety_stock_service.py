"""
Phase 2 Task 6: Safety Stock from Forecast Error.

Implements evidence-based safety stock derived from historical out-of-sample
forecast errors, horizon scaling (Lead Time + Review Period), pattern-aware
service levels, and robust fallback for sparse histories.
"""

from __future__ import annotations

import math
from typing import Any
import numpy as np
import pandas as pd

from app.forecasting.benchmark_v2.models import forecast_multistep

# Canonical Service Level Policies by Demand Pattern
PATTERN_SERVICE_LEVELS: dict[str, float] = {
    "fast_moving": 0.80,
    "stable": 0.80,
    "normal": 0.80,
    "rising": 0.75,
    "falling": 0.75,
    "intermittent": 0.75,
    "cold_start": 0.75,
    "dead_stock": 0.00,
}

# Empirical Fallback CV (Coefficient of Variation) by Demand Pattern
PATTERN_FALLBACK_CV: dict[str, float] = {
    "fast_moving": 0.40,
    "stable": 0.20,
    "normal": 0.20,
    "rising": 0.35,
    "falling": 0.35,
    "intermittent": 0.50,
    "cold_start": 0.30,
    "dead_stock": 0.00,
}

# Standard normal inverse CDF (quantile function) approximation
# Rational approximation for Phi^-1(p) with high numerical precision
def get_z_score(service_level: float) -> float:
    """
    Returns the standard normal critical value Z_alpha for a given cycle service level.
    """
    if service_level <= 0.0:
        return 0.0
    if service_level >= 1.0:
        return 3.0902  # 99.9% clamp

    # Direct standard normal quantile for common service levels
    standard_z = {
        0.50: 0.0000,
        0.70: 0.5244,
        0.75: 0.6745,
        0.80: 0.8416,
        0.85: 1.0364,
        0.90: 1.2816,
        0.95: 1.6449,
        0.99: 2.3263,
    }
    rounded_sl = round(service_level, 2)
    if rounded_sl in standard_z:
        return standard_z[rounded_sl]

    # Acklam's approximation for arbitrary service levels
    p = service_level
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02, 1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02, 6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00, -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00]

    q = min(p, 1.0 - p)
    if q > 0.02425:
        r = q - 0.5
        r2 = r * r
        z = (((((a[0]*r2 + a[1])*r2 + a[2])*r2 + a[3])*r2 + a[4])*r2 + a[5])*r / (((((b[0]*r2 + b[1])*r2 + b[2])*r2 + b[3])*r2 + b[4])*r2 + 1.0)
    else:
        r = math.sqrt(-2.0 * math.log(q))
        z = (((((c[0]*r + c[1])*r + c[2])*r + c[3])*r + c[4])*r + c[5]) / ((((d[0]*r + d[1])*r + d[2])*r + d[3])*r + 1.0)
    
    if p < 0.5:
        z = -z
    return float(z)


def compute_historical_forecast_error(
    sales: pd.Series | Sequence[float],
    model_name: str = "trimmed_mean_3",
    min_origins: int = 5,
) -> tuple[float | None, int]:
    """
    Computes empirical out-of-sample 1-step forecast RMSE using rolling origins
    strictly terminating at historical boundaries (no future leakage).

    Returns:
        (sigma_error, observation_count)
    """
    if sales is None or len(sales) < 6:
        return None, 0

    series = pd.Series(sales, dtype=float).reset_index(drop=True)
    n = len(series)
    errors: list[float] = []

    # Rolling walk-forward origins
    for origin_idx in range(6, n):
        train_slice = series.iloc[:origin_idx].reset_index(drop=True)
        act_val = float(series.iloc[origin_idx])
        
        try:
            preds = forecast_multistep(model_name, train_slice, max_horizon=1)
            pred_val = float(preds[0]) if preds else 0.0
        except Exception:
            pred_val = float(train_slice.iloc[-1]) if not train_slice.empty else 0.0

        errors.append(pred_val - act_val)

    if len(errors) < min_origins:
        return None, len(errors)

    err_arr = np.asarray(errors, dtype=float)
    rmse = float(np.sqrt(np.mean(err_arr ** 2)))
    return round(rmse, 4), len(errors)


def calculate_error_based_safety_stock(
    forecasted_horizon_demand: float,
    lead_time_months: float = 3.0,
    review_period_months: float = 1.0,
    demand_pattern: str = "normal",
    service_level: float | None = None,
    sigma_error: float | None = None,
    dead_stock: bool = False,
    cap_factor: float = 1.5,
) -> dict[str, Any]:
    """
    Calculates safety stock derived from forecast error over the operational horizon.

    Equation:
        Operational Horizon H = L + R (e.g. 3 + 1 = 4 months)
        Horizon Error Scale: sigma_H = sqrt(L + R) * sigma_error = 2.0 * sigma_error
        Raw Safety Stock: SS_raw = Z_alpha * sigma_H
        Capped Safety Stock: SS = min(SS_raw, max(1.5 * D_horizon, 10.0))

    Guarantees:
        - Dead stock invariant: 0.0 buffer
        - Non-negative: SS >= 0.0
        - Noisy items get larger buffers; steady items get smaller buffers
        - Robust fallback for low-data series
    """
    fc = max(0.0, float(forecasted_horizon_demand or 0.0))

    if dead_stock or fc <= 0.0:
        return {
            "safety_stock": 0.0,
            "service_level": 0.0,
            "z_score": 0.0,
            "sigma_error_1m": 0.0,
            "sigma_horizon": 0.0,
            "horizon_scale_factor": 2.0,
            "raw_safety_stock": 0.0,
            "cap_applied": False,
            "cap_value": 0.0,
            "safety_stock_method": "dead_stock" if dead_stock else "zero_forecast",
            "fallback_used": False,
            "dead_stock_safeguard": True,
        }

    pat = str(demand_pattern or "normal").lower()
    sl = float(service_level) if service_level is not None else PATTERN_SERVICE_LEVELS.get(pat, 0.75)
    z = get_z_score(sl)

    operational_horizon = max(0.1, float(lead_time_months + review_period_months))
    horizon_scale_factor = math.sqrt(operational_horizon)

    if sigma_error is not None:
        sigma_1m = max(0.0, float(sigma_error))
        fallback_used = False
        method = "zero_error" if sigma_1m == 0.0 else "error_based"
    else:
        # Fallback CV scaled to monthly equivalent demand
        cv = PATTERN_FALLBACK_CV.get(pat, 0.25)
        monthly_demand_est = fc / operational_horizon
        sigma_1m = cv * monthly_demand_est
        fallback_used = True
        method = "pattern_fallback"

    sigma_horizon = horizon_scale_factor * sigma_1m
    raw_ss = z * sigma_horizon

    # Outlier safety cap to prevent unrealistic buffers
    max_cap = max(fc * cap_factor, 10.0)
    cap_applied = raw_ss > max_cap
    safety_stock = round(max(0.0, min(raw_ss, max_cap)), 4)

    return {
        "safety_stock": safety_stock,
        "service_level": round(sl, 4),
        "z_score": round(z, 4),
        "sigma_error_1m": round(sigma_1m, 4),
        "sigma_horizon": round(sigma_horizon, 4),
        "horizon_scale_factor": round(horizon_scale_factor, 4),
        "raw_safety_stock": round(raw_ss, 4),
        "cap_applied": cap_applied,
        "cap_value": round(max_cap, 4),
        "safety_stock_method": method,
        "fallback_used": fallback_used,
        "dead_stock_safeguard": False,
    }
