"""
Benchmark V2 Empirical Forecast Calibration & Safety Stock Layer.

This module implements empirical forecast calibration and pattern-aware safety stock
estimation derived from out-of-sample historical forecast errors.

Guarantees:
- 100% point-in-time safe (calibrated strictly on historical evaluation errors).
- Non-negative safety buffers: buffer >= 0.0.
- Dead stock isolation: zero buffer when pattern == 'dead_stock' or forecast <= 0.0.
- Outlier safety cap: buffers are capped to avoid absurd inventory targets.
- Deterministic execution across all configurations.
- Development / Benchmark V2 only (production code remains isolated).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CalibratedForecast:
    """
    Shadow-safe output structure representing a calibrated demand forecast
    and its empirical safety stock target.
    """
    forecast: float
    forecast_horizon: int
    pattern: str
    model: str
    error_quantile: float
    safety_buffer: float
    target_stock: float
    service_level: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EmpiricalSafetyCalibrator:
    """
    Point-in-time empirical safety stock calibrator.

    Computes empirical error quantiles from historical out-of-sample evaluation
    shortfalls (actual - forecast) partitioned by:
      (model, demand_pattern, horizon)
    with fallbacks to (model, demand_pattern) and (model).
    """

    SUPPORTED_SERVICE_LEVELS = (0.75, 0.80, 0.85, 0.90, 0.95)

    def __init__(
        self,
        cap_factor: float = 3.0,
        min_cap_floor: float = 5.0,
        service_levels: Sequence[float] | None = None,
    ):
        """
        Args:
            cap_factor: Maximum multiple of max(forecast, scale) permitted as buffer.
            min_cap_floor: Absolute minimum cap ceiling to prevent zero-cap on small series.
            service_levels: Supported target cycle service levels.
        """
        self.cap_factor = float(cap_factor)
        self.min_cap_floor = float(min_cap_floor)
        self.service_levels = tuple(service_levels) if service_levels else self.SUPPORTED_SERVICE_LEVELS

        # Calibration lookup tables:
        # (model, pattern, horizon, service_level) -> normalized quantile
        self._q_table: dict[tuple[str, str, int, float], float] = {}
        # (model, pattern, service_level) -> normalized quantile
        self._q_fallback_pat: dict[tuple[str, str, float], float] = {}
        # (model, service_level) -> normalized quantile
        self._q_fallback_model: dict[tuple[str, float], float] = {}

        self._is_calibrated = False

    @property
    def is_calibrated(self) -> bool:
        return self._is_calibrated

    def fit(self, historical_evaluations: pd.DataFrame) -> EmpiricalSafetyCalibrator:
        """
        Fits empirical quantile tables using historical evaluation rows.

        Expected DataFrame columns:
          - 'model': str
          - 'as_of_origin_pattern' or 'pattern': str
          - 'horizon': int
          - 'actual': float
          - 'forecast': float
          - 'mase_scale' (optional): float
        """
        if historical_evaluations.empty:
            self._is_calibrated = False
            return self

        df = historical_evaluations.copy()
        pat_col = "as_of_origin_pattern" if "as_of_origin_pattern" in df.columns else "demand_pattern"
        if pat_col not in df.columns:
            pat_col = "pattern"

        # Shortfall: actual demand minus forecast (clipped at 0: only positive shortfall requires safety buffer)
        shortfall = np.maximum(0.0, df["actual"].values - df["forecast"].values)
        scales = df["mase_scale"].values if "mase_scale" in df.columns else np.ones(len(df))
        scales = np.maximum(np.nan_to_num(scales, nan=1.0), 1.0)
        norm_shortfall = shortfall / scales

        df["_norm_sf"] = norm_shortfall
        df["_pat"] = df[pat_col].astype(str)
        df["_hz"] = df["horizon"].astype(int)
        df["_m"] = df["model"].astype(str)

        # 1. Primary level: (model, pattern, horizon)
        self._q_table.clear()
        for (m, pat, h), grp in df.groupby(["_m", "_pat", "_hz"]):
            vals = grp["_norm_sf"].values
            for sl in self.service_levels:
                self._q_table[(m, pat, h, sl)] = float(np.percentile(vals, sl * 100.0))

        # 2. Secondary fallback: (model, pattern)
        self._q_fallback_pat.clear()
        for (m, pat), grp in df.groupby(["_m", "_pat"]):
            vals = grp["_norm_sf"].values
            for sl in self.service_levels:
                self._q_fallback_pat[(m, pat, sl)] = float(np.percentile(vals, sl * 100.0))

        # 3. Tertiary fallback: (model)
        self._q_fallback_model.clear()
        for m, grp in df.groupby("_m"):
            vals = grp["_norm_sf"].values
            for sl in self.service_levels:
                self._q_fallback_model[(m, sl)] = float(np.percentile(vals, sl * 100.0))

        self._is_calibrated = True
        return self

    def calculate_safety_buffer(
        self,
        forecast: float,
        horizon: int,
        pattern: str,
        model: str,
        service_level: float,
        scale: float | None = None,
    ) -> CalibratedForecast:
        """
        Calculates an empirical safety buffer and target inventory for a given forecast.

        Rules:
        - If pattern == 'dead_stock' or forecast <= 0.0: buffer = 0.0.
        - Non-negative: buffer is clamped to >= 0.0.
        - Outlier safe cap: buffer <= cap_factor * max(forecast, scale, min_cap_floor).
        """
        fc = max(0.0, float(forecast))
        h = int(horizon)
        pat = str(pattern)
        m = str(model)
        sl = float(service_level)
        s = max(1.0, float(scale)) if scale is not None and not np.isnan(scale) else max(1.0, fc)

        # Dead stock / zero forecast invariant
        if pat == "dead_stock" or fc <= 0.0:
            return CalibratedForecast(
                forecast=round(fc, 4),
                forecast_horizon=h,
                pattern=pat,
                model=m,
                error_quantile=0.0,
                safety_buffer=0.0,
                target_stock=round(fc, 4),
                service_level=round(sl, 4),
            )

        # Lookup empirical quantile
        q = self._lookup_quantile(m, pat, h, sl)

        # Unscaled raw buffer
        raw_buffer = q * s

        # Safe cap: avoid explosive buffers
        cap = self.cap_factor * max(fc, s, self.min_cap_floor)
        safety_buffer = float(np.clip(raw_buffer, 0.0, cap))

        target_stock = fc + safety_buffer

        return CalibratedForecast(
            forecast=round(fc, 4),
            forecast_horizon=h,
            pattern=pat,
            model=m,
            error_quantile=round(q, 4),
            safety_buffer=round(safety_buffer, 4),
            target_stock=round(target_stock, 4),
            service_level=round(sl, 4),
        )

    def _lookup_quantile(self, model: str, pattern: str, horizon: int, service_level: float) -> float:
        """Hierarchical quantile lookup with robust fallback."""
        if not self._is_calibrated:
            # Fallback when calibrator has not been fitted: conservative 10% default scale
            return 0.10

        # Try exact (model, pattern, horizon, service_level)
        key = (model, pattern, horizon, service_level)
        if key in self._q_table:
            return self._q_table[key]

        # Try (model, pattern, service_level)
        key_pat = (model, pattern, service_level)
        if key_pat in self._q_fallback_pat:
            return self._q_fallback_pat[key_pat]

        # Try (model, service_level)
        key_m = (model, service_level)
        if key_m in self._q_fallback_model:
            return self._q_fallback_model[key_m]

        # Final default fallback
        return 0.10


def calculate_fixed_buffer(forecast: float, multiplier: float = 0.10) -> float:
    """
    Calculates the legacy baseline fixed percentage safety buffer.
    """
    fc = max(0.0, float(forecast))
    return round(fc * multiplier, 4)
