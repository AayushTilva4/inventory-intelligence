import pandas as pd

from src.forecasting import (
    previous_month_forecast,
    moving_average_forecast,
    seasonal_naive_forecast,
    croston_forecast,
    exponential_smoothing_forecast,
    mae,
    wape,
    mase,
)


MODEL_FUNCS = {
    "previous_month": lambda s: previous_month_forecast(s),
    "moving_average_3": lambda s: moving_average_forecast(s, window=3),
    "seasonal_naive": lambda s: seasonal_naive_forecast(s, season_length=12),
    "croston": lambda s: croston_forecast(s),
    "exponential_smoothing": lambda s: exponential_smoothing_forecast(
        s, seasonal_periods=12
    ),
}


def run_walk_forward(sales: pd.Series, test_size: int = 6, season_length: int = 12) -> dict:
    """
    Core walk-forward evaluation loop — the single source of truth for
    how every model is trained/tested. Used by both the full-catalog
    batch pipeline and single-product inspection, so there's only one
    place this logic can go wrong.
    """
    train = sales.iloc[:-test_size].copy()
    test = sales.iloc[-test_size:].copy()

    predictions = {name: [] for name in MODEL_FUNCS}
    history = train.copy()

    for actual_value in test:
        for model_name, forecast_fn in MODEL_FUNCS.items():
            try:
                predictions[model_name].append(forecast_fn(history))
            except Exception:
                predictions[model_name].append(float("nan"))

        history = pd.concat([history, pd.Series([actual_value])], ignore_index=True)

    evaluation_rows = []
    for model_name, preds in predictions.items():
        preds_arr = pd.Series(preds)
        if preds_arr.isna().any():
            continue
        evaluation_rows.append({
            "model": model_name,
            "MAE": mae(test, preds_arr),
            "WAPE": wape(test, preds_arr),
            "MASE": mase(test, preds_arr, train, season_length=season_length),
        })

    return {
        "train": train,
        "test": test,
        "predictions": predictions,
        "evaluation": pd.DataFrame(evaluation_rows),
    }


def pick_best_model(evaluation_df: pd.DataFrame):
    """Returns (best_row, ranking_metric_used) or (None, None) if nothing usable."""
    if evaluation_df.empty:
        return None, None

    valid = evaluation_df.dropna(subset=["MASE"])
    ranking_metric = "MASE"

    if valid.empty:
        valid = evaluation_df.dropna(subset=["MAE"])
        ranking_metric = "MAE"

    if valid.empty:
        return None, None

    best = valid.loc[valid[ranking_metric].idxmin()]
    return best, ranking_metric


def build_actual_vs_forecast_table(
    product_df: pd.DataFrame,
    test_size: int = 6,
    season_length: int = 12,
) -> pd.DataFrame:
    """
    Month-by-month table comparing actual sales against every model's
    forecast for the held-out test period, for ONE product. This is
    what you look at to visually see how close the forecast really was.
    """
    sales = product_df["total_quantity"].astype(float).reset_index(drop=True)
    test_months = product_df["month"].iloc[-test_size:].reset_index(drop=True)

    result = run_walk_forward(sales, test_size=test_size, season_length=season_length)

    comparison = pd.DataFrame({
        "month": test_months,
        "actual": result["test"].to_numpy(),
    })
    for model_name, preds in result["predictions"].items():
        comparison[model_name] = preds

    best, ranking_metric = pick_best_model(result["evaluation"])
    comparison.attrs["evaluation"] = result["evaluation"]
    comparison.attrs["best_model"] = best["model"] if best is not None else None
    comparison.attrs["ranked_by"] = ranking_metric

    return comparison


def build_catalog_actual_vs_forecast(
    monthly_df: pd.DataFrame,
    test_size: int = 6,
    season_length: int = 12,
) -> pd.DataFrame:
    """
    Builds ONE combined table across the whole catalog: for every
    product with enough real history, one row per test month showing
    actual sales vs. its best model's forecast. This is the real
    "forecast vs reality" view at scale — save it and review/chart it.
    """
    from src.sales_data import complete_product_series

    min_months = test_size + season_length + 1
    global_end_month = monthly_df["month"].max()
    rows = []

    for product_id, group in monthly_df.groupby("product_id"):
        product_df = complete_product_series(group.copy(), end_date=global_end_month)
        product_df["month"] = pd.to_datetime(product_df["month"])
        product_df = product_df.sort_values("month").reset_index(drop=True)

        sales = product_df["total_quantity"].astype(float)
        if len(sales) < min_months:
            continue
        if sales.iloc[:-test_size].sum() == 0 and sales.iloc[-test_size:].sum() == 0:
            continue  # dead/no-activity product — nothing meaningful to compare

        comparison = build_actual_vs_forecast_table(product_df, test_size, season_length)
        best_model = comparison.attrs.get("best_model")
        if best_model is None:
            continue

        product_name = group["product_name"].dropna()
        name = product_name.iloc[0] if not product_name.empty else None

        for _, row in comparison.iterrows():
            rows.append({
                "product_id": product_id,
                "product_name": name,
                "month": row["month"],
                "actual": row["actual"],
                "forecast": row[best_model],
                "best_model": best_model,
            })

    return pd.DataFrame(rows)