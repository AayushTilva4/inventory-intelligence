from typing import Any

import pandas as pd

from app.forecasting.engine_adapter import load_existing_engine
from app.odoo.group_demand_service import get_group_demand_history
from app.odoo.product_group_service import get_group_members


TEST_SIZE = 6
SEASON_LENGTH = 12
MINIMUM_HISTORY = TEST_SIZE + SEASON_LENGTH + 1


def _finite_number(value: Any, digits: int | None = None) -> float | None:
    if value is None or pd.isna(value):
        return None
    result = float(value)
    return round(result, digits) if digits is not None else result


def get_group_forecast(product_id: int) -> dict[str, Any] | None:
    """Forecast total demand for the product's canonical main-product group."""
    demand = get_group_demand_history(product_id)
    if demand is None:
        return None

    group_history = demand["months"]
    sales = pd.Series(
        [month["actual"] for month in group_history],
        dtype=float,
    ).reset_index(drop=True)
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
        "best_model": None,
        "confidence": None,
        "mae": None,
        "wape": None,
        "mase": None,
        "avg_monthly_demand": float(sales.mean()) if not sales.empty else 0.0,
        "group_history": group_history,
    }

    if len(sales) < MINIMUM_HISTORY:
        return result

    load_existing_engine()
    from src.evaluation import MODEL_FUNCS, pick_best_model, run_walk_forward

    evaluation = run_walk_forward(
        sales,
        test_size=TEST_SIZE,
        season_length=SEASON_LENGTH,
    )
    evaluation_df = evaluation["evaluation"]

    if evaluation_df.empty:
        result["status"] = "all_models_failed"
        result["next_month_forecast"] = round(float(sales.mean()), 1)
        return result

    best, _ = pick_best_model(evaluation_df)
    if best is None:
        result["status"] = "no_valid_metric"
        result["next_month_forecast"] = round(float(sales.mean()), 1)
        return result

    best_model = str(best["model"])
    try:
        next_month_forecast = MODEL_FUNCS[best_model](sales)
    except Exception:
        next_month_forecast = float(sales.mean())

    train = evaluation["train"]
    test = evaluation["test"]
    mase = best["MASE"]
    confidence = (
        "trivial_zero" if test.sum() == 0 and train.sum() > 0
        else "low" if pd.notna(mase) and mase > 1.0
        else "normal"
    )

    result.update(
        {
            "status": "ok",
            "next_month_forecast": round(float(next_month_forecast), 1),
            "best_model": best_model,
            "confidence": confidence,
            "mae": _finite_number(best["MAE"], 2),
            "wape": _finite_number(best["WAPE"], 4),
            "mase": _finite_number(mase, 4),
        }
    )
    return result