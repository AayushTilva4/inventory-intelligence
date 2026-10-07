"""
Model wrappers for Forecast Benchmark V2.
Wraps existing V1 models and provides systematic tuned variants of non-intermittent candidates
for multi-step horizons (1 to 5 months).
"""

import sys
from typing import Sequence
import numpy as np
import pandas as pd

from app.forecasting.engine_adapter import get_forecasting_engine_root

engine_root = str(get_forecasting_engine_root())
if engine_root not in sys.path:
    sys.path.insert(0, engine_root)

# Import untouched existing V1 forecasting functions
from src.forecasting import (
    previous_month_forecast,
    moving_average_forecast,
    seasonal_naive_forecast,
    croston_forecast,
    exponential_smoothing_forecast,
)

from statsmodels.tsa.holtwinters import ExponentialSmoothing

BASELINE_MODELS = [
    "previous_month",
    "moving_average_3",
    "seasonal_naive",
    "croston",
    "exponential_smoothing",
]

INTERMITTENT_MODELS = [
    "croston_sba",
    "croston_tsb",
    "ses",
    "zero_baseline",
    "median_baseline",
]

TUNED_NON_INTERMITTENT_MODELS = [
    "moving_average_2",
    "moving_average_4",
    "moving_average_6",
    "moving_average_9",
    "moving_average_12",
    "moving_average_wma_3",
    "moving_average_wma_4",
    "ses_alpha_01",
    "ses_alpha_03",
    "ses_alpha_05",
    "ses_opt",
    "ets_linear_trend",
    "ets_damped_nonseasonal",
    "ets_seasonal_damped",
    "seasonal_naive_adaptive",
]

ROBUST_FAST_MOVING_MODELS = [
    "rolling_median_3",
    "rolling_median_6",
    "trimmed_mean_3",
    "trimmed_mean_6",
    "winsorized_mean_3",
    "winsorized_mean_6",
]

ROUTER_MODELS = [
    "pattern_router",
    "pattern_router_b",
    "pattern_router_c",
    "pattern_router_d",
    "pattern_router_e",
]

BENCHMARK_MODELS = (
    BASELINE_MODELS
    + INTERMITTENT_MODELS
    + TUNED_NON_INTERMITTENT_MODELS
    + ROBUST_FAST_MOVING_MODELS
    + ROUTER_MODELS
)


def forecast_previous_month(history: pd.Series, max_horizon: int = 5) -> list[float]:
    """
    Persistence naive forecast for multi-step horizons.
    For all horizons h=1..max_horizon, the expected demand remains the last known value.
    """
    if history.empty:
        raise ValueError("Cannot forecast from an empty series.")
    last_val = previous_month_forecast(history)
    return [max(float(last_val), 0.0)] * max_horizon


def forecast_moving_average_3(history: pd.Series, max_horizon: int = 5) -> list[float]:
    """
    Moving average (window=3) recursive multi-step forecasting.
    For h=1: average of last 3 actuals.
    For h>1: recursively averages the previous 3 values (including forecasted values).
    """
    if history.empty:
        raise ValueError("Cannot forecast from an empty series.")

    values = list(history.astype(float).values)
    forecasts: list[float] = []

    for _ in range(max_horizon):
        window_slice = values[-3:] if len(values) >= 3 else values
        pred = float(np.mean(window_slice))
        pred = max(pred, 0.0)
        forecasts.append(pred)
        values.append(pred)

    return forecasts


def forecast_moving_average(
    history: pd.Series,
    max_horizon: int = 5,
    window: int = 3,
) -> list[float]:
    """
    Moving average recursive multi-step forecasting with arbitrary window.
    For h=1: average of last `window` actuals.
    For h>1: recursively averages the previous `window` values (including forecasted values).
    All forecasts floored at 0.0.
    """
    if history.empty:
        raise ValueError("Cannot forecast from an empty series.")
    if window < 1:
        raise ValueError(f"Window must be at least 1, got {window}")

    values = list(history.astype(float).values)
    forecasts: list[float] = []

    for _ in range(max_horizon):
        window_slice = values[-window:] if len(values) >= window else values
        pred = float(np.mean(window_slice)) if len(window_slice) > 0 else 0.0
        pred = max(pred, 0.0)
        forecasts.append(pred)
        values.append(pred)

    return forecasts


def forecast_weighted_moving_average(
    history: pd.Series,
    max_horizon: int = 5,
    window: int = 3,
) -> list[float]:
    """
    Linearly weighted moving average (WMA) recursive multi-step forecasting.
    Assigns linearly increasing weights 1..k to the most recent observations in the window,
    so the newest month receives the highest weight.
    All forecasts floored at 0.0.
    """
    if history.empty:
        raise ValueError("Cannot forecast from an empty series.")
    if window < 1:
        raise ValueError(f"Window must be at least 1, got {window}")

    values = list(history.astype(float).values)
    forecasts: list[float] = []

    for _ in range(max_horizon):
        window_slice = values[-window:] if len(values) >= window else values
        k = len(window_slice)
        if k == 0:
            pred = 0.0
        elif k == 1:
            pred = float(window_slice[0])
        else:
            weights = np.arange(1, k + 1, dtype=float)
            weights /= weights.sum()
            pred = float(np.dot(weights, window_slice))
        pred = max(pred, 0.0)
        forecasts.append(pred)
        values.append(pred)

    return forecasts


def forecast_rolling_median(
    history: pd.Series,
    max_horizon: int = 5,
    window: int = 3,
) -> list[float]:
    """
    Rolling median recursive multi-step forecasting.
    Takes the median of the trailing `window` observations (or all available if < window).
    At each step h>1, uses previous recursive forecasts.
    Floored at 0.0. Point-in-time safe and robust to extreme outliers.
    """
    if history.empty:
        raise ValueError("Cannot forecast from an empty series.")
    if window < 1:
        raise ValueError(f"Window must be at least 1, got {window}")

    values = list(history.astype(float).values)
    forecasts: list[float] = []

    for _ in range(max_horizon):
        window_slice = values[-window:] if len(values) >= window else values
        pred = float(np.median(window_slice)) if len(window_slice) > 0 else 0.0
        pred = max(pred, 0.0)
        forecasts.append(pred)
        values.append(pred)

    return forecasts


def forecast_trimmed_mean(
    history: pd.Series,
    max_horizon: int = 5,
    window: int = 3,
) -> list[float]:
    """
    Trimmed mean recursive multi-step forecasting with deterministic trimming rules:
    - For window=3: takes trailing 3 observations, drops the single highest outlier,
      and averages the remaining 2 observations. (If history < 3, averages available).
    - For window=6: takes trailing 6 observations, drops 1 minimum and 1 maximum outlier,
      and averages the middle 4 observations. (If history < 4, averages available).
    - For other windows: if k >= 4, drops 1 min and 1 max; else averages available.
    Floored at 0.0.
    """
    if history.empty:
        raise ValueError("Cannot forecast from an empty series.")
    if window < 1:
        raise ValueError(f"Window must be at least 1, got {window}")

    values = list(history.astype(float).values)
    forecasts: list[float] = []

    for _ in range(max_horizon):
        window_slice = values[-window:] if len(values) >= window else values
        k = len(window_slice)
        if k == 0:
            pred = 0.0
        elif k < 3:
            pred = float(np.mean(window_slice))
        elif window == 3 and k == 3:
            # Sort and trim highest outlier
            sorted_v = sorted(window_slice)
            pred = float(np.mean(sorted_v[:2]))
        elif k >= 4:
            # Sort and trim 1 min and 1 max
            sorted_v = sorted(window_slice)
            pred = float(np.mean(sorted_v[1:-1]))
        else:
            pred = float(np.mean(window_slice))

        pred = max(pred, 0.0)
        forecasts.append(pred)
        values.append(pred)

    return forecasts


def forecast_winsorized_mean(
    history: pd.Series,
    max_horizon: int = 5,
    window: int = 3,
) -> list[float]:
    """
    Winsorized mean recursive multi-step forecasting with deterministic winsorization rules:
    - For window=3: takes trailing 3 observations, sorts them [v0, v1, v2], and winsorizes
      the maximum to the second highest: v2 -> v1, yielding [v0, v1, v1], then averages.
      (Dampens spikes without dropping data entirely).
    - For window=6: takes trailing 6 observations, sorts them [v0, v1, v2, v3, v4, v5],
      replaces min with 2nd lowest (v0 -> v1), replaces max with 2nd highest (v5 -> v4),
      then averages. (If k < 4, averages available).
    Floored at 0.0.
    """
    if history.empty:
        raise ValueError("Cannot forecast from an empty series.")
    if window < 1:
        raise ValueError(f"Window must be at least 1, got {window}")

    values = list(history.astype(float).values)
    forecasts: list[float] = []

    for _ in range(max_horizon):
        window_slice = values[-window:] if len(values) >= window else values
        k = len(window_slice)
        if k == 0:
            pred = 0.0
        elif k < 3:
            pred = float(np.mean(window_slice))
        elif window == 3 and k == 3:
            sorted_v = sorted(window_slice)
            # Winsorize max to 2nd highest
            winsorized = [sorted_v[0], sorted_v[1], sorted_v[1]]
            pred = float(np.mean(winsorized))
        elif k >= 4:
            sorted_v = sorted(window_slice)
            winsorized = list(sorted_v)
            winsorized[0] = winsorized[1]
            winsorized[-1] = winsorized[-2]
            pred = float(np.mean(winsorized))
        else:
            pred = float(np.mean(window_slice))

        pred = max(pred, 0.0)
        forecasts.append(pred)
        values.append(pred)

    return forecasts


def forecast_seasonal_naive(
    history: pd.Series,
    max_horizon: int = 5,
    season_length: int = 12,
) -> list[float]:
    """
    Seasonal naive multi-step forecast.
    For horizon h (target step T+h), the forecast uses the observation from
    the same calendar month 12 months prior (index len(history) + h - 1 - season_length).
    If history < season_length, falls back to the last known value.
    """
    if history.empty:
        raise ValueError("Cannot forecast from an empty series.")

    n = len(history)
    forecasts: list[float] = []

    for h in range(1, max_horizon + 1):
        target_lag_idx = n + h - 1 - season_length
        if 0 <= target_lag_idx < n:
            val = float(history.iloc[target_lag_idx])
        else:
            val = float(history.iloc[-1])
        forecasts.append(max(val, 0.0))

    return forecasts


def forecast_seasonal_naive_adaptive(
    history: pd.Series,
    max_horizon: int = 5,
    season_length: int = 12,
    min_seasonal_history: int = 24,
) -> list[float]:
    """
    Adaptive Seasonal Naive multi-step forecast.
    Does NOT force seasonal naive behavior when history does not support meaningful 12-month seasonality:
    - If history < 24 months (< 2 full seasonal cycles), falls back to persistence naive (previous_month).
    - If history >= 24 months, verifies series has non-constant values and uses seasonal naive;
      if series is flat or degenerate, falls back safely.
    All forecasts floored at 0.0.
    """
    if history.empty:
        raise ValueError("Cannot forecast from an empty series.")

    n = len(history)
    if n < min_seasonal_history:
        last_val = max(float(history.iloc[-1]), 0.0)
        return [last_val] * max_horizon

    values = history.astype(float).values
    if np.all(values == values[0]):
        return [max(float(values[0]), 0.0)] * max_horizon

    forecasts: list[float] = []
    for h in range(1, max_horizon + 1):
        target_lag_idx = n + h - 1 - season_length
        if 0 <= target_lag_idx < n:
            val = float(history.iloc[target_lag_idx])
        else:
            val = float(history.iloc[-1])
        forecasts.append(max(val, 0.0))

    return forecasts


def forecast_croston(history: pd.Series, max_horizon: int = 5, alpha: float = 0.1) -> list[float]:
    """
    Croston's method for intermittent demand across multi-step horizons.
    Croston estimates an expected demand rate (size / interval).
    For future periods h=1..max_horizon, the expected demand rate is constant.
    """
    if history.empty:
        raise ValueError("Cannot forecast from an empty series.")

    rate = croston_forecast(history, alpha=alpha)
    return [max(float(rate), 0.0)] * max_horizon


def forecast_exponential_smoothing(
    history: pd.Series,
    max_horizon: int = 5,
    seasonal_periods: int | None = 12,
) -> list[float]:
    """
    Exponential Smoothing multi-step forecast using statsmodels Holt-Winters.
    Uses additive damped trend (and additive seasonal if len >= 24) matching the V1 engine,
    then generates forecasts for steps 1..max_horizon floored at 0.0.
    """
    if history.empty:
        raise ValueError("Cannot forecast from an empty series.")

    series = history.astype(float).reset_index(drop=True)

    if len(series) < 4:
        mean_val = max(float(series.mean()), 0.0)
        return [mean_val] * max_horizon

    use_seasonal = (
        seasonal_periods is not None
        and seasonal_periods > 1
        and len(series) >= 2 * seasonal_periods
    )

    if use_seasonal:
        model = ExponentialSmoothing(
            series,
            trend="add",
            damped_trend=True,
            seasonal="add",
            seasonal_periods=seasonal_periods,
            initialization_method="estimated",
        )
    else:
        model = ExponentialSmoothing(
            series,
            trend="add",
            damped_trend=True,
            seasonal=None,
            initialization_method="estimated",
        )

    fitted_model = model.fit(optimized=True)
    fc_values = fitted_model.forecast(max_horizon)
    return [max(float(val), 0.0) for val in fc_values]


def forecast_ets(
    history: pd.Series,
    max_horizon: int = 5,
    trend: str | None = "add",
    damped_trend: bool = True,
    seasonal: str | None = None,
    seasonal_periods: int | None = 12,
) -> list[float]:
    """
    Configurable Holt-Winters Exponential Smoothing with safe parameter bounds,
    non-negative guarantees, and graceful convergence fallback.
    """
    if history.empty:
        raise ValueError("Cannot forecast from an empty series.")

    series = history.astype(float).reset_index(drop=True)

    if len(series) < 4:
        mean_val = max(float(series.mean()), 0.0)
        return [mean_val] * max_horizon

    if np.all(series.values == series.values[0]):
        return [max(float(series.values[0]), 0.0)] * max_horizon

    use_seasonal = (
        seasonal is not None
        and seasonal_periods is not None
        and seasonal_periods > 1
        and len(series) >= 2 * seasonal_periods
    )
    actual_seasonal = seasonal if use_seasonal else None
    actual_sp = seasonal_periods if use_seasonal else None

    actual_trend = trend if len(series) >= 4 else None
    actual_damped = damped_trend if actual_trend is not None else False

    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = ExponentialSmoothing(
                series,
                trend=actual_trend,
                damped_trend=actual_damped,
                seasonal=actual_seasonal,
                seasonal_periods=actual_sp,
                initialization_method="estimated",
            )
            fitted_model = model.fit(optimized=True)
            fc_values = fitted_model.forecast(max_horizon)
            return [max(float(val), 0.0) for val in fc_values]
    except Exception:
        val = ses_forecast_fixed(history, alpha=0.2)
        return [max(float(val), 0.0)] * max_horizon


def croston_sba_forecast(series: pd.Series, alpha: float = 0.1) -> float:
    """
    Croston's method with Syntetos-Boylan Approximation (SBA).
    Multiplies the standard Croston rate by (1 - alpha / 2) to correct for its upward bias.
    """
    rate = croston_forecast(series, alpha=alpha)
    if rate <= 0.0:
        return 0.0
    sba_rate = (1.0 - (alpha / 2.0)) * rate
    return max(float(sba_rate), 0.0)


def forecast_croston_sba(
    history: pd.Series,
    max_horizon: int = 5,
    alpha: float = 0.1,
) -> list[float]:
    """
    Croston SBA multi-step forecast.
    Flat forecast rate across future horizons h=1..max_horizon floored at 0.0.
    """
    if history.empty:
        raise ValueError("Cannot forecast from an empty series.")
    rate = croston_sba_forecast(history, alpha=alpha)
    return [max(float(rate), 0.0)] * max_horizon


def croston_tsb_forecast(
    series: pd.Series,
    alpha: float = 0.1,
    beta: float = 0.1,
) -> float:
    """
    Teunter-Syntetos-Babai (TSB) method for intermittent and obsolescent demand.
    Separates demand size z (updated only on non-zero periods) and demand probability p
    (updated every period). When demand is 0, p decays by (1 - beta), safely handling
    long runs of zero demand without artificial upward spikes.
    """
    values = series.astype(float).to_numpy()
    if len(values) == 0:
        raise ValueError("Cannot forecast from an empty series.")

    if (values > 0).sum() == 0:
        return 0.0

    first_nonzero = int(np.argmax(values > 0))
    z = float(values[first_nonzero])
    p = 1.0 / (first_nonzero + 1) if first_nonzero > 0 else 1.0

    for t in range(first_nonzero + 1, len(values)):
        if values[t] > 0:
            z = alpha * float(values[t]) + (1.0 - alpha) * z
            p = beta * 1.0 + (1.0 - beta) * p
        else:
            p = (1.0 - beta) * p

    forecast = p * z
    return max(float(forecast), 0.0)


def forecast_croston_tsb(
    history: pd.Series,
    max_horizon: int = 5,
    alpha: float = 0.1,
    beta: float = 0.1,
) -> list[float]:
    """
    Croston TSB multi-step forecast.
    Flat expected demand rate (p_T * z_T) across future horizons h=1..max_horizon floored at 0.0.
    """
    if history.empty:
        raise ValueError("Cannot forecast from an empty series.")
    rate = croston_tsb_forecast(history, alpha=alpha, beta=beta)
    return [max(float(rate), 0.0)] * max_horizon


def optimize_ses_alpha(
    values: np.ndarray | Sequence[float],
    candidate_alphas: Sequence[float] = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8),
) -> float:
    """
    Determines optimal SES smoothing parameter alpha strictly on training history
    by minimizing 1-step-ahead in-sample Sum of Squared Errors (SSE).
    Deterministic, point-in-time safe, and free from numerical solver instability.
    """
    arr = np.asarray(values, dtype=float)
    if len(arr) < 2 or np.all(arr == arr[0]):
        return 0.2

    best_alpha = 0.2
    best_sse = float("inf")

    for a in candidate_alphas:
        level = float(arr[0])
        sse = 0.0
        for t in range(1, len(arr)):
            err = float(arr[t]) - level
            sse += err * err
            level = a * float(arr[t]) + (1.0 - a) * level
        if sse < best_sse:
            best_sse = sse
            best_alpha = float(a)

    return best_alpha


def ses_forecast_fixed(series: pd.Series, alpha: float = 0.2) -> float:
    """
    Fixed-alpha Simple Exponential Smoothing recurrence level forecast.
    Guaranteed deterministic, non-negative, with robust recurrence.
    """
    if series.empty:
        raise ValueError("Cannot forecast from an empty series.")

    values = series.astype(float).to_numpy()
    if len(values) == 0:
        raise ValueError("Cannot forecast from an empty series.")
    if len(values) == 1 or np.all(values == values[0]):
        return max(float(values[0]), 0.0)
    if len(values) < 3:
        return max(float(np.mean(values)), 0.0)

    level = float(values[0])
    for val in values[1:]:
        level = alpha * float(val) + (1.0 - alpha) * level
    return max(float(level), 0.0)


def forecast_ses_optimized(history: pd.Series, max_horizon: int = 5) -> list[float]:
    """
    SES multi-step forecast using deterministic SSE-optimized alpha determined
    strictly on training history up to origin.
    """
    if history.empty:
        raise ValueError("Cannot forecast from an empty series.")
    vals = history.astype(float).to_numpy()
    opt_alpha = optimize_ses_alpha(vals)
    pred = ses_forecast_fixed(history, alpha=opt_alpha)
    return [max(float(pred), 0.0)] * max_horizon


def ses_forecast(series: pd.Series, alpha: float = 0.2) -> float:
    """
    Simple Exponential Smoothing (SES) level-only point forecast.
    Uses statsmodels SimpleExpSmoothing when variation exists, with robust
    alpha=0.2 recurrence fallback on short, constant, or edge-case series.
    """
    if series.empty:
        raise ValueError("Cannot forecast from an empty series.")

    values = series.astype(float).to_numpy()
    if len(values) == 0:
        raise ValueError("Cannot forecast from an empty series.")

    if len(values) == 1 or np.all(values == values[0]):
        return max(float(values[0]), 0.0)

    if len(values) < 4:
        return max(float(np.mean(values)), 0.0)

    try:
        from statsmodels.tsa.holtwinters import SimpleExpSmoothing
        model = SimpleExpSmoothing(values, initialization_method="estimated")
        fitted = model.fit(optimized=True)
        fc = float(fitted.forecast(1)[0])
        return max(fc, 0.0)
    except Exception:
        level = float(values[0])
        for val in values[1:]:
            level = alpha * float(val) + (1.0 - alpha) * level
        return max(level, 0.0)


def forecast_ses(
    history: pd.Series,
    max_horizon: int = 5,
    alpha: float = 0.2,
) -> list[float]:
    """
    Simple Exponential Smoothing multi-step forecast.
    Flat level forecast across future horizons h=1..max_horizon floored at 0.0.
    """
    if history.empty:
        raise ValueError("Cannot forecast from an empty series.")
    val = ses_forecast(history, alpha=alpha)
    return [max(float(val), 0.0)] * max_horizon


def forecast_zero_baseline(
    history: pd.Series,
    max_horizon: int = 5,
) -> list[float]:
    """
    Zero baseline: always forecasts 0.0 across all future horizons.
    Essential benchmark reference for dead stock and obsolete items.
    """
    if history.empty:
        raise ValueError("Cannot forecast from an empty series.")
    return [0.0] * max_horizon


def forecast_median_baseline(
    history: pd.Series,
    max_horizon: int = 5,
) -> list[float]:
    """
    Median baseline: forecasts the in-sample historical median for all future horizons.
    Optimal point forecast under MAE (L1 loss). Strictly as-of-origin.
    """
    if history.empty:
        raise ValueError("Cannot forecast from an empty series.")
    med = float(history.astype(float).median())
    return [max(med, 0.0)] * max_horizon


def forecast_multistep(
    model_name: str,
    history: pd.Series,
    max_horizon: int = 5,
) -> list[float]:
    """
    Dispatches multi-step forecasting to the requested model.
    Returns a list of floats of length max_horizon for h=1..max_horizon.
    """
    # 1. Baseline models
    if model_name == "previous_month":
        return forecast_previous_month(history, max_horizon)
    elif model_name == "moving_average_3":
        return forecast_moving_average_3(history, max_horizon)
    elif model_name == "seasonal_naive":
        return forecast_seasonal_naive(history, max_horizon)
    elif model_name == "croston":
        return forecast_croston(history, max_horizon)
    elif model_name == "exponential_smoothing":
        return forecast_exponential_smoothing(history, max_horizon)

    # 2. Intermittent models (Step 3)
    elif model_name == "croston_sba":
        return forecast_croston_sba(history, max_horizon)
    elif model_name == "croston_tsb":
        return forecast_croston_tsb(history, max_horizon)
    elif model_name == "ses":
        return forecast_ses(history, max_horizon)
    elif model_name == "zero_baseline":
        return forecast_zero_baseline(history, max_horizon)
    elif model_name == "median_baseline":
        return forecast_median_baseline(history, max_horizon)

    # 3. Tuned Non-Intermittent models (Step 4)
    # Moving Average variants
    elif model_name == "moving_average_2":
        return forecast_moving_average(history, max_horizon, window=2)
    elif model_name == "moving_average_4":
        return forecast_moving_average(history, max_horizon, window=4)
    elif model_name == "moving_average_6":
        return forecast_moving_average(history, max_horizon, window=6)
    elif model_name == "moving_average_9":
        return forecast_moving_average(history, max_horizon, window=9)
    elif model_name == "moving_average_12":
        return forecast_moving_average(history, max_horizon, window=12)
    elif model_name == "moving_average_wma_3":
        return forecast_weighted_moving_average(history, max_horizon, window=3)
    elif model_name == "moving_average_wma_4":
        return forecast_weighted_moving_average(history, max_horizon, window=4)

    # SES variants
    elif model_name == "ses_alpha_01":
        val = ses_forecast_fixed(history, alpha=0.1)
        return [max(float(val), 0.0)] * max_horizon
    elif model_name == "ses_alpha_02":
        val = ses_forecast_fixed(history, alpha=0.2)
        return [max(float(val), 0.0)] * max_horizon
    elif model_name == "ses_alpha_03":
        val = ses_forecast_fixed(history, alpha=0.3)
        return [max(float(val), 0.0)] * max_horizon
    elif model_name == "ses_alpha_05":
        val = ses_forecast_fixed(history, alpha=0.5)
        return [max(float(val), 0.0)] * max_horizon
    elif model_name == "ses_opt":
        return forecast_ses_optimized(history, max_horizon)

    # Exponential Smoothing (ETS) variants
    elif model_name == "ets_linear_trend":
        return forecast_ets(history, max_horizon, trend="add", damped_trend=False, seasonal=None)
    elif model_name == "ets_damped_nonseasonal":
        return forecast_ets(history, max_horizon, trend="add", damped_trend=True, seasonal=None)
    elif model_name == "ets_seasonal_damped":
        return forecast_ets(history, max_horizon, trend="add", damped_trend=True, seasonal="add", seasonal_periods=12)

    # Seasonal Naive variants
    elif model_name == "seasonal_naive_adaptive":
        return forecast_seasonal_naive_adaptive(history, max_horizon)

    # Robust Fast-Moving variants (Step 6)
    elif model_name == "rolling_median_3":
        return forecast_rolling_median(history, max_horizon, window=3)
    elif model_name == "rolling_median_6":
        return forecast_rolling_median(history, max_horizon, window=6)
    elif model_name == "trimmed_mean_3":
        return forecast_trimmed_mean(history, max_horizon, window=3)
    elif model_name == "trimmed_mean_6":
        return forecast_trimmed_mean(history, max_horizon, window=6)
    elif model_name == "winsorized_mean_3":
        return forecast_winsorized_mean(history, max_horizon, window=3)
    elif model_name == "winsorized_mean_6":
        return forecast_winsorized_mean(history, max_horizon, window=6)

    # Pattern Router variants
    elif model_name == "pattern_router":
        from app.forecasting.benchmark_v2.router import forecast_pattern_router
        forecasts, _ = forecast_pattern_router(history, max_horizon=max_horizon, objective="variant_a")
        return forecasts
    elif model_name == "pattern_router_b":
        from app.forecasting.benchmark_v2.router import forecast_pattern_router
        forecasts, _ = forecast_pattern_router(history, max_horizon=max_horizon, objective="variant_b")
        return forecasts
    elif model_name == "pattern_router_c":
        from app.forecasting.benchmark_v2.router import forecast_pattern_router
        forecasts, _ = forecast_pattern_router(history, max_horizon=max_horizon, objective="variant_c")
        return forecasts
    elif model_name == "pattern_router_d":
        from app.forecasting.benchmark_v2.router import forecast_pattern_router
        forecasts, _ = forecast_pattern_router(history, max_horizon=max_horizon, objective="variant_d")
        return forecasts
    elif model_name == "pattern_router_e":
        from app.forecasting.benchmark_v2.router import forecast_pattern_router
        forecasts, _ = forecast_pattern_router(history, max_horizon=max_horizon, objective="variant_e")
        return forecasts

    else:
        raise ValueError(f"Unknown model name: {model_name}")
