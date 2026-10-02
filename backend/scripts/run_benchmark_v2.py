"""
Command-line interface to execute Forecast Benchmark V2.
Supports rolling-origin backtesting, multi-horizon evaluation (1-5 months),
and saves results directly to the POC PostgreSQL database.

Usage examples:
  # Run on the 10 POC products (default):
  python scripts/run_benchmark_v2.py --poc-only

  # Run on top 20 active products:
  python scripts/run_benchmark_v2.py --top-n 20

  # Run on specific product IDs:
  python scripts/run_benchmark_v2.py --product-ids 16697,16905,17402

  # Run with custom origins and horizons:
  python scripts/run_benchmark_v2.py --origins 8 --horizons 1,2,3,4,5 --export-csv data/benchmark_output
"""

import sys
import argparse
from pathlib import Path

# Setup paths
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.forecasting.benchmark_v2 import BenchmarkRunner, BENCHMARK_MODELS


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run Forecast Benchmark V2 (Rolling-origin backtesting, 1-5 month horizons)"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--poc-only",
        action="store_true",
        default=True,
        help="Benchmark on the 10 POC products (default).",
    )
    group.add_argument(
        "--product-ids",
        type=str,
        help="Comma-separated product IDs to evaluate (e.g. 16697,16905,604).",
    )
    group.add_argument(
        "--top-n",
        type=int,
        help="Benchmark on top N active products by sales volume (e.g. 20, 50).",
    )
    group.add_argument(
        "--all-products",
        action="store_true",
        help="Benchmark on all catalog products with sufficient history.",
    )

    parser.add_argument(
        "--origins",
        type=int,
        default=6,
        help="Number of rolling forecast origins to test (default: 6).",
    )
    parser.add_argument(
        "--horizons",
        type=str,
        default="1,2,3,4,5",
        help="Comma-separated forecast horizons in months (default: 1,2,3,4,5).",
    )
    parser.add_argument(
        "--models",
        type=str,
        default=",".join(BENCHMARK_MODELS),
        help=f"Comma-separated models to benchmark (default: {','.join(BENCHMARK_MODELS)}).",
    )
    parser.add_argument(
        "--run-name",
        type=str,
        default=None,
        help="Optional custom name for this benchmark run.",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Skip saving benchmark results to the POC PostgreSQL database.",
    )
    parser.add_argument(
        "--export-csv",
        type=str,
        default=None,
        help="Optional directory to export CSV files of metrics and predictions.",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    # Determine mode
    if args.product_ids:
        mode = "ids"
        pids = [int(p.strip()) for p in args.product_ids.split(",") if p.strip()]
        top_n = None
    elif args.top_n:
        mode = "top_n"
        pids = None
        top_n = args.top_n
    elif args.all_products:
        mode = "all"
        pids = None
        top_n = None
    else:
        mode = "poc"
        pids = None
        top_n = None

    horizons = [int(h.strip()) for h in args.horizons.split(",") if h.strip()]
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    runner = BenchmarkRunner(
        horizons=horizons,
        num_origins=args.origins,
        models=models,
    )

    results = runner.run_benchmark(
        mode=mode,
        product_ids=pids,
        top_n=top_n,
        run_name=args.run_name,
        save_db=not args.no_db,
    )

    # Export CSVs if requested
    if args.export_csv and results.get("status") != "failed":
        out_dir = Path(args.export_csv)
        out_dir.mkdir(parents=True, exist_ok=True)

        forecast_path = out_dir / "benchmark_forecasts.csv"
        metrics_path = out_dir / "benchmark_metrics.csv"

        results["forecast_df"].to_csv(forecast_path, index=False)
        results["metrics_df"].to_csv(metrics_path, index=False)
        print(f"\n[Export] CSV files exported to:\n  {forecast_path}\n  {metrics_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
