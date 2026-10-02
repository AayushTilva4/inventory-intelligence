"""
Model wrappers for Forecast Benchmark V2.
Wraps the untouched existing V1 models to support multi-step horizons (1 to 5 months).
"""

import sys
from pathlib import Path
from typing import Sequence
import numpy as np
import pandas as pd

# Ensure AI-Demand-System is importable
EXISTING_ENGINE_ROOT = Path(r"E:\AI-Demand-System")
if str(EXISTING_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(EXISTING_ENGINE_ROOT))

# Import untouched existing V1 forecasting functions
from src.forecasting import (
    previous_month_forecast,
    moving_average_forecast,
    seasonal_naive_forecast,
    croston_forecast,
    exponential_smoothing_forecast,
)

from statsmodels.tsa.holtwinters import ExponentialSmoothing

BENCHMARK_MODELS = [
    "previous_month",
    "moving_average_3",
    "seasonal_naive",
    "croston",
    "exponential_smoothing",
]


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
        if target_lag_idx >= 0 and target_lag_idx < n:
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


def forecast_multistep(
    model_name: str,
    history: pd.Series,
    max_horizon: int = 5,
) -> list[float]:
    """
    Dispatches multi-step forecasting to the requested model.
    Returns a list of floats of length max_horizon for h=1..max_horizon.
    """
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
    else:
        raise ValueError(f"Unknown model name: {model_name}")
