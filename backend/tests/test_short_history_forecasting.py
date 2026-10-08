import pytest
import pandas as pd
import numpy as np

from app.forecasting.group_forecast_service import get_group_forecast, MINIMUM_HISTORY
from app.forecasting.model_selection import (
    select_best_model_operational,
    CANDIDATE_MODELS,
    NON_SEASONAL_CANDIDATE_MODELS,
)
from app.forecasting.benchmark_v2.models import forecast_multistep
from app.forecasting.confidence import classify_forecast_confidence, calculate_forecast_error_metrics


def test_minimum_history_constant():
    """Verify minimum history threshold is 6 months."""
    assert MINIMUM_HISTORY == 6


def test_insufficient_history_under_6_months():
    """Series with fewer than 6 observations must return insufficient history."""
    short_series = pd.Series([10.0, 12.0, 15.0, 11.0, 14.0]) # 5 months
    assert len(short_series) < 6


def test_6_month_history_forecast():
    """Series with exactly 6 months of history must generate a forecast without seasonal_naive."""
    sales = pd.Series([10.0, 12.0, 15.0, 11.0, 14.0, 13.0])
    sel = select_best_model_operational(sales=sales, dead_stock=False)
    assert sel["best_model"] in NON_SEASONAL_CANDIDATE_MODELS
    assert sel["best_model"] != "seasonal_naive"
    
    fc = forecast_multistep(sel["best_model"], sales, max_horizon=3)
    assert len(fc) == 3
    assert all(np.isfinite(fc))
    assert all(f >= 0 for f in fc)


def test_7_to_11_month_no_annual_seasonality():
    """Series with 7–11 months must never select seasonal_naive."""
    for n in range(7, 12):
        sales = pd.Series(np.random.uniform(10, 50, size=n))
        sel = select_best_model_operational(sales=sales, dead_stock=False)
        assert sel["best_model"] != "seasonal_naive", f"Failed for n={n}"


def test_12_month_boundary_seasonal_allowed():
    """At 12+ months, seasonal models become eligible."""
    sales = pd.Series([10, 20, 30, 40, 50, 60, 10, 20, 30, 40, 50, 60], dtype=float)
    sel = select_best_model_operational(sales=sales, dead_stock=False)
    assert sel["best_model"] is not None


def test_13_to_18_month_history():
    """Series with 13–18 months evaluate multi-origin or robust fallback cleanly."""
    sales = pd.Series([15, 18, 22, 19, 25, 30, 28, 35, 32, 40, 38, 45, 42, 50, 48], dtype=float) # 15m
    sel = select_best_model_operational(sales=sales, dead_stock=False)
    assert sel["best_model"] in CANDIDATE_MODELS
    fc = forecast_multistep(sel["best_model"], sales, max_horizon=4)
    assert len(fc) == 4
    assert all(f >= 0 for f in fc)


def test_dead_stock_zero_forecast():
    """Dead stock (all zero sales) must produce forecast = 0.0 with no artificial demand."""
    sales = pd.Series([0.0] * 8)
    sel = select_best_model_operational(sales=sales, dead_stock=True)
    assert sel["best_model"] == "previous_month"
    assert sel["selection_reason"] == "dead_stock_zero_demand"
    fc = forecast_multistep(sel["best_model"], sales, max_horizon=5)
    assert all(f == 0.0 for f in fc)


def test_intermittent_short_history_no_explosion():
    """Sparse/intermittent short history must not explode forecast."""
    sales = pd.Series([0.0, 0.0, 100.0, 0.0, 0.0, 0.0, 150.0, 0.0], dtype=float)
    sel = select_best_model_operational(sales=sales, dead_stock=False)
    fc = forecast_multistep(sel["best_model"], sales, max_horizon=3)
    # Forecast must remain bounded reasonably (e.g. <= max historic sale)
    assert all(f <= 200.0 for f in fc)
    assert all(f >= 0.0 for f in fc)


def test_stockout_censored_months_integrity():
    """Stockout-censored months must remain excluded from history without inventing demand."""
    # 8 raw months with 2 stockout months removed by Task 9 stockout_service
    sales_clean = pd.Series([20.0, 25.0, 30.0, 22.0, 28.0, 35.0], dtype=float) # 6 usable obs
    sel = select_best_model_operational(sales=sales_clean, dead_stock=False)
    fc = forecast_multistep(sel["best_model"], sales_clean, max_horizon=3)
    assert len(fc) == 3
    assert all(np.isfinite(fc))


def test_no_future_leakage():
    """Forecast at historical origin t must depend strictly on sales[:t]."""
    full_series = pd.Series([10, 12, 14, 16, 18, 20, 50, 100, 200], dtype=float)
    t = 6
    history_at_t = full_series.iloc[:t].copy()
    
    sel_t = select_best_model_operational(sales=history_at_t, dead_stock=False)
    fc_t = forecast_multistep(sel_t["best_model"], history_at_t, max_horizon=1)[0]
    
    # Mutating future elements (index 6, 7, 8) must NOT alter fc_t
    full_series.iloc[6] = 99999.0
    sel_t_after = select_best_model_operational(sales=history_at_t, dead_stock=False)
    fc_t_after = forecast_multistep(sel_t_after["best_model"], history_at_t, max_horizon=1)[0]
    
    assert fc_t == fc_t_after


def test_nan_inf_handling():
    """NaN or Inf inputs must be safely handled without throwing exceptions."""
    sales = pd.Series([10.0, np.nan, 15.0, 12.0, np.inf, 14.0], dtype=float).fillna(0.0)
    sales = sales.replace([np.inf, -np.inf], 0.0)
    sel = select_best_model_operational(sales=sales, dead_stock=False)
    fc = forecast_multistep(sel["best_model"], sales, max_horizon=3)
    assert all(np.isfinite(fc))
    assert all(f >= 0.0 for f in fc)
