import math
import numpy as np
import pandas as pd
import pytest

from app.odoo.stockout_service import (
    classify_group_monthly_stockouts,
    build_corrected_demand_series,
)


def test_genuine_zero_demand_remains_zero():
    """A month with zero sales and ample on-hand stock must remain NORMAL_ZERO_DEMAND."""
    months = [
        {"month": "2025-01", "actual": 100.0},
        {"month": "2025-02", "actual": 0.0},
        {"month": "2025-03", "actual": 120.0},
    ]
    # Mock stock moves: initial stock 500, no depleting moves
    df_moves = pd.DataFrame([
        {"date": pd.Timestamp("2024-12-01"), "quantity": 500.0, "delta": 500.0, "cum_stock": 500.0}
    ])
    classified = classify_group_monthly_stockouts(12345, months, df_moves=df_moves)
    assert len(classified) == 3
    assert classified[1]["classification"] == "NORMAL_ZERO_DEMAND"
    assert classified[1]["is_stockout"] is False
    assert "available_stock" in classified[1]["reason"]

    corrected = build_corrected_demand_series(classified)
    assert corrected.iloc[1] == 0.0


def test_confirmed_stockout_month_becomes_suppressed():
    """A month with zero sales and zero stock must be classified as STOCKOUT_SUPPRESSED and treated as missing (NaN)."""
    months = [
        {"month": "2025-01", "actual": 100.0},
        {"month": "2025-02", "actual": 0.0},
        {"month": "2025-03", "actual": 120.0},
    ]
    df_moves = pd.DataFrame([
        {"date": pd.Timestamp("2025-01-01"), "quantity": 100.0, "delta": 100.0, "cum_stock": 100.0},
        {"date": pd.Timestamp("2025-01-20"), "quantity": 100.0, "delta": -100.0, "cum_stock": 0.0},
        {"date": pd.Timestamp("2025-03-01"), "quantity": 150.0, "delta": 150.0, "cum_stock": 150.0},
    ])
    classified = classify_group_monthly_stockouts(12345, months, df_moves=df_moves)
    assert len(classified) == 3
    assert classified[1]["classification"] == "STOCKOUT_SUPPRESSED"
    assert classified[1]["is_stockout"] is True
    assert "depleted_stock" in classified[1]["reason"]

    from app.odoo.stockout_service import build_missing_demand_series
    nan_series = build_missing_demand_series(classified)
    assert pd.isna(nan_series.iloc[1])

    corrected = build_corrected_demand_series(classified)
    # Missing-aware clean series excludes NaN -> [100.0, 120.0]
    assert list(corrected) == [100.0, 120.0]


def test_unknown_month_does_not_become_stockout():
    """A month with no stock history must be UNKNOWN and treated by default as zero."""
    months = [
        {"month": "2024-01", "actual": 0.0},
        {"month": "2024-02", "actual": 50.0},
    ]
    df_moves = pd.DataFrame(columns=["date", "delta", "cum_stock"])
    classified = classify_group_monthly_stockouts(12345, months, df_moves=df_moves)
    assert classified[0]["classification"] == "UNKNOWN"
    assert classified[0]["is_stockout"] is False

    corrected = build_corrected_demand_series(classified)
    assert corrected.iloc[0] == 0.0


def test_intermittent_demand_remains_safe():
    """Intermittent product with sporadic sales but continuous stock must retain all zeros."""
    months = [
        {"month": "2025-01", "actual": 10.0},
        {"month": "2025-02", "actual": 0.0},
        {"month": "2025-03", "actual": 0.0},
        {"month": "2025-04", "actual": 15.0},
        {"month": "2025-05", "actual": 0.0},
    ]
    df_moves = pd.DataFrame([
        {"date": pd.Timestamp("2024-12-01"), "quantity": 100.0, "delta": 100.0, "cum_stock": 100.0}
    ])
    classified = classify_group_monthly_stockouts(12345, months, df_moves=df_moves)
    for m in [classified[1], classified[2], classified[4]]:
        assert m["classification"] == "NORMAL_ZERO_DEMAND"
        assert m["is_stockout"] is False

    corrected = build_corrected_demand_series(classified)
    assert list(corrected) == [10.0, 0.0, 0.0, 15.0, 0.0]


def test_dead_stock_remains_zero():
    """Dead stock with stock on hand but no customer interest must not be inflated."""
    months = [{"month": f"2025-{i:02d}", "actual": 0.0} for i in range(1, 13)]
    df_moves = pd.DataFrame([
        {"date": pd.Timestamp("2024-12-01"), "quantity": 250.0, "delta": 250.0, "cum_stock": 250.0}
    ])
    classified = classify_group_monthly_stockouts(12345, months, df_moves=df_moves)
    for m in classified:
        assert m["classification"] == "NORMAL_ZERO_DEMAND"
        assert m["is_stockout"] is False

    corrected = build_corrected_demand_series(classified)
    assert all(v == 0.0 for v in corrected)


def test_point_in_time_no_future_leakage():
    """Stockout classification and series reconstruction at origin t must not use future moves."""
    months = [
        {"month": "2025-01", "actual": 50.0},
        {"month": "2025-02", "actual": 0.0}, # Stockout
        {"month": "2025-03", "actual": 200.0}, # Huge replenishment and sale later
    ]
    df_moves = pd.DataFrame([
        {"date": pd.Timestamp("2025-01-01"), "quantity": 50.0, "delta": 50.0, "cum_stock": 50.0},
        {"date": pd.Timestamp("2025-01-25"), "quantity": 50.0, "delta": -50.0, "cum_stock": 0.0},
        {"date": pd.Timestamp("2025-03-01"), "quantity": 500.0, "delta": 500.0, "cum_stock": 500.0},
    ])
    classified = classify_group_monthly_stockouts(12345, months[:2], df_moves=df_moves)
    assert len(classified) == 2
    assert classified[1]["classification"] == "STOCKOUT_SUPPRESSED"

    corrected_at_t2 = build_corrected_demand_series(classified)
    # Excludes 2025-02 stockout -> [50.0]
    assert list(corrected_at_t2) == [50.0]


def test_deterministic_classification():
    """Classification is 100% deterministic across repeated calls."""
    months = [
        {"month": "2025-01", "actual": 80.0},
        {"month": "2025-02", "actual": 0.0},
        {"month": "2025-03", "actual": 90.0},
    ]
    df_moves = pd.DataFrame([
        {"date": pd.Timestamp("2025-01-01"), "quantity": 80.0, "delta": 80.0, "cum_stock": 80.0},
        {"date": pd.Timestamp("2025-01-20"), "quantity": 80.0, "delta": -80.0, "cum_stock": 0.0},
    ])
    res1 = classify_group_monthly_stockouts(999, months, df_moves=df_moves)
    res2 = classify_group_monthly_stockouts(999, months, df_moves=df_moves)
    assert res1 == res2


def test_413_11_case_reconstruction():
    """Group 413-11 case: sales drop to 0 while out of stock is marked as STOCKOUT_SUPPRESSED."""
    months = [
        {"month": "2024-10", "actual": 52.0},
        {"month": "2024-11", "actual": 48.0},
        {"month": "2024-12", "actual": 0.0},
        {"month": "2025-01", "actual": 261.0},
    ]
    df_moves = pd.DataFrame([
        {"date": pd.Timestamp("2024-10-15"), "quantity": 100.0, "delta": 100.0, "cum_stock": 100.0},
        {"date": pd.Timestamp("2024-11-28"), "quantity": 97.0, "delta": -97.0, "cum_stock": 3.0}, # Stock depleted to 3.0
        {"date": pd.Timestamp("2025-01-05"), "quantity": 500.0, "delta": 500.0, "cum_stock": 503.0},
    ])
    classified = classify_group_monthly_stockouts(16742, months, df_moves=df_moves)
    assert classified[2]["classification"] == "STOCKOUT_SUPPRESSED"
    assert classified[2]["is_stockout"] is True

    from app.odoo.stockout_service import build_missing_demand_series
    nan_series = build_missing_demand_series(classified)
    assert pd.isna(nan_series.iloc[2])

    corrected = build_corrected_demand_series(classified)
    # Missing-aware series excludes stockout 2024-12 -> [52.0, 48.0, 261.0]
    assert list(corrected) == [52.0, 48.0, 261.0]


def test_nan_and_insufficient_history_handling():
    """Empty list, NaNs, and zero-length inputs are safely handled without exceptions."""
    assert build_corrected_demand_series([]).empty
    
    months_all_stockout = [
        {"month": "2025-01", "actual": 0.0, "is_stockout": True, "classification": "STOCKOUT_SUPPRESSED"},
        {"month": "2025-02", "actual": 0.0, "is_stockout": True, "classification": "STOCKOUT_SUPPRESSED"},
    ]
    corr = build_corrected_demand_series(months_all_stockout)
    assert len(corr) == 2
    assert all(v == 0.0 for v in corr)
