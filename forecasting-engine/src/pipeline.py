import pandas as pd

from src.sales_data import complete_product_series
from src.evaluation import run_walk_forward, pick_best_model, MODEL_FUNCS
from src.trend import detect_trend
from src.reorder import calculate_reorder_point
from src.dead_stock import months_since_last_sale, detect_dead_stock
from src.similar_products import historical_analogue_forecast

def forecast_product(
    product_df: pd.DataFrame,
    test_size: int = 6,
    season_length: int = 12,
    stock_on_hand: float = 0.0,
) -> dict:
    """
    Runs the full forecast + evaluation pipeline for a single product's
    monthly series. Returns a summary dict — one row of the insight table.
    """
    sales = product_df["total_quantity"].astype(float).reset_index(drop=True)

    min_required = test_size + season_length
    if len(sales) <= min_required:
        return {"status": "insufficient_history", "months_available": len(sales)}

    train = sales.iloc[:-test_size]
    test = sales.iloc[-test_size:]

    if train.sum() == 0 and test.sum() == 0:
        idle = months_since_last_sale(product_df)
        dead = detect_dead_stock(stock_on_hand, 0.0, idle)
        return {
            "status": "no_sales_activity",
            "months_available": len(sales),
            "next_month_forecast": 0.0,
            "dead_stock": dead["dead_stock"],
            "dead_stock_reason": dead["dead_stock_reason"],
            "suggested_discount_pct": dead["suggested_discount_pct"],
            "months_since_last_sale": idle,
            "stock_on_hand": stock_on_hand,
        }

    result = run_walk_forward(sales, test_size=test_size, season_length=season_length)
    evaluation_df = result["evaluation"]

    if evaluation_df.empty:
        return {
            "status": "all_models_failed",
            "months_available": len(sales),
            "next_month_forecast": round(float(sales.mean()), 1),
        }

    best, ranking_metric = pick_best_model(evaluation_df)
    if best is None:
        return {
            "status": "no_valid_metric",
            "months_available": len(sales),
            "next_month_forecast": round(float(sales.mean()), 1),
        }

    best_model_name = best["model"]
    try:
        final_forecast = MODEL_FUNCS[best_model_name](sales)
    except Exception:
        final_forecast = float(sales.mean())

    trend_info = detect_trend(sales)
    reorder_info = calculate_reorder_point(sales, lead_time_months=3, safety_stock_months=1.0)
    idle = months_since_last_sale(product_df)
    dead = detect_dead_stock(stock_on_hand, reorder_info["avg_monthly_demand"], idle)

    return {
        "status": "ok",
        "best_model": best_model_name,
        "ranked_by": ranking_metric,
        "MAE": round(float(best["MAE"]), 2),
        "WAPE": round(float(best["WAPE"]), 4),
        "MASE": round(float(best["MASE"]), 4) if pd.notna(best["MASE"]) else None,
        "confidence": (
            "trivial_zero" if test.sum() == 0 and train.sum() > 0
            else "low" if pd.notna(best["MASE"]) and best["MASE"] > 1.0
            else "normal"
        ),
        "next_month_forecast": round(float(final_forecast), 1),
        "months_available": len(sales),
        "trend": trend_info["trend"],
        "trend_pct_change": trend_info["trend_pct_change"],
        "reorder_point": reorder_info["reorder_point"],
        "avg_monthly_demand": reorder_info["avg_monthly_demand"],
        "dead_stock": dead["dead_stock"],
        "dead_stock_reason": dead["dead_stock_reason"],
        "suggested_discount_pct": dead["suggested_discount_pct"],
        "months_since_last_sale": idle,
        "stock_on_hand": stock_on_hand,
    }


def cold_start_fallback(product_id, monthly_df: pd.DataFrame, category_map: dict) -> dict:
    """Fallback for products with too little history — uses category peer average."""
    category = category_map.get(product_id)

    if category is None:
        return {
            "status": "cold_start_no_category", "confidence": "very_low",
            "next_month_forecast": 0.0, "trend": "unknown", "trend_pct_change": None,
            "reorder_point": 0.0, "avg_monthly_demand": 0.0,
        }

    peer_ids = [pid for pid, cat in category_map.items() if cat == category and pid != product_id]
    if not peer_ids:
        peer_ids = [pid for pid, cat in category_map.items() if cat == category]

    peer_sales = monthly_df[monthly_df["product_id"].isin(peer_ids)]

    if peer_sales.empty:
        return {
            "status": "cold_start_no_peers", "confidence": "very_low",
            "next_month_forecast": 0.0, "trend": "unknown", "trend_pct_change": None,
            "reorder_point": 0.0, "avg_monthly_demand": 0.0,
        }

    global_end_month = monthly_df["month"].max()
    peer_averages = []
    for _, group in peer_sales.groupby("product_id"):
        peer_df = complete_product_series(group.copy(), end_date=global_end_month)
        peer_averages.append(float(peer_df["total_quantity"].mean()))

    if not peer_averages:
        return {
            "status": "cold_start_no_peers", "confidence": "very_low",
            "next_month_forecast": 0.0, "trend": "unknown", "trend_pct_change": None,
            "reorder_point": 0.0, "avg_monthly_demand": 0.0,
        }

    avg_monthly = sum(peer_averages) / len(peer_averages)

    return {
        "status": "cold_start_category_average",
        "confidence": "very_low",
        "next_month_forecast": round(float(avg_monthly), 1),
        "trend": "unknown",
        "trend_pct_change": None,
        "reorder_point": round(float(avg_monthly) * 4, 1),
        "avg_monthly_demand": round(float(avg_monthly), 1),
    }


def forecast_all_products(
    monthly_df: pd.DataFrame,
    test_size: int = 6,
    season_length: int = 12,
    category_map: dict | None = None,
    stock_map: dict | None = None,
    similar_candidates: pd.DataFrame | None = None,
    product_ids: list[int] | None = None,
) -> pd.DataFrame:
    """Runs forecast_product for every product — this is the insight table."""
    rows = []
    total_products = monthly_df["product_id"].nunique()
    processed = 0
    stock_map = stock_map or {}
    global_end_month = monthly_df["month"].max()
    selected_product_ids = set(product_ids) if product_ids is not None else None

    for product_id, group in monthly_df.groupby("product_id"):
        if selected_product_ids is not None and int(product_id) not in selected_product_ids:
            continue
        processed += 1
        if processed % 200 == 0:
            print(f"Processed {processed}/{total_products} products...")

        product_df = complete_product_series(group.copy(), end_date=global_end_month)
        product_df["month"] = pd.to_datetime(product_df["month"])
        product_df = product_df.sort_values("month").reset_index(drop=True)

        stock_on_hand = stock_map.get(product_id, 0.0)

        summary = forecast_product(
            product_df, test_size=test_size, season_length=season_length,
            stock_on_hand=stock_on_hand,
        )

        if summary["status"] == "insufficient_history":
            # Prefer explicit Odoo-linked historical analogues.
            # Fall back to the existing category average only when no
            # sufficiently supported analogue is available.
            if similar_candidates is not None:
                analogue = historical_analogue_forecast(
                    product_id=product_id,
                    product_df=product_df,
                    monthly_df=monthly_df,
                    similarity_candidates=similar_candidates,
                )
                if analogue["status"] == "cold_start_historical_analogue":
                    summary.update(analogue)

            if summary["status"] == "insufficient_history" and category_map:
                fallback = cold_start_fallback(product_id, monthly_df, category_map)
                summary.update(fallback)

        summary["product_id"] = product_id
        product_name = group["product_name"].dropna()
        summary["product_name"] = product_name.iloc[0] if not product_name.empty else None

        rows.append(summary)

    return pd.DataFrame(rows)


def save_forecasts(results_df: pd.DataFrame, engine, table_name: str = "product_demand_forecast"):
    """Writes the forecast results table to the database."""
    results_df.to_sql(table_name, engine, if_exists="replace", index=False)
    print(f"Saved {len(results_df)} rows to '{table_name}'.")