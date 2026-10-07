"""
Benchmark Runner for Forecast Benchmark V2.
Performs rolling-origin backtesting across horizons 1 to 5 months,
evaluates all 5 models against actual demand, classifies demand patterns,
and stores comprehensive results in the POC PostgreSQL database.
"""

import sys
import time
import json
import uuid
import logging
from pathlib import Path
from typing import Sequence, Any, Optional

import numpy as np
import pandas as pd

from app.forecasting.engine_adapter import load_forecasting_inputs, load_existing_engine
from app.forecasting.benchmark_v2.models import BENCHMARK_MODELS, forecast_multistep
from app.forecasting.benchmark_v2.metrics import calculate_metrics, calculate_mase_scale
from app.forecasting.benchmark_v2.classification import classify_demand_pattern
from app.forecasting.benchmark_v2.db import (
    init_benchmark_tables,
    save_benchmark_run,
    save_benchmark_forecasts,
    save_benchmark_metrics,
)
from app.db.connection import get_poc_engine

logger = logging.getLogger("benchmark_v2")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


POC_10_PRODUCT_IDS = [
    16697,  # 413-11 (fast_moving)
    16905,  # 415-39 (rising_demand)
    17402,  # 419-33 (falling_demand)
    9220,   # 392-31 (low_demand)
    22596,  # Buckby Latte - AW (reorder_needed / cold_start)
    9436,   # Naples-03 (excess_stock)
    5448,   # 353-20 (intermittent)
    1047,   # 314-09 (dead_stock_candidate)
    22662,  # 433-47 (cold_start)
    604,    # 330-08 (normal_healthy)
]


class BenchmarkRunner:
    """
    Executes rolling-origin forecast benchmarks across multiple horizons (1-5 months).
    """

    def __init__(
        self,
        horizons: Sequence[int] = (1, 2, 3, 4, 5),
        num_origins: int = 6,
        models: Sequence[str] | None = None,
        min_train_months: int = 3,
        engine=None,
    ):
        self.horizons = sorted(list(horizons))
        self.max_horizon = max(self.horizons)
        self.num_origins = num_origins
        self.models = list(models) if models else BENCHMARK_MODELS
        self.min_train_months = min_train_months
        self.poc_engine = engine or get_poc_engine()

        # Ensure database tables exist
        init_benchmark_tables(self.poc_engine)

    def load_data(self) -> dict[str, Any]:
        """Fetch raw sales and inventory data from Odoo via the legacy adapter."""
        logger.info("Loading sales and inventory inputs from Odoo database...")
        load_existing_engine()
        inputs = load_forecasting_inputs()
        logger.info(
            f"Loaded {len(inputs['monthly_df']):,} monthly sales records across "
            f"{inputs['monthly_df']['product_id'].nunique():,} unique products."
        )
        return inputs

    def select_products(
        self,
        monthly_df: pd.DataFrame,
        mode: str = "poc",
        product_ids: Sequence[int] | None = None,
        top_n: int | None = None,
    ) -> list[int]:
        """
        Determines the list of product IDs to benchmark based on mode:
        - 'poc': 10 specific POC products
        - 'ids': custom list of product IDs
        - 'top_n': top N active products by total demand
        - 'all': all products with enough historical records
        """
        if mode == "poc":
            # Match available POC products in dataset
            available_pids = set(monthly_df["product_id"].unique())
            selected = [pid for pid in POC_10_PRODUCT_IDS if pid in available_pids]
            logger.info(f"Selected {len(selected)} POC products for benchmark: {selected}")
            return selected

        elif mode == "ids":
            if not product_ids:
                raise ValueError("product_ids list must be provided when mode='ids'")
            available_pids = set(monthly_df["product_id"].unique())
            selected = [int(pid) for pid in product_ids if int(pid) in available_pids]
            logger.info(f"Selected {len(selected)} user-specified products for benchmark: {selected}")
            return selected

        elif mode == "top_n":
            n = top_n or 20
            totals = monthly_df.groupby("product_id")["total_quantity"].sum().sort_values(ascending=False)
            selected = totals.head(n).index.tolist()
            logger.info(f"Selected top {len(selected)} active products by volume for benchmark.")
            return selected

        elif mode == "all":
            # Products with at least min_train_months + max_horizon months of history
            counts = monthly_df.groupby("product_id")["month"].count()
            selected = counts[counts >= (self.min_train_months + self.max_horizon)].index.tolist()
            logger.info(f"Selected all {len(selected)} eligible catalog products for benchmark.")
            return selected

        else:
            raise ValueError(f"Unknown product selection mode: {mode}")

    def determine_rolling_origins(self, monthly_df: pd.DataFrame) -> list[pd.Timestamp]:
        """
        Calculates the list of rolling forecast origins.
        The latest origin is (global_end_month - max_horizon months) so all horizons
        have observable actual ground-truth future demand.
        """
        global_end = pd.to_datetime(monthly_df["month"]).max()
        # Ensure month is at start of month
        global_end = pd.Timestamp(global_end.year, global_end.month, 1)

        latest_origin = global_end - pd.DateOffset(months=self.max_horizon)
        latest_origin = pd.Timestamp(latest_origin.year, latest_origin.month, 1)

        origins = [
            latest_origin - pd.DateOffset(months=i)
            for i in range(self.num_origins - 1, -1, -1)
        ]
        origins = [pd.Timestamp(dt.year, dt.month, 1) for dt in origins]

        logger.info(
            f"Determined {len(origins)} rolling forecast origins "
            f"(from {origins[0].strftime('%Y-%m')} to {origins[-1].strftime('%Y-%m')}). "
            f"Global data end: {global_end.strftime('%Y-%m')}."
        )
        return origins

    def run_benchmark(
        self,
        mode: str = "poc",
        product_ids: Sequence[int] | None = None,
        top_n: int | None = None,
        run_name: str | None = None,
        save_db: bool = True,
    ) -> dict[str, Any]:
        """
        Executes the full rolling-origin backtest.
        """
        run_start_time = time.perf_counter()
        run_id = f"bm_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        run_name = run_name or f"Benchmark V2.1 ({mode.upper()})"

        # 1. Data Loading
        t_load_start = time.perf_counter()
        inputs = self.load_data()
        monthly_df = inputs["monthly_df"]
        stock_map = inputs.get("stock_map", {})
        data_loading_seconds = time.perf_counter() - t_load_start

        from src.sales_data import complete_product_series

        selected_pids = self.select_products(monthly_df, mode=mode, product_ids=product_ids, top_n=top_n)
        origins = self.determine_rolling_origins(monthly_df)
        global_end = pd.to_datetime(monthly_df["month"]).max()

        logger.info("=" * 80)
        logger.info(f"STARTING BENCHMARK RUN: {run_name} (Run ID: {run_id})")
        logger.info(f"  Products: {len(selected_pids)}")
        logger.info(f"  Origins:  {len(origins)} {[dt.strftime('%Y-%m') for dt in origins]}")
        logger.info(f"  Horizons: {self.horizons} months")
        logger.info(f"  Models:   {self.models}")
        logger.info("=" * 80)

        t_forecast_start = time.perf_counter()
        forecast_rows: list[dict[str, Any]] = []
        train_histories: dict[tuple[int, pd.Timestamp], list[float]] = {}
        current_classification_map: dict[int, dict[str, Any]] = {}
        origin_classification_map: dict[tuple[int, pd.Timestamp], dict[str, Any]] = {}
        scale_stats = {"valid_origins": 0, "undefined_origins": 0}
        failures: list[dict[str, Any]] = []

        total_product_count = len(selected_pids)

        for p_idx, pid in enumerate(selected_pids, 1):
            p_group = monthly_df[monthly_df["product_id"] == pid].copy()
            if p_group.empty:
                failures.append({"product_id": pid, "reason": "No sales records found in Odoo"})
                continue

            product_name = p_group["product_name"].dropna().iloc[0] if not p_group["product_name"].dropna().empty else f"Product {pid}"
            stock_val = float(stock_map.get(pid, 0.0))

            # Build full contiguous monthly series
            full_series_df = complete_product_series(p_group, end_date=global_end)
            full_series_df["month"] = pd.to_datetime(full_series_df["month"])
            full_series_df = full_series_df.sort_values("month").reset_index(drop=True)

            first_active_month = p_group["month"].min()

            # Classify current product demand pattern using full series and latest stock
            current_cls = classify_demand_pattern(full_series_df["total_quantity"], stock_on_hand=stock_val)
            current_pattern = current_cls["pattern"]
            current_classification_map[pid] = current_cls

            logger.info(f"[{p_idx}/{total_product_count}] Product {pid} ('{product_name}') -> Current Pattern: {current_pattern}")

            # Iterate over rolling forecast origins
            for origin_dt in origins:
                # Historical data available STRICTLY before or on origin_dt
                hist_mask = full_series_df["month"] <= origin_dt
                train_slice = full_series_df[hist_mask]

                if first_active_month > origin_dt:
                    # Product was not yet created at this origin
                    failures.append({
                        "product_id": pid,
                        "origin": origin_dt.strftime("%Y-%m-%d"),
                        "reason": f"Not launched yet (first sale was {first_active_month.strftime('%Y-%m')})",
                    })
                    continue

                if len(train_slice) < self.min_train_months:
                    failures.append({
                        "product_id": pid,
                        "origin": origin_dt.strftime("%Y-%m-%d"),
                        "reason": f"Insufficient history at origin ({len(train_slice)} < {self.min_train_months} months)",
                    })
                    continue

                train_series = train_slice["total_quantity"].astype(float).reset_index(drop=True)
                train_histories[(pid, origin_dt)] = list(train_series.values)

                # AS-OF-ORIGIN CLASSIFICATION: Strictly data available up to origin_dt, stock=0 (no future lookahead)
                as_of_origin_cls = classify_demand_pattern(train_series, stock_on_hand=0.0)
                as_of_origin_pattern = as_of_origin_cls["pattern"]
                origin_classification_map[(pid, origin_dt)] = as_of_origin_cls

                # MASE SCALE: In-sample naive scale from training history only
                mase_scale = calculate_mase_scale(train_series, season_length=12)
                if mase_scale is not None and mase_scale > 0:
                    scale_stats["valid_origins"] += 1
                else:
                    scale_stats["undefined_origins"] += 1

                # Extract ground truth actuals for requested future horizons
                future_actuals: dict[int, tuple[pd.Timestamp, float]] = {}
                for h in self.horizons:
                    target_dt = origin_dt + pd.DateOffset(months=h)
                    target_dt = pd.Timestamp(target_dt.year, target_dt.month, 1)

                    match_row = full_series_df[full_series_df["month"] == target_dt]
                    if not match_row.empty:
                        act_val = float(match_row["total_quantity"].iloc[0])
                        future_actuals[h] = (target_dt, act_val)

                # Generate forecasts for all benchmark models
                for model_name in self.models:
                    router_telemetry = None
                    try:
                        if model_name.startswith("pattern_router"):
                            from app.forecasting.benchmark_v2.router import forecast_pattern_router
                            obj_map = {
                                "pattern_router": "variant_a",
                                "pattern_router_b": "variant_b",
                                "pattern_router_c": "variant_c",
                                "pattern_router_d": "variant_d",
                                "pattern_router_e": "variant_e",
                            }
                            obj = obj_map.get(model_name, "variant_a")
                            preds, router_telemetry = forecast_pattern_router(
                                train_series, max_horizon=self.max_horizon, objective=obj
                            )
                        else:
                            preds = forecast_multistep(model_name, train_series, max_horizon=self.max_horizon)
                    except Exception as exc:
                        failures.append({
                            "product_id": pid,
                            "origin": origin_dt.strftime("%Y-%m-%d"),
                            "model": model_name,
                            "reason": f"Model forecast error: {str(exc)}",
                        })
                        continue

                    # Record forecast vs actual for each horizon
                    for h in self.horizons:
                        if h not in future_actuals:
                            continue

                        target_dt, act_val = future_actuals[h]
                        pred_val = float(preds[h - 1]) if len(preds) >= h else 0.0
                        err = pred_val - act_val
                        abs_err = abs(err)
                        scaled_err = (abs_err / mase_scale) if (mase_scale is not None and mase_scale > 0) else None

                        forecast_rows.append({
                            "run_id": run_id,
                            "product_id": pid,
                            "product_name": product_name,
                            "demand_pattern": as_of_origin_pattern,
                            "as_of_origin_pattern": as_of_origin_pattern,
                            "current_pattern": current_pattern,
                            "origin_date": origin_dt.date(),
                            "target_date": target_dt.date(),
                            "horizon": int(h),
                            "model": model_name,
                            "actual": round(act_val, 2),
                            "forecast": round(pred_val, 2),
                            "error": round(err, 2),
                            "abs_error": round(abs_err, 2),
                            "sq_error": round(err ** 2, 2),
                            "mase_scale": round(mase_scale, 4) if mase_scale is not None else None,
                            "scaled_error": round(scaled_err, 4) if scaled_err is not None else None,
                            "router_pattern": router_telemetry.get("pattern") if router_telemetry else None,
                            "router_candidate_pool": ",".join(router_telemetry.get("candidate_pool", [])) if router_telemetry else None,
                            "router_selected_model": router_telemetry.get("selected_model") if router_telemetry else None,
                            "router_internal_score": router_telemetry.get("internal_score") if router_telemetry else None,
                            "router_val_horizon": router_telemetry.get("val_horizon") if router_telemetry else None,
                            "router_objective": router_telemetry.get("objective") if router_telemetry else None,
                            "router_candidate_scores": json.dumps(router_telemetry.get("candidate_scores")) if router_telemetry and router_telemetry.get("candidate_scores") else None,
                            "router_intermittent_diagnostics": json.dumps(router_telemetry.get("intermittent_diagnostics")) if router_telemetry and router_telemetry.get("intermittent_diagnostics") else None,
                            "router_fast_moving_diagnostics": json.dumps(router_telemetry.get("fast_moving_diagnostics")) if router_telemetry and router_telemetry.get("fast_moving_diagnostics") else None,
                        })

        forecasting_seconds = time.perf_counter() - t_forecast_start
        logger.info(
            f"Generated {len(forecast_rows):,} forecast evaluations across all origins and models in {forecasting_seconds:.2f}s."
        )
        logger.info(f"Recorded {len(failures)} skip/failure events.")

        if not forecast_rows:
            logger.error("No valid forecast evaluations produced!")
            return {"run_id": run_id, "status": "failed", "failures": failures}

        forecast_df = pd.DataFrame(forecast_rows)

        # -------------------------------------------------------------
        # Compute Metrics across Aggregation Levels
        # -------------------------------------------------------------
        t_metrics_start = time.perf_counter()
        logger.info("Computing benchmark metrics across all requested aggregation levels...")
        metric_rows = self._compute_all_metrics(run_id, forecast_df)
        metrics_df = pd.DataFrame(metric_rows)
        metrics_seconds = time.perf_counter() - t_metrics_start

        # Determine Best Overall Model (lowest pooled WAPE)
        model_scores = metrics_df[metrics_df["aggregation_level"] == "model"].copy()
        if not model_scores.empty and "wape" in model_scores.columns:
            valid_wapes = model_scores.dropna(subset=["wape"]).sort_values("wape")
            if not valid_wapes.empty:
                best_overall_row = valid_wapes.iloc[0]
            else:
                best_overall_row = model_scores.sort_values("mae").iloc[0]
            best_model_name = str(best_overall_row["model"])
        else:
            best_model_name = self.models[0]

        logger.info(f"BEST OVERALL MODEL: {best_model_name}")

        t_db_start = time.perf_counter()
        db_write_seconds = 0.0

        run_info = {
            "run_id": run_id,
            "run_name": run_name,
            "status": "completed",
            "num_products": len(selected_pids),
            "models": self.models,
            "horizons": self.horizons,
            "num_origins": len(origins),
            "total_evaluations": len(forecast_rows),
            "best_overall_model": best_model_name,
            "runtime_seconds": 0.0,
            "timings": {
                "data_loading_seconds": round(data_loading_seconds, 2),
                "forecasting_seconds": round(forecasting_seconds, 2),
                "metrics_seconds": round(metrics_seconds, 2),
                "db_write_seconds": 0.0,
                "total_runtime_seconds": 0.0,
            },
            "scale_stats": scale_stats,
            "config": {
                "mode": mode,
                "origins": [d.strftime("%Y-%m-%d") for d in origins],
                "horizons": self.horizons,
                "min_train_months": self.min_train_months,
                "product_ids": selected_pids,
            },
        }

        # Save to PostgreSQL
        if save_db:
            logger.info("Saving benchmark run, forecasts, and metrics to POC PostgreSQL database...")
            save_benchmark_run(run_info, engine=self.poc_engine)
            save_benchmark_forecasts(forecast_rows, engine=self.poc_engine)
            save_benchmark_metrics(metric_rows, engine=self.poc_engine)
            db_write_seconds = time.perf_counter() - t_db_start
            logger.info("Saved successfully to POC PostgreSQL tables.")

        total_runtime_seconds = time.perf_counter() - run_start_time
        run_info["runtime_seconds"] = round(total_runtime_seconds, 2)
        run_info["timings"]["db_write_seconds"] = round(db_write_seconds, 2)
        run_info["timings"]["total_runtime_seconds"] = round(total_runtime_seconds, 2)

        if save_db:
            # Update benchmark_runs with final end-to-end runtime
            save_benchmark_run(run_info, engine=self.poc_engine)

        # Print Summary
        self.print_summary(run_info, metrics_df, current_classification_map, origin_classification_map, forecast_df)

        return {
            "run_info": run_info,
            "forecast_df": forecast_df,
            "metrics_df": metrics_df,
            "current_classifications": current_classification_map,
            "origin_classifications": origin_classification_map,
            "failures": failures,
        }

    def _compute_all_metrics(
        self,
        run_id: str,
        forecast_df: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        """Computes metrics at: aggregate, model, horizon, pattern, and product levels."""
        metric_rows: list[dict[str, Any]] = []

        # 1. Model Level & Aggregate Level
        for model in self.models:
            sub = forecast_df[forecast_df["model"] == model]
            if sub.empty:
                continue

            m = calculate_metrics(
                actual=sub["actual"].values,
                predicted=sub["forecast"].values,
                scaled_errors=sub["scaled_error"].values,
            )

            # Macro WAPE by Product (unweighted average across products with actual > 0)
            p_wapes: list[float] = []
            for pid_val in sub["product_id"].unique():
                p_sub = sub[sub["product_id"] == pid_val]
                p_act_sum = float(p_sub["actual"].sum())
                if p_act_sum > 0:
                    p_wapes.append(float(p_sub["abs_error"].sum() / p_act_sum))
            macro_wape_product = round(float(np.mean(p_wapes)), 4) if p_wapes else None

            # Macro WAPE by Horizon (unweighted average across horizons with actual > 0)
            h_wapes: list[float] = []
            for h_val in self.horizons:
                h_sub = sub[sub["horizon"] == h_val]
                h_act_sum = float(h_sub["actual"].sum())
                if h_act_sum > 0:
                    h_wapes.append(float(h_sub["abs_error"].sum() / h_act_sum))
            macro_wape_horizon = round(float(np.mean(h_wapes)), 4) if h_wapes else None

            m_row = {
                "run_id": run_id,
                "aggregation_level": "model",
                "product_id": None,
                "product_name": None,
                "demand_pattern": None,
                "model": model,
                "horizon": None,
                "macro_wape_product": macro_wape_product,
                "macro_wape_horizon": macro_wape_horizon,
                **m,
            }
            metric_rows.append(m_row)

            # Also add duplicate as 'aggregate'
            agg_row = dict(m_row)
            agg_row["aggregation_level"] = "aggregate"
            metric_rows.append(agg_row)

        # 2. Horizon Level (for each model and horizon)
        for model in self.models:
            for h in self.horizons:
                sub = forecast_df[(forecast_df["model"] == model) & (forecast_df["horizon"] == h)]
                if sub.empty:
                    continue

                m = calculate_metrics(
                    actual=sub["actual"].values,
                    predicted=sub["forecast"].values,
                    scaled_errors=sub["scaled_error"].values,
                )
                metric_rows.append({
                    "run_id": run_id,
                    "aggregation_level": "horizon",
                    "product_id": None,
                    "product_name": None,
                    "demand_pattern": None,
                    "model": model,
                    "horizon": int(h),
                    "macro_wape_product": None,
                    "macro_wape_horizon": None,
                    **m,
                })

        # 3. Demand Pattern Level (for each as-of-origin pattern and model)
        patterns = forecast_df["as_of_origin_pattern"].unique()
        for pattern in patterns:
            for model in self.models:
                sub = forecast_df[(forecast_df["as_of_origin_pattern"] == pattern) & (forecast_df["model"] == model)]
                if sub.empty:
                    continue

                m = calculate_metrics(
                    actual=sub["actual"].values,
                    predicted=sub["forecast"].values,
                    scaled_errors=sub["scaled_error"].values,
                )
                metric_rows.append({
                    "run_id": run_id,
                    "aggregation_level": "pattern",
                    "product_id": None,
                    "product_name": None,
                    "demand_pattern": str(pattern),
                    "model": model,
                    "horizon": None,
                    "macro_wape_product": None,
                    "macro_wape_horizon": None,
                    **m,
                })

        # 4. Product Level (for each product and model)
        products = forecast_df[["product_id", "product_name", "current_pattern"]].drop_duplicates()
        for _, p_row in products.iterrows():
            pid = int(p_row["product_id"])
            pname = str(p_row["product_name"])
            curr_pat = str(p_row["current_pattern"])

            for model in self.models:
                sub = forecast_df[(forecast_df["product_id"] == pid) & (forecast_df["model"] == model)]
                if sub.empty:
                    continue

                m = calculate_metrics(
                    actual=sub["actual"].values,
                    predicted=sub["forecast"].values,
                    scaled_errors=sub["scaled_error"].values,
                )
                metric_rows.append({
                    "run_id": run_id,
                    "aggregation_level": "product",
                    "product_id": pid,
                    "product_name": pname,
                    "demand_pattern": curr_pat,
                    "model": model,
                    "horizon": None,
                    "macro_wape_product": None,
                    "macro_wape_horizon": None,
                    **m,
                })

        return metric_rows

    def print_summary(
        self,
        run_info: dict[str, Any],
        metrics_df: pd.DataFrame,
        current_classification_map: dict[int, dict[str, Any]],
        origin_classification_map: dict[tuple[int, pd.Timestamp], dict[str, Any]],
        forecast_df: pd.DataFrame,
    ) -> None:
        """Prints formatted benchmark results directly to console."""
        print("\n" + "=" * 96)
        print(f"FORECAST BENCHMARK V2.1 RESULTS: {run_info['run_name']}")
        print("=" * 96)
        print(f"Run ID:             {run_info['run_id']}")
        print(f"Products tested:    {run_info['num_products']}")
        print(f"Rolling origins:    {run_info['num_origins']}")
        print(f"Horizons evaluated: {run_info['horizons']} months")
        print(f"Total evaluations:  {run_info['total_evaluations']:,}")
        print(f"BEST OVERALL MODEL: {run_info['best_overall_model'].upper()}")
        print("-" * 96)
        t = run_info.get("timings", {})
        print(
            f"Runtime Breakdown: Total {run_info['runtime_seconds']:.2f}s "
            f"(Data Loading: {t.get('data_loading_seconds', 0):.2f}s | "
            f"Forecasting: {t.get('forecasting_seconds', 0):.2f}s | "
            f"Metrics: {t.get('metrics_seconds', 0):.2f}s | "
            f"DB Writes: {t.get('db_write_seconds', 0):.2f}s)"
        )
        print("-" * 96)

        # 1. Overall Model Comparison Table
        print("\n[1] OVERALL MODEL ACCURACY RANKING:")
        print("    - pooled WAPE: volume-weighted portfolio accuracy (sum(|y-y_hat|) / sum(y))")
        print("    - macro WAPE (prod): unweighted average of product WAPEs (equal product importance)")
        print("    - macro WAPE (horiz): unweighted average of horizon WAPEs (equal horizon importance)")
        print("    - MASE: Mean Absolute Scaled Error (scaled by in-sample origin training scale)")
        model_df = metrics_df[metrics_df["aggregation_level"] == "model"].copy()
        if not model_df.empty:
            cols = [
                "model",
                "mae",
                "wape",
                "macro_wape_product",
                "macro_wape_horizon",
                "mase",
                "rmse",
                "bias",
                "under_forecast_rate",
                "over_forecast_rate",
            ]
            disp_df = model_df[cols].rename(
                columns={
                    "wape": "pooled_wape",
                    "macro_wape_product": "macro_wape_prod",
                    "macro_wape_horizon": "macro_wape_horiz",
                }
            ).sort_values("pooled_wape").reset_index(drop=True)
            print(disp_df.to_string(index=False))

        # 2. Horizon-by-Horizon Degradation Table
        print("\n[2] ACCURACY BY FORECAST HORIZON (Degradation over 1 to 5 months):")
        horizon_df = metrics_df[metrics_df["aggregation_level"] == "horizon"].copy()
        if not horizon_df.empty:
            pivot_wape = horizon_df.pivot(index="model", columns="horizon", values="wape")
            print("Pooled WAPE by Horizon (lower is better):")
            print(pivot_wape.to_string())

            pivot_mase = horizon_df.pivot(index="model", columns="horizon", values="mase")
            print("\nMASE by Horizon (lower is better, < 1.0 beats naive):")
            print(pivot_mase.to_string())

            pivot_mae = horizon_df.pivot(index="model", columns="horizon", values="mae")
            print("\nMAE by Horizon:")
            print(pivot_mae.to_string())

        # 3. Demand Pattern Breakdown Table
        print("\n[3] MODEL PERFORMANCE BY AS-OF-ORIGIN DEMAND PATTERN:")
        pattern_df = metrics_df[metrics_df["aggregation_level"] == "pattern"].copy()
        if not pattern_df.empty:
            pivot_pat_wape = pattern_df.pivot(index="demand_pattern", columns="model", values="wape")
            print("Pooled WAPE by As-Of-Origin Demand Pattern:")
            print(pivot_pat_wape.to_string())

            pivot_pat_mase = pattern_df.pivot(index="demand_pattern", columns="model", values="mase")
            print("\nMASE by As-Of-Origin Demand Pattern:")
            print(pivot_pat_mase.to_string())

        # 4. Pattern Stability and Shifts
        print("\n[4] AS-OF-ORIGIN VS CURRENT DEMAND PATTERN COMPARISON:")
        shift_rows = []
        for pid, c_cls in current_classification_map.items():
            curr_pat = c_cls["pattern"]
            # Find origin patterns for this product
            origin_pats = sorted(
                list({cls["pattern"] for (p, _), cls in origin_classification_map.items() if p == pid})
            )
            shift_rows.append({
                "product_id": pid,
                "current_pattern": curr_pat,
                "as_of_origin_patterns": ", ".join(origin_pats) if origin_pats else "N/A",
                "patterns_differ": "YES (shifted)" if any(p != curr_pat for p in origin_pats) else "NO (stable)",
            })
        if shift_rows:
            print(pd.DataFrame(shift_rows).to_string(index=False))

        # 5. MASE & Correctness Diagnostics
        print("\n[5] CORRECTNESS DIAGNOSTICS:")
        valid_mase_rows = int(forecast_df["scaled_error"].notna().sum())
        undefined_mase_rows = int(forecast_df["scaled_error"].isna().sum())
        total_evals = len(forecast_df)
        pct_valid = (valid_mase_rows / total_evals * 100) if total_evals > 0 else 0.0

        print(f"  Total forecast evaluation rows:      {total_evals:,}")
        print(f"  Valid MASE scaled evaluations:       {valid_mase_rows:,} ({pct_valid:.1f}%)")
        print(f"  Undefined MASE evaluations (scale=0): {undefined_mase_rows:,} ({100 - pct_valid:.1f}%)")
        print(f"  Unique product-origin training pairs: {len(origin_classification_map)}")
        scale_stats = run_info.get("scale_stats", {})
        print(
            f"  Product-origin training scales:      "
            f"{scale_stats.get('valid_origins', 0)} valid nonzero, "
            f"{scale_stats.get('undefined_origins', 0)} zero/undefined"
        )
        pattern_diff_count = int((forecast_df["as_of_origin_pattern"] != forecast_df["current_pattern"]).sum())
        print(f"  Forecast rows where origin pattern differs from current: {pattern_diff_count:,} / {total_evals:,}")

        # 6. Pattern-Aware Forecasting Router Analytics (if evaluated)
        if "pattern_router" in forecast_df["model"].values:
            print("\n[6] PATTERN-AWARE FORECASTING ROUTER TELEMETRY & SELECTION ANALYTICS:")
            router_sub = forecast_df[forecast_df["model"] == "pattern_router"].drop_duplicates(
                subset=["product_id", "origin_date"]
            )
            total_sels = len(router_sub)
            print(f"  Total Origin Selection Events: {total_sels:,}")

            if "router_selected_model" in router_sub.columns and total_sels > 0:
                print("\n  Overall Candidate Model Selection Frequency:")
                counts = router_sub["router_selected_model"].value_counts()
                pcts = (counts / total_sels * 100).map("{:.1f}%".format)
                freq_df = pd.DataFrame({"Selections": counts, "Percentage": pcts})
                print(freq_df.to_string())

                print("\n  Model Selection Frequency by As-Of-Origin Demand Pattern:")
                ct = pd.crosstab(
                    router_sub["as_of_origin_pattern"],
                    router_sub["router_selected_model"],
                    margins=True,
                    margins_name="Total",
                )
                print(ct.to_string())

            # Horizon 3 performance comparison
            h3_df = metrics_df[(metrics_df["aggregation_level"] == "horizon") & (metrics_df["horizon"] == 3)]
            if not h3_df.empty:
                print("\n  Horizon 3 Specific Lead-Time Accuracy (Supplier Reorder Lead Time):")
                h3_disp = h3_df[["model", "mae", "wape", "mase", "rmse", "bias"]].sort_values("wape")
                print(h3_disp.to_string(index=False))

        print("\n" + "=" * 96 + "\n")

