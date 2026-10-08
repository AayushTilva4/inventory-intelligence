import math
from typing import Any
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Canonical Thresholds for Forecast Confidence
# ---------------------------------------------------------------------------
# Derived from empirical out-of-sample distribution across the catalog:
# - High confidence: Strong historical accuracy (WAPE <= 35%, MASE <= 1.0)
# - Normal confidence: Acceptable historical accuracy (WAPE <= 50%, MASE <= 1.25)
# - Low confidence: High error (WAPE > 50% or MASE > 1.25) or sparse data
# - Trivial zero: Dead stock / zero recent actual demand
# ---------------------------------------------------------------------------
HIGH_CONFIDENCE_MAX_WAPE = 0.35
NORMAL_CONFIDENCE_MAX_WAPE = 0.50

HIGH_CONFIDENCE_MAX_MASE = 1.00
NORMAL_CONFIDENCE_MAX_MASE = 1.25

MIN_OBSERVATIONS_FOR_CONFIDENCE = 5
MIN_HISTORY_MONTHS_FOR_CONFIDENCE = 12


def calculate_forecast_error_metrics(
    actual: pd.Series | list[float] | np.ndarray,
    forecast: pd.Series | list[float] | np.ndarray,
    train: pd.Series | list[float] | np.ndarray | None = None,
    season_length: int = 12,
) -> dict[str, Any]:
    """
    Calculate canonical forecast error metrics point-in-time:
    - WAPE (Weighted Absolute Percentage Error)
    - MASE (Mean Absolute Scaled Error)
    - MAE (Mean Absolute Error)
    - RMSE (Root Mean Squared Error)
    - Bias (Mean Signed Error: forecast - actual)
    - Underforecast rate (fraction where forecast < actual)
    - Overforecast rate (fraction where forecast > actual)
    - Observation count (number of valid evaluation periods)
    """
    y = np.asarray(actual, dtype=float)
    y_hat = np.asarray(forecast, dtype=float)

    # Filter any NaN or infinite values
    valid_mask = np.isfinite(y) & np.isfinite(y_hat)
    y = y[valid_mask]
    y_hat = y_hat[valid_mask]

    n = len(y)
    if n == 0:
        return {
            "observation_count": 0,
            "wape": None,
            "mase": None,
            "mae": None,
            "rmse": None,
            "bias": None,
            "underforecast_rate": None,
            "overforecast_rate": None,
            "actual_sum": 0.0,
            "forecast_sum": 0.0,
        }

    abs_err = np.abs(y - y_hat)
    err = y_hat - y  # positive = overforecast, negative = underforecast

    mae_val = float(np.mean(abs_err))
    rmse_val = float(np.sqrt(np.mean((y - y_hat) ** 2)))
    bias_val = float(np.mean(err))

    under_rate = float(np.mean(y_hat < y))
    over_rate = float(np.mean(y_hat > y))

    sum_actual = float(np.sum(np.abs(y)))
    sum_abs_err = float(np.sum(abs_err))
    actual_sum = float(np.sum(y))
    forecast_sum = float(np.sum(y_hat))

    # WAPE calculation with safe zero-denominator handling
    if sum_actual > 0:
        wape_val = sum_abs_err / sum_actual
    else:
        # Actual demand was zero across the entire evaluation window
        wape_val = 0.0 if sum_abs_err == 0 else float("inf")

    # MASE calculation with safe scale handling
    mase_val = None
    if train is not None:
        y_train = np.asarray(train, dtype=float)
        valid_train = y_train[np.isfinite(y_train)]
        if len(valid_train) >= 2:
            # 1-step naive scale on train history
            naive_diffs = np.abs(np.diff(valid_train))
            scale = float(np.mean(naive_diffs)) if len(naive_diffs) > 0 else 0.0
            if scale > 1e-9:
                mase_val = mae_val / scale

    return {
        "observation_count": n,
        "wape": wape_val,
        "mase": mase_val,
        "mae": mae_val,
        "rmse": rmse_val,
        "bias": bias_val,
        "underforecast_rate": under_rate,
        "overforecast_rate": over_rate,
        "actual_sum": actual_sum,
        "forecast_sum": forecast_sum,
    }


def classify_forecast_confidence(
    wape: float | None,
    mase: float | None = None,
    observation_count: int = 0,
    dead_stock: bool = False,
    is_sparse: bool = False,
    actual_sum: float | None = None,
    forecast_sum: float | None = None,
) -> tuple[str, str]:
    """
    Classify forecast confidence based strictly on predictive reliability:
    Returns (confidence_level, reason_code).

    Levels:
    - 'trivial_zero': Dead stock or zero demand series.
    - 'high': Strong predictive reliability (WAPE <= 0.35, MASE <= 1.0).
    - 'normal': Acceptable reliability (WAPE <= 0.50, MASE <= 1.25).
    - 'low': Weak reliability (WAPE > 0.50 or MASE > 1.25) or insufficient data.
    """
    # 1. Dead stock or zero demand window
    if dead_stock or (
        actual_sum is not None
        and actual_sum == 0
        and (forecast_sum is None or forecast_sum == 0)
    ):
        return "trivial_zero", "dead_stock_zero_demand"

    if actual_sum is not None and actual_sum == 0 and forecast_sum is not None and forecast_sum > 0:
        return "trivial_zero", "zero_actual_demand_window"

    # 2. Sparse history / insufficient evaluation observations
    if is_sparse or observation_count < MIN_OBSERVATIONS_FOR_CONFIDENCE:
        return "low", "sparse_history"

    # 3. Invalid / undefined / infinite WAPE
    if wape is None or not math.isfinite(wape):
        return "low", "undefined_or_infinite_error"

    # 4. Canonical Error Thresholds
    # A group with >50% WAPE can NEVER be 'normal' or 'high'.
    if wape <= HIGH_CONFIDENCE_MAX_WAPE:
        if mase is not None and math.isfinite(mase) and mase > NORMAL_CONFIDENCE_MAX_MASE:
            return "low", f"high_mase_penalty_{mase:.2f}"
        elif mase is not None and math.isfinite(mase) and mase > HIGH_CONFIDENCE_MAX_MASE:
            return "normal", f"mase_moderation_{mase:.2f}"
        else:
            return "high", f"wape_{wape:.4f}"

    elif wape <= NORMAL_CONFIDENCE_MAX_WAPE:
        if mase is not None and math.isfinite(mase) and mase > NORMAL_CONFIDENCE_MAX_MASE:
            return "low", f"high_mase_penalty_{mase:.2f}"
        else:
            return "normal", f"wape_{wape:.4f}"

    else:
        # WAPE > 50%
        return "low", f"wape_over_50_pct_{wape:.4f}"
