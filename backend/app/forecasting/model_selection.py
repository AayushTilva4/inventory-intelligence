import math
from typing import Any, Sequence
import numpy as np
import pandas as pd

from app.forecasting.benchmark_v2.models import forecast_multistep


CANDIDATE_MODELS: list[str] = [
    "trimmed_mean_3",
    "winsorized_mean_3",
    "previous_month",
    "moving_average_3",
    "moving_average_6",
    "seasonal_naive",
    "croston",
    "ses",
    "median_baseline",
]

NON_SEASONAL_CANDIDATE_MODELS: list[str] = [
    m for m in CANDIDATE_MODELS if m != "seasonal_naive"
]

MIN_HISTORY_FOR_MULTI_ORIGIN = 14
MIN_TRAIN_LENGTH = 10
DEFAULT_MAX_ORIGINS = 6
DEFAULT_MAX_HORIZON = 4


def evaluate_candidate_models_multi_origin(
    sales: pd.Series,
    candidate_models: Sequence[str] | None = None,
    max_origins: int = DEFAULT_MAX_ORIGINS,
    max_horizon: int = DEFAULT_MAX_HORIZON,
) -> dict[str, dict[str, Any]]:
    """
    Evaluates candidate models across multiple rolling historical origins strictly point-in-time.
    For each origin, generates multi-step forecasts (h=1..max_horizon) and evaluates cumulative
    and step errors on operational replenishment horizons (H=3 and H=4).
    """
    if candidate_models is None:
        candidate_models = CANDIDATE_MODELS

    arr = sales.astype(float).to_numpy()
    n = len(arr)
    if n < (MIN_TRAIN_LENGTH + max_horizon):
        return {}

    possible_origins = n - max_horizon - MIN_TRAIN_LENGTH + 1
    num_origins = min(max_origins, max(1, possible_origins))
    origin_indices = [n - max_horizon - num_origins + 1 + i for i in range(num_origins)]

    model_evals: dict[str, list[dict[str, float]]] = {m: [] for m in candidate_models}

    for orig_idx in origin_indices:
        train_hist = pd.Series(arr[:orig_idx])
        actuals_h = arr[orig_idx : orig_idx + max_horizon]

        # Naive scale on train history for MASE
        train_diffs = np.abs(np.diff(arr[:orig_idx]))
        scale = float(np.mean(train_diffs)) if len(train_diffs) > 0 else 1.0
        if scale <= 1e-9:
            scale = 1.0

        for m in candidate_models:
            try:
                preds_h = np.array(
                    forecast_multistep(m, train_hist, max_horizon=max_horizon),
                    dtype=float,
                )
            except Exception:
                mean_v = float(train_hist.mean()) if not train_hist.empty else 0.0
                preds_h = np.array([mean_v] * max_horizon, dtype=float)

            # Filter non-finite predictions
            if not np.all(np.isfinite(preds_h)):
                mean_v = float(train_hist.mean()) if not train_hist.empty else 0.0
                preds_h = np.array([mean_v] * max_horizon, dtype=float)

            # H1 metrics (month 1)
            err_h1 = float(preds_h[0] - actuals_h[0])
            abs_err_h1 = abs(err_h1)
            act_h1 = float(actuals_h[0])

            # H3 cumulative metrics (months 1..3)
            cum_act_h3 = float(np.sum(actuals_h[:3]))
            cum_pred_h3 = float(np.sum(preds_h[:3]))
            cum_err_h3 = cum_pred_h3 - cum_act_h3
            cum_abs_err_h3 = abs(cum_err_h3)

            # H4 cumulative metrics (months 1..4)
            cum_act_h4 = float(np.sum(actuals_h[:4]))
            cum_pred_h4 = float(np.sum(preds_h[:4]))
            cum_err_h4 = cum_pred_h4 - cum_act_h4
            cum_abs_err_h4 = abs(cum_err_h4)

            model_evals[m].append(
                {
                    "act_h1": act_h1,
                    "abs_err_h1": abs_err_h1,
                    "err_h1": err_h1,
                    "cum_act_h3": cum_act_h3,
                    "cum_abs_err_h3": cum_abs_err_h3,
                    "cum_err_h3": cum_err_h3,
                    "cum_act_h4": cum_act_h4,
                    "cum_abs_err_h4": cum_abs_err_h4,
                    "cum_err_h4": cum_err_h4,
                    "mase_scale": scale,
                }
            )

    model_summary: dict[str, dict[str, Any]] = {}
    for m, ev_list in model_evals.items():
        if not ev_list:
            continue
        df_ev = pd.DataFrame(ev_list)

        sum_act_h1 = float(df_ev["act_h1"].sum())
        sum_abs_h1 = float(df_ev["abs_err_h1"].sum())
        wape_h1 = (sum_abs_h1 / sum_act_h1) if sum_act_h1 > 0 else (0.0 if sum_abs_h1 == 0 else 1.0)
        mae_h1 = float(df_ev["abs_err_h1"].mean())

        sum_act_h3 = float(df_ev["cum_act_h3"].sum())
        sum_abs_h3 = float(df_ev["cum_abs_err_h3"].sum())
        wape_h3 = (sum_abs_h3 / sum_act_h3) if sum_act_h3 > 0 else (0.0 if sum_abs_h3 == 0 else 1.0)
        mae_h3 = float(df_ev["cum_abs_err_h3"].mean())

        sum_act_h4 = float(df_ev["cum_act_h4"].sum())
        sum_abs_h4 = float(df_ev["cum_abs_err_h4"].sum())
        wape_h4 = (sum_abs_h4 / sum_act_h4) if sum_act_h4 > 0 else (0.0 if sum_abs_h4 == 0 else 1.0)
        mae_h4 = float(df_ev["cum_abs_err_h4"].mean())
        bias_h4 = float(df_ev["cum_err_h4"].mean())

        mase_scale_mean = float(df_ev["mase_scale"].mean())
        mase_h4 = (mae_h4 / 4.0) / mase_scale_mean if mase_scale_mean > 0 else 1.0
        mase_h3 = (mae_h3 / 3.0) / mase_scale_mean if mase_scale_mean > 0 else 1.0

        # Combined H3/H4 Operational Horizon Loss:
        # Lead Time = 3 months, Review Period = 1 month -> Total Horizon = 4 months
        combined_h3_h4_wape = 0.4 * wape_h3 + 0.6 * wape_h4

        model_summary[m] = {
            "model": m,
            "num_origins": len(df_ev),
            "h1_wape": wape_h1,
            "h1_mae": mae_h1,
            "h3_wape": wape_h3,
            "h3_mae": mae_h3,
            "h3_mase": mase_h3,
            "h4_wape": wape_h4,
            "h4_mae": mae_h4,
            "h4_mase": mase_h4,
            "bias_h4": bias_h4,
            "combined_score": combined_h3_h4_wape,
        }

    return model_summary


def select_best_model_operational(
    sales: pd.Series,
    candidate_models: Sequence[str] | None = None,
    dead_stock: bool = False,
    max_origins: int = DEFAULT_MAX_ORIGINS,
    max_horizon: int = DEFAULT_MAX_HORIZON,
) -> dict[str, Any]:
    """
    Selects the optimal forecasting model aligned with the 3–4 month operational replenishment horizon.
    Uses multi-origin rolling evaluation with deterministic tie-breaking.
    """
    if candidate_models is None:
        if len(sales) < 12:
            candidate_models = NON_SEASONAL_CANDIDATE_MODELS
        else:
            candidate_models = CANDIDATE_MODELS

    if dead_stock or (not sales.empty and float(sales.sum()) == 0):
        return {
            "best_model": "previous_month",
            "selection_reason": "dead_stock_zero_demand",
            "h1_wape": 0.0,
            "h3_wape": 0.0,
            "h4_wape": 0.0,
            "h4_mae": 0.0,
            "h4_mase": 0.0,
            "bias_h4": 0.0,
            "combined_score": 0.0,
            "num_origins": 0,
            "all_model_scores": {},
        }

    if len(sales) < MIN_HISTORY_FOR_MULTI_ORIGIN:
        # Short history fallback: robust baseline
        return {
            "best_model": "trimmed_mean_3",
            "selection_reason": "short_history_robust_default",
            "h1_wape": None,
            "h3_wape": None,
            "h4_wape": None,
            "h4_mae": None,
            "h4_mase": None,
            "bias_h4": None,
            "combined_score": None,
            "num_origins": 0,
            "all_model_scores": {},
        }

    summary = evaluate_candidate_models_multi_origin(
        sales=sales,
        candidate_models=candidate_models,
        max_origins=max_origins,
        max_horizon=max_horizon,
    )

    if not summary:
        return {
            "best_model": "trimmed_mean_3",
            "selection_reason": "evaluation_empty_robust_fallback",
            "h1_wape": None,
            "h3_wape": None,
            "h4_wape": None,
            "h4_mae": None,
            "h4_mase": None,
            "bias_h4": None,
            "combined_score": None,
            "num_origins": 0,
            "all_model_scores": {},
        }

    # Deterministic Selection:
    # 1. Primary: Minimum Combined H3/H4 WAPE (tolerance 0.005)
    # 2. Secondary: Minimum H4 MAE
    # 3. Tertiary: Candidate Model Priority Order (simpler model preferred)
    model_order = {m: i for i, m in enumerate(candidate_models or CANDIDATE_MODELS)}

    best_item = min(
        summary.values(),
        key=lambda x: (
            round(x["combined_score"], 3),
            round(x["h4_mae"], 2),
            model_order.get(x["model"], 99),
        ),
    )

    best_model = best_item["model"]
    return {
        "best_model": best_model,
        "selection_reason": f"min_combined_h3_h4_wape_{best_item['combined_score']:.4f}",
        "h1_wape": best_item["h1_wape"],
        "h3_wape": best_item["h3_wape"],
        "h4_wape": best_item["h4_wape"],
        "h4_mae": best_item["h4_mae"],
        "h4_mase": best_item["h4_mase"],
        "bias_h4": best_item["bias_h4"],
        "combined_score": best_item["combined_score"],
        "num_origins": best_item["num_origins"],
        "all_model_scores": summary,
    }
