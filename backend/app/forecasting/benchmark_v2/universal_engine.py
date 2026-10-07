"""
Universal Forecasting Engine & Sufficiency Architecture for Step 12.

Hardening Principles:
1. Universal Coverage: Handles 100% of products in the Odoo catalog deterministically.
2. History Sufficiency Layer: Assesses series depth, quality, and eligibility before model execution.
3. Deterministic Fallback Hierarchy:
   - Level 0: trimmed_mean_3 (direct champion)
   - Level 1: recent_mean_fallback (for short history <3m or single-observation active items)
   - Level 2: analogue_or_category_fallback (for cold start / new active items)
   - Level 3: dead_stock_zero_clamp (for dormant items >= 6m with no recent demand)
   - Level 4: zero_demand_safe_floor (safe business floor, guaranteed non-negative)
4. Business Guardrails:
   - forecast >= 0, finite, no NaN, no Inf
   - dead stock hard clamp: forecast = 0, buffer = 0, target = 0, suggested_purchase = 0
   - phantom demand protection: if forecast == 0 or recent 3m == 0, safety buffer = 0
   - negative stock protection: effective_stock = max(0.0, current_stock)
   - stockout-suppressed demand awareness flag
5. Strictly Read-Only with respect to Odoo: Zero writes, zero schema modifications, zero Odoo POs.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence
import numpy as np
import pandas as pd

from .classification import classify_demand_pattern
from .models import forecast_multistep
from .calibration import EmpiricalSafetyCalibrator
from .metrics import calculate_mase_scale


# ==============================================================================
# CONFIGURATION & CONSTANTS
# ==============================================================================

CHAMPION_MODEL = "trimmed_mean_3"

SERVICE_LEVEL_POLICIES = {
    "fast_moving": 0.80,
    "stable/normal": 0.80,
    "rising": 0.75,
    "falling": 0.75,
    "intermittent": 0.75,
    "dead_stock": 0.00,
    "cold_start": 0.75,
    "low_demand": 0.75,
    "no_history": 0.00,
}


@dataclass(frozen=True)
class HistorySufficiency:
    """Explicit assessment of historical sales depth and quality."""
    history_length: int              # Total calendar months from first sale to global end (0 if no sales)
    positive_months: int            # Number of positive sales months recorded
    history_tier: str               # <3m_extremely_short, 3-5m_short, 6-11m_medium, 12-17m_moderate, 18-23m_sufficient, >=24m_long, no_history
    history_quality: str            # none, extremely_sparse, sparse, moderate, rich
    forecast_eligibility: str       # fully_eligible, short_history_eligible, extremely_short_fallback, dead_stock_clamped, cold_start_analogue, no_history_dormant
    fallback_reason: str | None     # Explanation if direct model cannot execute safely


@dataclass(frozen=True)
class UniversalForecastResult:
    """Guaranteed deterministic result for any product in the catalog."""
    product_id: int
    product_name: str
    category_id: str | None
    demand_pattern: str
    history_length: int
    history_quality: str
    forecast_eligibility: str
    selected_strategy: str
    fallback_used: bool
    fallback_level: int
    fallback_reason: str | None
    forecast_1m: float
    forecast_h3: float
    calibration_policy: str
    safety_buffer: float
    target_stock: float
    current_stock: float
    suggested_purchase: float
    confidence_status: str
    diagnostic_flags: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HistorySufficiencyLayer:
    """
    Assesses whether a product has sufficient, high-quality sales history
    to run multi-step time series models safely without distortion.
    """

    @staticmethod
    def assess(
        series: Sequence[float] | pd.Series,
        months_since_last_sale: int = 0,
        stock_on_hand: float = 0.0,
    ) -> HistorySufficiency:
        vals = np.array(series, dtype=float) if len(series) > 0 else np.array([], dtype=float)
        n_len = len(vals)
        pos_mask = vals > 0
        pos_count = int(pos_mask.sum())

        if n_len == 0 or pos_count == 0:
            h_tier = "no_history"
            h_quality = "none"
            if stock_on_hand > 0:
                elig = "dead_stock_clamped"
                reason = "No lifetime sales with on-hand inventory; treated as dormant inventory."
            else:
                elig = "no_history_dormant"
                reason = "Zero lifetime sales and zero inventory; safe zero floor applied."
            return HistorySufficiency(
                history_length=0,
                positive_months=0,
                history_tier=h_tier,
                history_quality=h_quality,
                forecast_eligibility=elig,
                fallback_reason=reason,
            )

        # First positive sale index defines true calendar history span
        first_pos_idx = int(np.where(pos_mask)[0][0])
        calendar_span = n_len - first_pos_idx

        # Assign History Tier
        if calendar_span < 3:
            h_tier = "<3m_extremely_short"
        elif calendar_span < 6:
            h_tier = "3-5m_short"
        elif calendar_span < 12:
            h_tier = "6-11m_medium"
        elif calendar_span < 18:
            h_tier = "12-17m_moderate"
        elif calendar_span < 24:
            h_tier = "18-23m_sufficient"
        else:
            h_tier = ">=24m_long"

        # Assign History Quality
        if pos_count == 1:
            h_quality = "extremely_sparse"
        elif pos_count <= 3:
            h_quality = "sparse"
        elif pos_count <= 6:
            h_quality = "moderate"
        else:
            h_quality = "rich"

        # Assign Eligibility
        if months_since_last_sale >= 6 and (stock_on_hand > 0 or calendar_span >= 12):
            elig = "dead_stock_clamped"
            reason = f"Dormant for {months_since_last_sale} months; hard-clamped to zero."
        elif calendar_span < 3:
            elig = "extremely_short_fallback"
            reason = f"History span ({calendar_span}m) is less than 3 months; trimmed_mean_3 requires fallback."
        elif calendar_span < 6:
            elig = "short_history_eligible"
            reason = None
        else:
            elig = "fully_eligible"
            reason = None

        return HistorySufficiency(
            history_length=calendar_span,
            positive_months=pos_count,
            history_tier=h_tier,
            history_quality=h_quality,
            forecast_eligibility=elig,
            fallback_reason=reason,
        )


class UniversalForecastingEngine:
    """
    Hardened, universal forecasting and inventory recommendation engine.
    Guarantees deterministic, safe, non-negative results for every product.
    """

    def __init__(
        self,
        calibrator: EmpiricalSafetyCalibrator | None = None,
        category_medians: Mapping[str, float] | None = None,
    ):
        self.calibrator = calibrator or EmpiricalSafetyCalibrator()
        self.category_medians = dict(category_medians or {})

    def forecast_product(
        self,
        product_id: int,
        series: Sequence[float] | pd.Series,
        current_stock: float = 0.0,
        product_name: str | None = None,
        category_id: str | None = None,
    ) -> UniversalForecastResult:
        """
        Executes hardened forecasting pipeline with universal fallback hierarchy.
        """
        pid = int(product_id)
        pname = str(product_name or f"Product {pid}")
        cat_id = str(category_id) if category_id else None
        stock_val = max(0.0, float(current_stock or 0.0))
        s_series = pd.to_numeric(pd.Series(series), errors="coerce").fillna(0.0).reset_index(drop=True)
        vals = s_series.values
        n_pts = len(vals)

        # 1. Preprocessing & Recency Metrics
        rec_1m = float(vals[-1]) if n_pts >= 1 else 0.0
        rec_3m = float(vals[-3:].sum()) if n_pts >= 3 else float(vals.sum()) if n_pts >= 1 else 0.0
        rec_6m = float(vals[-6:].sum()) if n_pts >= 6 else float(vals.sum()) if n_pts >= 1 else 0.0
        rec_12m = float(vals[-12:].sum()) if n_pts >= 12 else float(vals.sum()) if n_pts >= 1 else 0.0

        pos_indices = np.where(vals > 0)[0]
        if len(pos_indices) > 0:
            last_pos_idx = pos_indices[-1]
            months_since_last_sale = n_pts - 1 - last_pos_idx
        else:
            months_since_last_sale = 999

        # 2. Demand Pattern Classification with Hardened Invariants
        cls = classify_demand_pattern(s_series, stock_on_hand=stock_val)
        pattern = cls["pattern"]

        # Reactivation safeguard: If product has recent sales in last 2m, it cannot be dead_stock
        if pattern == "dead_stock" and months_since_last_sale < 3:
            pattern = "intermittent"

        # Sudden collapse safeguard: If fast_moving or stable has 0 sales in last 3 months, downgrade
        if pattern in ["fast_moving", "stable/normal"] and rec_3m == 0.0:
            pattern = "falling"

        # 3. History Sufficiency Assessment
        sufficiency = HistorySufficiencyLayer.assess(
            s_series,
            months_since_last_sale=months_since_last_sale,
            stock_on_hand=stock_val,
        )

        diagnostic_flags: list[str] = []

        # Stockout-suppressed demand check
        if stock_val == 0.0 and rec_3m == 0.0 and rec_12m > 0.0:
            diagnostic_flags.append("stockout_suppressed_demand_risk")

        # Reactivation candidate check
        if months_since_last_sale < 2 and n_pts >= 6:
            prior_vals = vals[:-1]
            zero_runs = []
            c_run = 0
            for v in prior_vals:
                if v == 0:
                    c_run += 1
                else:
                    if c_run > 0:
                        zero_runs.append(c_run)
                    c_run = 0
            if c_run > 0:
                zero_runs.append(c_run)
            if any(r >= 4 for r in zero_runs):
                diagnostic_flags.append("recent_reactivation_candidate")

        # 4. Universal Fallback Hierarchy Execution
        selected_strategy = CHAMPION_MODEL
        fallback_used = False
        fallback_level = 0
        fallback_reason: str | None = None

        fc_1m: float = 0.0
        fc_h3: float = 0.0

        # LEVEL 3: Dead-Stock Hard Clamp (Dormant items)
        if pattern == "dead_stock" or sufficiency.forecast_eligibility == "dead_stock_clamped":
            selected_strategy = "dead_stock_zero_clamp"
            fallback_used = True
            fallback_level = 3
            fallback_reason = "Dead stock (no demand >= 6m with stock or prolonged dormancy); clamped to zero."
            fc_1m = 0.0
            fc_h3 = 0.0

        # LEVEL 4: No History Safe Floor (Zero lifetime sales & zero stock)
        elif sufficiency.history_tier == "no_history" or n_pts == 0 or sufficiency.positive_months == 0:
            # Check if category analogue fallback is available for active category
            cat_median = self.category_medians.get(cat_id, 0.0) if cat_id else 0.0
            if cat_median > 0.0 and pattern == "cold_start":
                selected_strategy = "category_analogue_fallback"
                fallback_used = True
                fallback_level = 2
                fallback_reason = f"No sales history; initialized with 50% category median ({cat_median:.2f})."
                fc_1m = max(0.0, round(float(cat_median * 0.50), 2))
                fc_h3 = fc_1m
            else:
                selected_strategy = "zero_demand_safe_floor"
                fallback_used = True
                fallback_level = 4
                fallback_reason = "No historical sales or analogue baseline available; zero floor applied."
                fc_1m = 0.0
                fc_h3 = 0.0

        # LEVEL 1: Extremely Short History (<3 months) or Single Observation
        elif sufficiency.history_length < 3 or n_pts < 3:
            selected_strategy = "recent_mean_fallback"
            fallback_used = True
            fallback_level = 1
            avail_pos = vals[vals > 0]
            val_mean = float(np.mean(avail_pos)) if len(avail_pos) > 0 else 0.0

            if sufficiency.positive_months == 1:
                # Single observation handling:
                if months_since_last_sale >= 1:
                    # Isolated past observation followed by zero; do not extrapolate into recurring demand
                    selected_strategy = "dead_stock_zero_clamp"
                    fallback_level = 3
                    fallback_reason = "Single past observation with subsequent zero sales; clamped to zero."
                    fc_1m = 0.0
                    fc_h3 = 0.0
                else:
                    # Current month single observation: apply 50% conservative damping and flag for review
                    fallback_reason = "Single current observation; applying 50% damped baseline with diagnostic review."
                    diagnostic_flags.append("single_recent_sale_diagnostic")
                    fc_1m = max(0.0, round(val_mean * 0.50, 2))
                    fc_h3 = fc_1m
            else:
                # 2 positive observations in <3m history: apply 65% damping to avoid launch spike overforecast
                damp_ratio = 0.50 if sufficiency.history_length == 1 else 0.65
                fallback_reason = f"Short history ({sufficiency.history_length}m); using {int(damp_ratio*100)}% damped positive mean."
                fc_1m = max(0.0, round(val_mean * damp_ratio, 2))
                fc_h3 = fc_1m

        # LEVEL 0: Direct Champion Model (trimmed_mean_3)
        else:
            try:
                preds = forecast_multistep(CHAMPION_MODEL, s_series, max_horizon=3)
                raw_1m = float(preds[0]) if len(preds) >= 1 else 0.0
                raw_h3 = float(preds[2]) if len(preds) >= 3 else raw_1m

                if math.isnan(raw_1m) or math.isinf(raw_1m) or math.isnan(raw_h3) or math.isinf(raw_h3):
                    raise ValueError("Champion model generated non-finite forecast.")

                fc_1m = max(0.0, round(raw_1m, 2))
                fc_h3 = max(0.0, round(raw_h3, 2))
                selected_strategy = CHAMPION_MODEL
                fallback_used = False
                fallback_level = 0
                fallback_reason = None
            except Exception as e:
                # Validated Fallback on unexpected failure
                selected_strategy = "recent_mean_fallback"
                fallback_used = True
                fallback_level = 1
                fallback_reason = f"Champion model exception ({type(e).__name__}); fell back to recent mean."
                fc_1m = max(0.0, round(float(rec_3m / 3.0), 2))
                fc_h3 = fc_1m

        # 5. Business Guardrails & Safety Clamps
        # Guardrail A: Non-negativity and finiteness
        fc_1m = 0.0 if math.isnan(fc_1m) or math.isinf(fc_1m) else max(0.0, fc_1m)
        fc_h3 = 0.0 if math.isnan(fc_h3) or math.isinf(fc_h3) else max(0.0, fc_h3)

        # Guardrail B: Extreme Jump Clamp
        # If forecast > 5x historical max or > 10x recent run rate without rising trend, clamp to 3x run rate
        hist_max = float(vals.max()) if n_pts > 0 else 0.0
        run_rate = max(rec_3m / 3.0, 1.0)
        if pattern != "rising" and fc_h3 > 5.0 * run_rate and fc_h3 > 20.0:
            diagnostic_flags.append("extreme_jump_clamped")
            fc_h3 = round(min(fc_h3, 3.0 * run_rate), 2)
            fc_1m = round(min(fc_1m, 3.0 * run_rate), 2)

        # 6. Safety Buffer & Calibration Policy
        policy_sl = SERVICE_LEVEL_POLICIES.get(pattern, 0.75)

        if pattern == "dead_stock" or fc_h3 == 0.0 or rec_3m == 0.0:
            # Phantom Demand Protection: if forecast is 0.0 or recent 3m demand is 0, buffer is clamped to 0
            safety_buf = 0.0
            cal_policy_str = "clamped_0%_phantom_protection" if fc_h3 == 0.0 else "dead_stock_0%"
        else:
            scale = calculate_mase_scale(s_series, season_length=12) if n_pts >= 13 else None
            if scale is None or scale <= 0.0 or math.isnan(scale):
                scale = max(1.0, fc_h3)

            cal_res = self.calibrator.calculate_safety_buffer(
                forecast=fc_h3,
                horizon=3,
                pattern=pattern,
                model=CHAMPION_MODEL,
                service_level=policy_sl,
                scale=scale,
            )
            raw_buf = cal_res.safety_buffer
            raw_buf = 0.0 if math.isnan(raw_buf) or math.isinf(raw_buf) else max(0.0, raw_buf)
            # Cap safety buffer at 3x forecast to prevent explosive targets on volatile series
            safety_buf = max(0.0, round(min(raw_buf, 3.0 * fc_h3 + 5.0), 2))
            cal_policy_str = f"empirical_{int(policy_sl * 100)}%"

        # 7. Inventory Target & Suggested Purchase
        if pattern == "dead_stock" or (fc_h3 == 0.0 and safety_buf == 0.0):
            tgt_stock = 0.0
            suggested_buy = 0.0
        else:
            tgt_stock = max(0.0, round(fc_h3 + safety_buf, 2))
            suggested_buy = max(0.0, round(tgt_stock - stock_val, 2))

        # 8. Confidence Status
        if pattern == "dead_stock":
            confidence = "high_dead_stock_clamped"
        elif fallback_used and fallback_level >= 2:
            confidence = "low_fallback"
        elif pattern == "intermittent" and rec_3m == 0.0:
            confidence = "low_intermittent"
        elif sufficiency.history_quality in ["rich", "moderate"] and not fallback_used:
            confidence = "high_champion"
        else:
            confidence = "medium"

        # Final Invariant Sanity Assertions
        assert fc_1m >= 0.0, f"Invariant violation: fc_1m < 0 on product {pid}"
        assert fc_h3 >= 0.0, f"Invariant violation: fc_h3 < 0 on product {pid}"
        assert tgt_stock >= 0.0, f"Invariant violation: tgt_stock < 0 on product {pid}"
        assert suggested_buy >= 0.0, f"Invariant violation: suggested_buy < 0 on product {pid}"
        if pattern == "dead_stock":
            assert tgt_stock == 0.0, f"Invariant violation: dead_stock target > 0 on product {pid}"
            assert suggested_buy == 0.0, f"Invariant violation: dead_stock buy > 0 on product {pid}"

        return UniversalForecastResult(
            product_id=pid,
            product_name=pname,
            category_id=cat_id,
            demand_pattern=pattern,
            history_length=sufficiency.history_length,
            history_quality=sufficiency.history_quality,
            forecast_eligibility=sufficiency.forecast_eligibility,
            selected_strategy=selected_strategy,
            fallback_used=fallback_used,
            fallback_level=fallback_level,
            fallback_reason=fallback_reason,
            forecast_1m=fc_1m,
            forecast_h3=fc_h3,
            calibration_policy=cal_policy_str,
            safety_buffer=safety_buf,
            target_stock=tgt_stock,
            current_stock=stock_val,
            suggested_purchase=suggested_buy,
            confidence_status=confidence,
            diagnostic_flags=diagnostic_flags,
        )
