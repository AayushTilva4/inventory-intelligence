"""
Forecast Benchmark V2 package.
Provides isolated rolling-origin backtesting, multi-horizon evaluation (1-5 months),
demand-pattern classification, and reporting for Milano / Dazzle Fabrics.
"""

from .models import (
    BENCHMARK_MODELS,
    BASELINE_MODELS,
    INTERMITTENT_MODELS,
    TUNED_NON_INTERMITTENT_MODELS,
    ROBUST_FAST_MOVING_MODELS,
    ROUTER_MODELS,
    forecast_multistep,
)
from .router import (
    PATTERN_CANDIDATE_POOLS,
    select_model_via_internal_backtest,
    forecast_pattern_router,
)
from .metrics import calculate_metrics, calculate_mase_scale
from .classification import classify_demand_pattern
from .calibration import EmpiricalSafetyCalibrator, CalibratedForecast, calculate_fixed_buffer
from .shadow import ShadowPipeline, ShadowForecastComparison
from .db import init_benchmark_tables, get_poc_engine
from .runner import BenchmarkRunner

__all__ = [
    "BENCHMARK_MODELS",
    "BASELINE_MODELS",
    "INTERMITTENT_MODELS",
    "TUNED_NON_INTERMITTENT_MODELS",
    "ROBUST_FAST_MOVING_MODELS",
    "ROUTER_MODELS",
    "PATTERN_CANDIDATE_POOLS",
    "select_model_via_internal_backtest",
    "forecast_pattern_router",
    "forecast_multistep",
    "calculate_metrics",
    "calculate_mase_scale",
    "classify_demand_pattern",
    "EmpiricalSafetyCalibrator",
    "CalibratedForecast",
    "calculate_fixed_buffer",
    "ShadowPipeline",
    "ShadowForecastComparison",
    "init_benchmark_tables",
    "get_poc_engine",
    "BenchmarkRunner",
    "UniversalForecastingEngine",
    "HistorySufficiencyLayer",
    "UniversalForecastResult",
    "PortalPOService",
    "PortalPORecord",
]

from .universal_engine import (
    UniversalForecastingEngine,
    HistorySufficiencyLayer,
    UniversalForecastResult,
)
from .portal_po import (
    PortalPOService,
    PortalPORecord,
)
