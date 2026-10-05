import numpy as np
import pandas as pd

from statsmodels.tsa.holtwinters import ExponentialSmoothing


def previous_month_forecast(series: pd.Series) -> float:
    """Predict the next month using the previous month's value."""
    if series.empty:
        raise ValueError("Cannot forecast from an empty series.")

    return float(series.iloc[-1])


def moving_average_forecast(
    series: pd.Series,
    window: int = 3,
) -> float:
    """Predict the next month using the average of the last N months."""
    if series.empty:
        raise ValueError("Cannot forecast from an empty series.")

    if window <= 0:
        raise ValueError("Window must be greater than 0.")

    if len(series) < window:
        return float(series.mean())

    return float(series.iloc[-window:].mean())


def seasonal_naive_forecast(
    series: pd.Series,
    season_length: int = 12,
) -> float:
    """
    Predict the next month using the value from the same period
    in the previous season.
    """
    if series.empty:
        raise ValueError("Cannot forecast from an empty series.")

    if season_length <= 0:
        raise ValueError("Season length must be greater than 0.")

    if len(series) < season_length:
        return float(series.iloc[-1])

    return float(series.iloc[-season_length])


def croston_forecast(series: pd.Series, alpha: float = 0.1) -> float:
    """
    Croston's method — designed for intermittent / lumpy demand.

    Separately smooths the demand size (only over periods where a sale
    actually happened) and the interval between sales, then combines
    them into a forecast rate. This tends to outperform standard
    smoothing methods on spiky, irregular series like individual
    fabric SKUs.
    """
    values = series.astype(float).to_numpy()

    if len(values) == 0:
        raise ValueError("Cannot forecast from an empty series.")

    if (values > 0).sum() == 0:
        # No sales at all in this history.
        return 0.0

    first_nonzero = int(np.argmax(values > 0))
    z = values[first_nonzero]   # smoothed demand size
    p = 1.0                     # smoothed inter-arrival interval
    q = 1                       # periods since last nonzero demand

    for t in range(first_nonzero + 1, len(values)):
        if values[t] > 0:
            z = alpha * values[t] + (1 - alpha) * z
            p = alpha * q + (1 - alpha) * p
            q = 1
        else:
            q += 1

    if p <= 0:
        return 0.0

    return float(z / p)


def exponential_smoothing_forecast(
    series: pd.Series,
    seasonal_periods: int | None = None,
) -> float:
    """
    Forecast the next month using Exponential Smoothing.

    If there is enough history and seasonal_periods is provided,
    a damped trend + seasonal model is used. Otherwise, a damped
    trend-only model is used.

    The trend is damped to prevent runaway extrapolation on short
    or spiky series, and the forecast is floored at zero since
    sales quantities cannot be negative.
    """
    if series.empty:
        raise ValueError("Cannot forecast from an empty series.")

    series = series.astype(float)

    if len(series) < 4:
        # Too little data to fit a trend model reliably.
        return float(series.mean())

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
    forecast = float(fitted_model.forecast(1).iloc[0])

    return max(forecast, 0.0)


def mae(actual, predicted) -> float:
    """Calculate Mean Absolute Error."""
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    if len(actual) != len(predicted):
        raise ValueError("Actual and predicted values must have the same length.")

    return float(np.mean(np.abs(actual - predicted)))


def wape(actual, predicted) -> float:
    """Calculate Weighted Absolute Percentage Error."""
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    if len(actual) != len(predicted):
        raise ValueError("Actual and predicted values must have the same length.")

    denominator = np.sum(np.abs(actual))

    if denominator == 0:
        return 0.0

    return float(
        np.sum(np.abs(actual - predicted)) / denominator
    )


def mase(actual, predicted, train_series, season_length: int = 1) -> float:
    """
    Calculate Mean Absolute Scaled Error.

    MASE compares the model's error against a naive same-period-ago
    baseline computed from the training series. MASE < 1 means the
    model beats that naive baseline; MASE > 1 means it's worse.

    Unlike WAPE, this is comparable across products regardless of
    how volatile each individual product's demand is, which makes
    it the right metric for picking the "best model" per product
    when scoring thousands of products at once.
    """
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    train = np.asarray(train_series, dtype=float)

    if len(actual) != len(predicted):
        raise ValueError("Actual and predicted values must have the same length.")

    if len(train) <= season_length:
        return float("nan")

    naive_errors = np.abs(train[season_length:] - train[:-season_length])
    scale = naive_errors.mean()

    if scale == 0:
        return float("nan")

    return float(np.mean(np.abs(actual - predicted)) / scale)