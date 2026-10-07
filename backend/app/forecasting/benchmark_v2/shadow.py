"""
Benchmark V2 Non-Blocking Shadow Forecast Pipeline.

Calculates shadow demand forecasts and empirical safety stock targets
alongside existing production forecasts for comparison and risk auditing.

Guarantees:
- Strictly NON-BLOCKING: Read-only data ingestion, zero writes to Odoo or production models.
- Production isolation: Existing production forecast outputs and recommendations remain untouched.
- Clean structured output with diagnostic risk flags.
- Configurable risk thresholds.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence
import numpy as np
import pandas as pd

from .classification import classify_demand_pattern
from .models import forecast_multistep
from .calibration import EmpiricalSafetyCalibrator, CalibratedForecast, calculate_fixed_buffer
from .metrics import calculate_mase_scale


@dataclass(frozen=True)
class ShadowForecastComparison:
    """Structured shadow forecast comparison and diagnostic record."""
    product_id: int
    product_name: str
    pattern: str
    forecast_model: str
    forecast: float
    forecast_horizon: int
    safety_buffer: float
    service_level_target: float
    target_stock: float
    production_forecast: float | None
    forecast_delta: float | None
    production_target_if_available: float | None
    target_delta: float | None
    service_level_policy: str
    # Diagnostic flags
    large_forecast_change: bool
    large_buffer: bool
    zero_forecast: bool
    dead_stock: bool
    intermittent: bool
    potential_understock_risk: bool
    potential_overstock_risk: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ShadowPipeline:
    """
    Non-blocking shadow forecasting runner.
    """

    def __init__(
        self,
        calibrator: EmpiricalSafetyCalibrator | None = None,
        default_service_level: float = 0.80,
        horizon: int = 3,
        large_change_threshold_pct: float = 0.50,
        understock_risk_delta: float = 10.0,
        overstock_risk_delta: float = 20.0,
    ):
        self.calibrator = calibrator or EmpiricalSafetyCalibrator()
        self.default_service_level = float(default_service_level)
        self.horizon = int(horizon)
        self.large_change_threshold_pct = float(large_change_threshold_pct)
        self.understock_risk_delta = float(understock_risk_delta)
        self.overstock_risk_delta = float(overstock_risk_delta)

    def evaluate_product(
        self,
        product_id: int,
        product_name: str,
        sales_series: Sequence[float] | pd.Series,
        stock_on_hand: float = 0.0,
        production_forecast: float | None = None,
        production_target: float | None = None,
        service_level: float | None = None,
    ) -> ShadowForecastComparison:
        """
        Calculates shadow forecast, empirical buffer, and diagnostic flags for a single product.
        """
        pid = int(product_id)
        pname = str(product_name)
        sl = float(service_level if service_level is not None else self.default_service_level)
        s_series = pd.Series(sales_series, dtype=float).reset_index(drop=True)

        # 1. Pattern classification (point-in-time on available sales_series)
        cls = classify_demand_pattern(s_series, stock_on_hand=stock_on_hand)
        pattern = cls["pattern"]

        # 2. Central forecast model selection:
        # Default development champion: trimmed_mean_3
        # Special case: dead stock strictly yields 0.0
        if pattern == "dead_stock":
            model_name = "trimmed_mean_3"
            central_fc = 0.0
            policy = "dead_stock_zero"
        else:
            model_name = "trimmed_mean_3"
            preds = forecast_multistep(model_name, s_series, max_horizon=self.horizon)
            central_fc = float(preds[self.horizon - 1]) if len(preds) >= self.horizon else 0.0
            policy = f"trimmed_mean_3_sl_{int(sl*100)}"

        central_fc = max(0.0, round(central_fc, 4))

        # 3. MASE scale for buffer sizing
        scale = calculate_mase_scale(s_series, season_length=12)
        if scale is None or scale <= 0.0:
            scale = max(1.0, central_fc)

        # 4. Empirical safety buffer
        calib_res = self.calibrator.calculate_safety_buffer(
            forecast=central_fc,
            horizon=self.horizon,
            pattern=pattern,
            model=model_name,
            service_level=sl,
            scale=scale,
        )
        safety_buffer = calib_res.safety_buffer
        target_stock = calib_res.target_stock

        # 5. Production comparisons
        prod_fc = float(production_forecast) if production_forecast is not None and not np.isnan(production_forecast) else None
        prod_tgt = float(production_target) if production_target is not None and not np.isnan(production_target) else None

        fc_delta = round(central_fc - prod_fc, 4) if prod_fc is not None else None
        tgt_delta = round(target_stock - prod_tgt, 4) if prod_tgt is not None else None

        # 6. Diagnostic flags
        is_dead = (pattern == "dead_stock")
        is_intermittent = (pattern == "intermittent")
        is_zero_fc = (central_fc <= 0.0)
        is_large_buf = (safety_buffer > central_fc and central_fc > 0.0)

        # Large forecast change flag: change relative to production forecast
        if prod_fc is not None and prod_fc > 0.0:
            rel_change = abs(central_fc - prod_fc) / prod_fc
            is_large_change = (rel_change >= self.large_change_threshold_pct)
        elif prod_fc is not None and prod_fc == 0.0 and central_fc > 0.0:
            is_large_change = True
        else:
            is_large_change = False

        # Potential understock / overstock risks vs production target
        if tgt_delta is not None:
            potential_understock = (tgt_delta < -self.understock_risk_delta)
            potential_overstock = (tgt_delta > self.overstock_risk_delta)
        else:
            potential_understock = False
            potential_overstock = False

        return ShadowForecastComparison(
            product_id=pid,
            product_name=pname,
            pattern=pattern,
            forecast_model=model_name,
            forecast=central_fc,
            forecast_horizon=self.horizon,
            safety_buffer=safety_buffer,
            service_level_target=sl,
            target_stock=target_stock,
            production_forecast=prod_fc,
            forecast_delta=fc_delta,
            production_target_if_available=prod_tgt,
            target_delta=tgt_delta,
            service_level_policy=policy,
            large_forecast_change=is_large_change,
            large_buffer=is_large_buf,
            zero_forecast=is_zero_fc,
            dead_stock=is_dead,
            intermittent=is_intermittent,
            potential_understock_risk=potential_understock,
            potential_overstock_risk=potential_overstock,
        )
