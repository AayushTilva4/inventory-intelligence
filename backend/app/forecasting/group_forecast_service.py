from typing import Any

import pandas as pd

from app.forecasting.engine_adapter import load_existing_engine
from app.odoo.group_demand_service import get_group_demand_history
from app.odoo.product_group_service import get_group_members


TEST_SIZE = 6
SEASON_LENGTH = 12
MINIMUM_HISTORY = 6


def _finite_number(value: Any, digits: int | None = None) -> float | None:
    if value is None or pd.isna(value):
        return None
    result = float(value)
    return round(result, digits) if digits is not None else result


def _get_next_months(start_month_str: str | None, count: int = 3) -> list[str]:
    if not start_month_str:
        return []
    parts = start_month_str.split("-")
    if len(parts) < 2:
        return []
    year = int(parts[0])
    month = int(parts[1])
    months = []
    for _ in range(count):
        month += 1
        if month > 12:
            month = 1
            year += 1
        months.append(f"{year:04d}-{month:02d}")
    return months


_group_forecast_cache: dict[int, dict[str, Any]] = {}


def get_group_forecast(product_id: int) -> dict[str, Any] | None:
    """Forecast total demand for the product's canonical main-product group."""
    if product_id in _group_forecast_cache:
        return _group_forecast_cache[product_id]

    demand = get_group_demand_history(product_id)
    if demand is None:
        return None

    group_history = demand["months"]
    from app.odoo.stockout_service import build_corrected_demand_series
    sales = build_corrected_demand_series(group_history)
    group_members = get_group_members(
        int(demand["main_product_template_id"])
    )

    result: dict[str, Any] = {
        "status": "insufficient_group_history",
        "forecast_scope": "canonical_main_product_group_total_demand",
        "main_product_template_id": demand["main_product_template_id"],
        "main_product_name": demand["main_product_name"],
        "group_size": len(
            {member["product_template_id"] for member in group_members}
        ),
        "months_available": len(sales),
        "history_start": group_history[0]["month"] if group_history else None,
        "history_end": group_history[-1]["month"] if group_history else None,
        "next_month_forecast": None,
        "forecast_3_months": [],
        "best_model": None,
        "confidence": None,
        "mae": None,
        "wape": None,
        "mase": None,
        "avg_monthly_demand": float(sales.mean()) if not sales.empty else 0.0,
        "group_history": group_history,
    }

    if len(sales) < MINIMUM_HISTORY:
        result["confidence"] = "low"
        result["confidence_reason"] = "insufficient_group_history"
        _group_forecast_cache[product_id] = result
        return result

    load_existing_engine()
    # pyrefly: ignore [missing-import]
    from src.evaluation import pick_best_model, run_walk_forward
    from app.forecasting.benchmark_v2.models import forecast_multistep

    n = len(sales)
    if n >= 12:
        eval_test_size = TEST_SIZE
        eval_season_length = SEASON_LENGTH
    else:
        eval_test_size = min(3, max(1, n // 2))
        eval_season_length = 1

    evaluation = run_walk_forward(
        sales,
        test_size=eval_test_size,
        season_length=eval_season_length,
    )
    evaluation_df = evaluation["evaluation"]

    future_months = _get_next_months(
        group_history[-1]["month"] if group_history else None,
        5,
    )

    if evaluation_df.empty:
        mean_val = round(float(sales.mean()), 1)
        result["status"] = "all_models_failed"
        result["confidence"] = "low"
        result["confidence_reason"] = "all_models_failed"
        result["next_month_forecast"] = mean_val
        result["forecast_3_months"] = [
            {"month": m, "forecast": mean_val} for m in future_months[:3]
        ]
        result["forecast_multistep_values"] = [mean_val] * 5
        _group_forecast_cache[product_id] = result
        return result

    from app.forecasting.model_selection import select_best_model_operational

    is_dead = float(sales.sum()) == 0
    selection = select_best_model_operational(
        sales=sales,
        dead_stock=is_dead,
        max_origins=6,
        max_horizon=4,
    )
    best_model = selection["best_model"]

    try:
        multi_forecast = forecast_multistep(best_model, sales, max_horizon=5)
        next_month_forecast = float(multi_forecast[0])
    except Exception:
        multi_forecast = [float(sales.mean())] * 5
        next_month_forecast = float(sales.mean())

    from app.forecasting.confidence import (
        calculate_forecast_error_metrics,
        classify_forecast_confidence,
    )

    train = evaluation["train"]
    test = evaluation["test"]
    predictions = evaluation.get("predictions", {})
    if best_model in predictions:
        best_preds = predictions[best_model]
    else:
        best_preds = []
        hist = train.copy()
        for actual_val in test:
            try:
                pred = forecast_multistep(best_model, hist, max_horizon=1)[0]
            except Exception:
                pred = float(hist.mean()) if not hist.empty else 0.0
            best_preds.append(pred)
            hist = pd.concat([hist, pd.Series([actual_val])], ignore_index=True)

    metrics = calculate_forecast_error_metrics(
        actual=test,
        forecast=best_preds,
        train=train,
        season_length=eval_season_length,
    )

    wape_val = metrics["wape"]
    mase_val = metrics["mase"]

    confidence, confidence_reason = classify_forecast_confidence(
        wape=wape_val,
        mase=mase_val,
        observation_count=metrics["observation_count"],
        actual_sum=metrics["actual_sum"],
        forecast_sum=metrics["forecast_sum"],
        is_sparse=(n < 12),
        dead_stock=is_dead,
    )

    forecast_3_months = [
        {"month": m, "forecast": round(float(fc), 1)}
        for m, fc in zip(future_months[:3], multi_forecast[:3])
    ]
    forecast_multistep_values = [
        round(float(fc), 2) for fc in multi_forecast
    ]

    result.update(
        {
            "status": "ok",
            "next_month_forecast": round(float(next_month_forecast), 1),
            "forecast_3_months": forecast_3_months,
            "forecast_multistep_values": forecast_multistep_values,
            "best_model": best_model,
            "confidence": confidence,
            "confidence_reason": confidence_reason,
            "mae": _finite_number(metrics.get("mae"), 2),
            "wape": _finite_number(wape_val, 4),
            "mase": _finite_number(mase_val, 4),
            "rmse": _finite_number(metrics.get("rmse"), 2),
            "bias": _finite_number(metrics.get("bias"), 2),
            "underforecast_rate": _finite_number(metrics.get("underforecast_rate"), 4),
            "overforecast_rate": _finite_number(metrics.get("overforecast_rate"), 4),
            "evaluation_observations": metrics.get("observation_count"),
        }
    )
    _group_forecast_cache[product_id] = result
    return result