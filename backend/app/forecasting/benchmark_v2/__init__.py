"""
Forecast Benchmark V2 package.
Provides isolated rolling-origin backtesting, multi-horizon evaluation (1-5 months),
demand-pattern classification, and reporting for Milano / Dazzle Fabrics.
"""

from .models import BENCHMARK_MODELS, forecast_multistep
from .metrics import calculate_metrics, calculate_mase_scale
from .classification import classify_demand_pattern
from .db import init_benchmark_tables, get_poc_engine
from .runner import BenchmarkRunner

__all__ = [
    "BENCHMARK_MODELS",
    "forecast_multistep",
    "calculate_metrics",
    "calculate_mase_scale",
    "classify_demand_pattern",
    "init_benchmark_tables",
    "get_poc_engine",
    "BenchmarkRunner",
]
