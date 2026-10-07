"""
Pattern-Aware Forecasting Router for Benchmark V2.
Performs point-in-time safe model selection within pattern-specific candidate pools
using training-only internal backtests prioritizing the 3-month supplier lead time horizon.

Supports multiple benchmark selection objective variants:
- Variant A (Baseline): 20% h1 + 30% h2 + 50% h3 absolute error
- Variant B (Horizon-3 WAPE focused): Normalized WAPE with h3 lead-time prioritization
- Variant C (Combined normalized MAE + positive bias penalty): Accuracy penalized for over-forecasting
- Variant D (Pattern-specific tailored objectives): Pattern-customized loss functions with
  intermittent positive-bias penalty and dead-stock protection
"""

from typing import Any, Sequence
import numpy as np
import pandas as pd

from app.forecasting.benchmark_v2.classification import classify_demand_pattern
from app.forecasting.benchmark_v2.models import forecast_multistep

PATTERN_CANDIDATE_POOLS: dict[str, list[str]] = {
    "fast_moving": [
        "median_baseline",
        "seasonal_naive_adaptive",
        "moving_average_3",
        "moving_average_6",
        "ses_alpha_05",
    ],
    "falling": [
        "moving_average_3",
        "moving_average_6",
        "ses_alpha_05",
        "previous_month",
    ],
    "rising": [
        "ets_linear_trend",
        "ets_damped_nonseasonal",
        "previous_month",
        "moving_average_3",
    ],
    "stable/normal": [
        "previous_month",
        "ets_linear_trend",
        "moving_average_3",
        "median_baseline",
    ],
    "intermittent": [
        "median_baseline",
        "croston_tsb",
        "croston_sba",
        "previous_month",
        "ses_alpha_05",
    ],
    "dead_stock": [
        "zero_baseline",
        "median_baseline",
        "moving_average_3",
    ],
    "cold_start": [
        "median_baseline",
        "previous_month",
        "seasonal_naive_adaptive",
    ],
}

PATTERN_CANDIDATE_POOLS_VARIANT_E: dict[str, list[str]] = {
    **PATTERN_CANDIDATE_POOLS,
    "fast_moving": [
        "median_baseline",
        "moving_average_3",
        "moving_average_6",
        "rolling_median_3",
        "rolling_median_6",
        "trimmed_mean_3",
        "trimmed_mean_6",
        "winsorized_mean_3",
        "winsorized_mean_6",
        "seasonal_naive_adaptive",
        "ses_alpha_05",
    ],
}

DEFAULT_FALLBACK_POOL = ["median_baseline", "previous_month"]


def compute_fast_moving_diagnostics(history: pd.Series) -> dict[str, Any]:
    """
    Computes derived telemetry for fast-moving products strictly from historical data.
    Provides diagnostic transparency into recent averages, medians, max demand, and spike ratio.
    """
    values = history.astype(float).values
    n = len(values)
    if n == 0:
        return {}

    recent_3 = values[-3:] if n >= 3 else values
    recent_6 = values[-6:] if n >= 6 else values

    r_mean_3 = float(np.mean(recent_3)) if len(recent_3) > 0 else 0.0
    r_mean_6 = float(np.mean(recent_6)) if len(recent_6) > 0 else 0.0
    r_med_3 = float(np.median(recent_3)) if len(recent_3) > 0 else 0.0
    r_med_6 = float(np.median(recent_6)) if len(recent_6) > 0 else 0.0

    max_recent = float(np.max(recent_6)) if len(recent_6) > 0 else 0.0
    max_historical = float(np.max(values)) if n > 0 else 0.0

    # Safe spike ratio: maximum recent demand relative to recent median (+1 for zero safety)
    spike_ratio = float(max_recent / (r_med_6 + 1.0)) if max_recent >= 0 else 0.0

    return {
        "recent_mean_3": round(r_mean_3, 2),
        "recent_mean_6": round(r_mean_6, 2),
        "recent_median_3": round(r_med_3, 2),
        "recent_median_6": round(r_med_6, 2),
        "maximum_recent_demand": round(max_recent, 2),
        "maximum_historical_demand": round(max_historical, 2),
        "spike_ratio": round(spike_ratio, 2),
    }


def compute_intermittent_diagnostics(history: pd.Series) -> dict[str, Any]:
    """
    Computes derived telemetry for intermittent products strictly from historical data.
    Provides diagnostic transparency into intermittency statistics and recent activity.
    """
    values = history.astype(float).values
    n = len(values)
    if n == 0:
        return {}

    nonzero_idx = np.where(values > 0)[0]
    n_nonzero = len(nonzero_idx)
    nonzero_ratio = n_nonzero / n if n > 0 else 0.0

    nonzero_vals = values[nonzero_idx] if n_nonzero > 0 else np.array([0.0])
    avg_nonzero = float(np.mean(nonzero_vals)) if n_nonzero > 0 else 0.0
    last_nonzero = float(nonzero_vals[-1]) if n_nonzero > 0 else 0.0
    months_since_last = int(n - 1 - nonzero_idx[-1]) if n_nonzero > 0 else n

    mean_pos = float(np.mean(nonzero_vals)) if n_nonzero > 0 else 0.0
    std_pos = float(np.std(nonzero_vals)) if n_nonzero > 1 else 0.0
    cv2 = float((std_pos / mean_pos) ** 2) if mean_pos > 0 else 0.0
    adi = float(n / n_nonzero) if n_nonzero > 0 else float(n)

    recent_3m = float(np.sum(values[-3:])) if n >= 3 else float(np.sum(values))
    recent_6m = float(np.sum(values[-6:])) if n >= 6 else float(np.sum(values))

    return {
        "nonzero_ratio": round(nonzero_ratio, 4),
        "avg_nonzero_demand": round(avg_nonzero, 2),
        "last_nonzero_demand": round(last_nonzero, 2),
        "months_since_last_nonzero": months_since_last,
        "adi": round(adi, 2),
        "cv2": round(cv2, 4),
        "recent_3m_activity": round(recent_3m, 2),
        "recent_6m_activity": round(recent_6m, 2),
    }


def evaluate_fold_loss(
    preds: Sequence[float],
    actuals: Sequence[float],
    val_horizon: int,
    pattern: str,
    objective: str = "variant_a",
) -> float:
    """
    Computes fold loss for a candidate model under a specified internal selection objective.
    All objectives are deterministic and point-in-time safe.
    """
    act_len = len(actuals)
    if act_len == 0:
        return 0.0

    abs_errs = [abs(preds[h] - actuals[h]) for h in range(act_len)]
    signed_errs = [preds[h] - actuals[h] for h in range(act_len)]
    mean_abs_err = float(np.mean(abs_errs))
    pos_bias = max(0.0, float(np.mean(signed_errs)))

    # Objective A: Current Baseline (20% h1 + 30% h2 + 50% h3 absolute error)
    if objective == "variant_a":
        h_weights = [0.20, 0.30, 0.50]
        if act_len == val_horizon:
            return float(sum(w * e for w, e in zip(h_weights, abs_errs)))
        return mean_abs_err

    # Objective B: Horizon-3 WAPE Focused
    elif objective == "variant_b":
        denom = float(np.sum(actuals))
        if denom == 0.0:
            denom = 1.0
        fold_wape = float(np.sum(abs_errs)) / denom

        if act_len >= 3:
            h3_norm_err = abs_errs[2] / (float(actuals[2]) + 1.0)
            return 0.50 * fold_wape + 0.50 * h3_norm_err
        return fold_wape

    # Objective C: Combined Normalized MAE/WAPE + Positive Bias Penalty
    elif objective == "variant_c":
        scale = float(np.mean(actuals)) + 1.0
        norm_mae = mean_abs_err / scale
        norm_pos_bias = pos_bias / scale
        return norm_mae + 0.50 * norm_pos_bias

    # Objective D & E: Pattern-Specific Tailored Objectives
    elif objective in ["variant_d", "variant_e"]:
        if pattern == "intermittent":
            # Prioritize MAE and heavily penalize positive bias (over-forecasting zeros)
            scale = float(np.mean(actuals)) + 1.0
            return (mean_abs_err / scale) + 1.50 * (pos_bias / scale)

        elif pattern == "falling":
            # Prioritize h2/h3 to track downward deceleration; penalize positive bias
            if act_len >= 3:
                h_loss = 0.10 * abs_errs[0] + 0.40 * abs_errs[1] + 0.50 * abs_errs[2]
            else:
                h_loss = mean_abs_err
            return h_loss + 0.50 * pos_bias

        elif pattern == "rising":
            # Allow trend models to project growth; mild positive bias penalty
            if act_len >= 3:
                h_loss = 0.30 * abs_errs[0] + 0.30 * abs_errs[1] + 0.40 * abs_errs[2]
            else:
                h_loss = mean_abs_err
            return h_loss + 0.20 * pos_bias

        elif pattern == "fast_moving":
            # Prioritize WAPE across horizons 1-3 with heavy weight on horizon 3
            if act_len >= 3:
                return (
                    0.20 * (abs_errs[0] / (float(actuals[0]) + 1.0))
                    + 0.30 * (abs_errs[1] / (float(actuals[1]) + 1.0))
                    + 0.50 * (abs_errs[2] / (float(actuals[2]) + 1.0))
                )
            denom = float(np.sum(actuals)) + 1.0
            return float(np.sum(abs_errs)) / denom

        elif pattern == "dead_stock":
            # Extremely strong penalty on any positive forecast
            mean_pred = float(np.mean(preds[:act_len]))
            return mean_abs_err + 5.0 * mean_pred

        elif pattern == "stable/normal":
            # Balanced multi-horizon accuracy with moderate bias penalty
            return mean_abs_err + 0.25 * pos_bias

        elif pattern == "cold_start":
            # Robust conservative L1 loss
            return mean_abs_err

        else:
            return mean_abs_err

    else:
        raise ValueError(f"Unknown router selection objective: {objective}")


def select_model_via_internal_backtest(
    history: pd.Series,
    pattern: str,
    val_horizon: int = 3,
    min_internal_train: int = 3,
    num_internal_origins: int = 3,
    objective: str = "variant_a",
) -> tuple[str, dict[str, Any]]:
    """
    Selects the best model from the pattern-specific candidate pool using ONLY
    the historical observations available at the origin.

    Internal validation strategy:
    - Splits history into expanding internal training sets and validation windows of length val_horizon (3 months).
    - Up to num_internal_origins rolling internal cutoffs within history.
    - Evaluates each candidate model across horizons 1..val_horizon.
    - Computes fold loss according to the chosen objective variant.
    - Ties broken deterministically by candidate pool order.
    - If history is too short for internal backtesting (len < min_internal_train + val_horizon),
      falls back safely to the primary default candidate for the pattern.
    """
    if objective == "variant_e":
        pool = PATTERN_CANDIDATE_POOLS_VARIANT_E.get(pattern, DEFAULT_FALLBACK_POOL)
    else:
        pool = PATTERN_CANDIDATE_POOLS.get(pattern, DEFAULT_FALLBACK_POOL)

    n = len(history)

    intermittent_telemetry = (
        compute_intermittent_diagnostics(history) if pattern in ["intermittent", "dead_stock"] else {}
    )
    fast_moving_telemetry = (
        compute_fast_moving_diagnostics(history) if pattern == "fast_moving" else {}
    )

    # Check if history is sufficient for at least one internal validation fold
    min_required = min_internal_train + val_horizon
    if n < min_required:
        selected = pool[0]
        return selected, {
            "pattern": pattern,
            "candidate_pool": pool,
            "selected_model": selected,
            "internal_score": None,
            "val_horizon": val_horizon,
            "objective": objective,
            "num_folds_evaluated": 0,
            "fallback": True,
            "fallback_reason": f"Insufficient history ({n} < {min_required} months)",
            "candidate_scores": {cand: None for cand in pool},
            "intermittent_diagnostics": intermittent_telemetry,
            "fast_moving_diagnostics": fast_moving_telemetry,
        }

    # Determine internal origins: up to num_internal_origins rolling origins ending within history
    latest_origin = n - val_horizon
    origins = [latest_origin - i for i in range(num_internal_origins) if (latest_origin - i) >= min_internal_train]
    origins.reverse()  # chronological order

    if not origins:
        selected = pool[0]
        return selected, {
            "pattern": pattern,
            "candidate_pool": pool,
            "selected_model": selected,
            "internal_score": None,
            "val_horizon": val_horizon,
            "objective": objective,
            "num_folds_evaluated": 0,
            "fallback": True,
            "fallback_reason": "No valid internal origin cutoffs found",
            "candidate_scores": {cand: None for cand in pool},
            "intermittent_diagnostics": intermittent_telemetry,
            "fast_moving_diagnostics": fast_moving_telemetry,
        }

    candidate_losses: dict[str, list[float]] = {cand: [] for cand in pool}
    values = history.astype(float).values

    for orig_idx in origins:
        train_sub = pd.Series(values[:orig_idx])
        actual_sub = values[orig_idx : orig_idx + val_horizon]

        for cand in pool:
            try:
                preds = forecast_multistep(cand, train_sub, max_horizon=val_horizon)
            except Exception:
                candidate_losses[cand].append(1e6)
                continue

            loss = evaluate_fold_loss(
                preds=preds,
                actuals=actual_sub,
                val_horizon=val_horizon,
                pattern=pattern,
                objective=objective,
            )
            candidate_losses[cand].append(loss)

    # Compute aggregate score for each candidate
    best_candidate = pool[0]
    best_score = float("inf")
    candidate_scores_summary: dict[str, float | None] = {}

    for cand in pool:
        scores = candidate_losses[cand]
        mean_score = float(np.mean(scores)) if scores else float("inf")
        candidate_scores_summary[cand] = round(mean_score, 4) if mean_score != float("inf") else None

        # Strict strictly-less-than for deterministic tie-breaking (earlier in pool wins ties)
        if mean_score < best_score:
            best_score = mean_score
            best_candidate = cand

    return best_candidate, {
        "pattern": pattern,
        "candidate_pool": pool,
        "selected_model": best_candidate,
        "internal_score": round(best_score, 4) if best_score != float("inf") else None,
        "val_horizon": val_horizon,
        "objective": objective,
        "num_folds_evaluated": len(origins),
        "fallback": False,
        "fallback_reason": None,
        "candidate_scores": candidate_scores_summary,
        "intermittent_diagnostics": intermittent_telemetry,
        "fast_moving_diagnostics": fast_moving_telemetry,
    }


def forecast_pattern_router(
    history: pd.Series,
    max_horizon: int = 5,
    val_horizon: int = 3,
    objective: str = "variant_a",
) -> tuple[list[float], dict[str, Any]]:
    """
    Pattern-aware forecasting router.
    1. Classifies demand pattern using ONLY data up to forecast origin (stock=0.0).
    2. Identifies pattern-specific candidate pool.
    3. Runs point-in-time safe internal backtest on training history prioritizing horizon 3.
    4. Selects best model deterministically under the specified objective.
    5. Generates multi-step forecasts for horizons 1..max_horizon.
    6. Returns forecasts along with complete telemetry.
    """
    if history.empty:
        raise ValueError("Cannot forecast from an empty series.")

    cls = classify_demand_pattern(history.astype(float), stock_on_hand=0.0)
    pattern = cls["pattern"]

    selected_model, telemetry = select_model_via_internal_backtest(
        history=history,
        pattern=pattern,
        val_horizon=val_horizon,
        objective=objective,
    )

    forecasts = forecast_multistep(selected_model, history, max_horizon=max_horizon)
    return forecasts, telemetry
