"""
Evaluation metrics for Forecast Benchmark V2.
Calculates MAE, WAPE, MASE, RMSE, Forecast Bias, Under-forecast rate, and Over-forecast rate.
"""

from typing import Sequence, Optional
import numpy as np


def calculate_mase_scale(
    train_history: Optional[Sequence[float]],
    season_length: int = 12,
) -> Optional[float]:
    """
    Computes the in-sample naive error scaling factor for MASE using historical training data only.
    
    1. If training length > season_length, attempts seasonal naive scale:
       mean(|y_t - y_{t-m}|) for t = m+1 .. T.
    2. If seasonal scale is not usable (or len <= season_length), falls back to lag-1 naive scale:
       mean(|y_t - y_{t-1}|) for t = 2 .. T.
    3. If all differences are zero (e.g., constant series or zero-demand) or insufficient history,
       returns None indicating undefined scaling factor.
    """
    if train_history is None or len(train_history) <= 1:
        return None

    train_arr = np.asarray(train_history, dtype=float)
    scale = None

    # 1. Attempt seasonal lag-12 naive scale
    if len(train_arr) > season_length:
        seasonal_diff = np.abs(train_arr[season_length:] - train_arr[:-season_length])
        s_scale = float(np.mean(seasonal_diff))
        if s_scale > 0:
            scale = s_scale

    # 2. Fallback to standard 1-lag naive scale
    if scale is None and len(train_arr) > 1:
        lag1_diff = np.abs(train_arr[1:] - train_arr[:-1])
        l1_scale = float(np.mean(lag1_diff))
        if l1_scale > 0:
            scale = l1_scale

    return scale


def calculate_metrics(
    actual: Sequence[float],
    predicted: Sequence[float],
    train_history: Optional[Sequence[float]] = None,
    scaled_errors: Optional[Sequence[Optional[float]]] = None,
    season_length: int = 12,
) -> dict[str, Optional[float]]:
    """
    Computes comprehensive evaluation metrics comparing actual vs predicted demand.
    
    Metrics returned:
    - sample_count: number of evaluation points
    - mae: Mean Absolute Error
    - rmse: Root Mean Squared Error
    - wape: Weighted Absolute Percentage Error (sum(|y - y_hat|) / sum(y))
    - mase: Mean Absolute Scaled Error (scaled by in-sample training naive error)
    - bias: Mean Error (y_hat - y). Positive = over-forecast, Negative = under-forecast
    - under_forecast_rate: fraction of observations where y_hat < y (stockout risk)
    - over_forecast_rate: fraction of observations where y_hat > y (excess stock risk)
    """
    actual_arr = np.asarray(actual, dtype=float)
    predicted_arr = np.asarray(predicted, dtype=float)

    if len(actual_arr) == 0:
        return {
            "sample_count": 0,
            "mae": None,
            "rmse": None,
            "wape": None,
            "mase": None,
            "bias": None,
            "under_forecast_rate": None,
            "over_forecast_rate": None,
        }

    if len(actual_arr) != len(predicted_arr):
        raise ValueError(
            f"Actual ({len(actual_arr)}) and predicted ({len(predicted_arr)}) lengths must match."
        )

    n = len(actual_arr)
    diff = predicted_arr - actual_arr
    abs_diff = np.abs(diff)

    # 1. MAE
    mae_val = float(np.mean(abs_diff))

    # 2. RMSE
    rmse_val = float(np.sqrt(np.mean(diff ** 2)))

    # 3. WAPE: sum(|y - y_hat|) / sum(y)
    actual_sum = float(np.sum(np.abs(actual_arr)))
    if actual_sum > 0:
        wape_val = float(np.sum(abs_diff) / actual_sum)
    else:
        # Edge Case (Audit Task 3): When total actual demand is zero,
        # WAPE is mathematically undefined (division by zero).
        # We record as NaN/None rather than an arbitrary 1.0 or 0.0,
        # ensuring arbitrarily large misses do not produce misleading WAPE=1.
        # MAE, RMSE, bias, and absolute errors remain fully available.
        wape_val = float("nan")

    # 4. MASE: Mean Absolute Scaled Error
    mase_val = float("nan")
    if scaled_errors is not None:
        valid_scaled = [s for s in scaled_errors if s is not None and not np.isnan(s)]
        if len(valid_scaled) > 0:
            mase_val = float(np.mean(valid_scaled))
    elif train_history is not None:
        scale = calculate_mase_scale(train_history, season_length=season_length)
        if scale is not None and scale > 0:
            mase_val = float(mae_val / scale)

    # 5. Forecast Bias: mean(predicted - actual)
    bias_val = float(np.mean(diff))

    # 6. Under-forecast rate: predicted < actual
    under_rate = float(np.mean(predicted_arr < actual_arr))

    # 7. Over-forecast rate: predicted > actual
    over_rate = float(np.mean(predicted_arr > actual_arr))

    return {
        "sample_count": n,
        "mae": round(mae_val, 4),
        "rmse": round(rmse_val, 4),
        "wape": round(wape_val, 4) if not np.isnan(wape_val) else None,
        "mase": round(mase_val, 4) if not np.isnan(mase_val) else None,
        "bias": round(bias_val, 4),
        "under_forecast_rate": round(under_rate, 4),
        "over_forecast_rate": round(over_rate, 4),
    }

