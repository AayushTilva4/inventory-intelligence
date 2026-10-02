import sys
from pathlib import Path

import pandas as pd


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.forecasting.engine_adapter import load_forecasting_inputs


def month_number(value):
    value = pd.Timestamp(value)
    return value.year * 12 + value.month


def main():
    print("=" * 70)
    print("SELECTING POC PRODUCTS")
    print("=" * 70)

    inputs = load_forecasting_inputs()

    monthly = inputs["monthly_df"].copy()
    stock_map = inputs["stock_map"]

    monthly["month"] = pd.to_datetime(monthly["month"])

    global_end = monthly["month"].max()
    global_end_num = month_number(global_end)

    rows = []

    for product_id, group in monthly.groupby("product_id"):
        group = group.sort_values("month")

        first_month = group["month"].min()
        last_sale = group["month"].max()

        history_months = global_end_num - month_number(first_month) + 1
        months_since_last_sale = global_end_num - month_number(last_sale)

        recent_start = global_end - pd.DateOffset(months=5)
        previous_start = global_end - pd.DateOffset(months=11)
        previous_end = global_end - pd.DateOffset(months=6)

        recent_sales = group.loc[
            group["month"] >= recent_start,
            "total_quantity",
        ].sum()

        previous_sales = group.loc[
            (group["month"] >= previous_start)
            & (group["month"] <= previous_end),
            "total_quantity",
        ].sum()

        recent_avg = float(recent_sales / 6)
        previous_avg = float(previous_sales / 6)

        if previous_avg > 0:
            trend_pct = (recent_avg - previous_avg) / previous_avg
        else:
            trend_pct = None

        active_months = len(group)
        active_ratio = active_months / history_months

        stock = float(stock_map.get(product_id, 0.0))

        # Same basic 4-month stock horizon used by the existing
        # reorder calculation: 3-month lead time + 1 month safety.
        reorder_proxy = recent_avg * 4

        if reorder_proxy > 0:
            stock_ratio = stock / reorder_proxy
        else:
            stock_ratio = None

        name_series = group["product_name"].dropna()
        product_name = (
            name_series.iloc[0]
            if not name_series.empty
            else None
        )

        rows.append(
            {
                "product_id": int(product_id),
                "product_name": product_name,
                "history_months": history_months,
                "months_since_last_sale": months_since_last_sale,
                "recent_avg": round(recent_avg, 2),
                "previous_avg": round(previous_avg, 2),
                "trend_pct": trend_pct,
                "active_ratio": round(active_ratio, 3),
                "stock_on_hand": round(stock, 2),
                "reorder_proxy": round(reorder_proxy, 2),
                "stock_ratio": stock_ratio,
            }
        )

    df = pd.DataFrame(rows)

    selected = {}

    def choose(label, candidates):
        candidates = candidates.copy()

        for product_id in selected.values():
            candidates = candidates[
                candidates["product_id"] != product_id
            ]

        if candidates.empty:
            print(f"[MISSING] {label}")
            return

        product_id = int(candidates.iloc[0]["product_id"])
        selected[label] = product_id

    # 1. Fast-moving
    choose(
        "fast_moving",
        df[
            df["history_months"] >= 18
        ].sort_values("recent_avg", ascending=False),
    )

    # 2. Rising demand
    choose(
        "rising_demand",
        df[
            (df["history_months"] >= 18)
            & (df["previous_avg"] > 5)
            & (df["recent_avg"] > df["previous_avg"])
        ].sort_values("trend_pct", ascending=False),
    )

    # 3. Falling demand
    choose(
        "falling_demand",
        df[
            (df["history_months"] >= 18)
            & (df["previous_avg"] > 5)
            & (df["recent_avg"] < df["previous_avg"])
        ].sort_values("trend_pct", ascending=True),
    )

    # 4. Low demand
    choose(
        "low_demand",
        df[
            (df["history_months"] >= 18)
            & (df["recent_avg"] > 0)
        ].sort_values("recent_avg", ascending=True),
    )

    # 5. Likely reorder-needed
    choose(
        "reorder_needed",
        df[
            (df["reorder_proxy"] > 0)
            & (df["stock_on_hand"] < df["reorder_proxy"])
        ].sort_values("stock_ratio", ascending=True),
    )

    # 6. Excess stock
    choose(
        "excess_stock",
        df[
            (df["reorder_proxy"] > 0)
            & (df["stock_on_hand"] > df["reorder_proxy"] * 1.5)
        ].sort_values("stock_ratio", ascending=False),
    )

    # 7. Intermittent demand
    choose(
        "intermittent",
        df[
            (df["history_months"] >= 18)
            & (df["active_ratio"] <= 0.35)
            & (df["recent_avg"] > 0)
        ].sort_values("active_ratio", ascending=True),
    )

    # 8. Dead-stock candidate
    choose(
        "dead_stock_candidate",
        df[
            (df["months_since_last_sale"] >= 6)
            & (df["stock_on_hand"] > 0)
        ].sort_values(
            ["months_since_last_sale", "stock_on_hand"],
            ascending=[False, False],
        ),
    )

    # 9. Cold-start
    choose(
        "cold_start",
        df[
            (df["history_months"] < 18)
            & (df["history_months"] >= 1)
        ].sort_values("history_months", ascending=True),
    )

    # 10. Normal / healthy stock
    choose(
        "normal_healthy",
        df[
            (df["history_months"] >= 18)
            & (df["reorder_proxy"] > 0)
            & (df["stock_ratio"] >= 0.8)
            & (df["stock_ratio"] <= 1.5)
        ].sort_values(
            ["stock_ratio", "recent_avg"],
            ascending=[True, False],
        ),
    )

    print()
    print("=" * 70)
    print("SELECTED POC PRODUCTS")
    print("=" * 70)

    selected_rows = []

    for scenario, product_id in selected.items():
        row = df[df["product_id"] == product_id].iloc[0].copy()
        row["scenario"] = scenario
        selected_rows.append(row)

    result = pd.DataFrame(selected_rows)

    columns = [
        "scenario",
        "product_id",
        "product_name",
        "history_months",
        "months_since_last_sale",
        "recent_avg",
        "previous_avg",
        "trend_pct",
        "active_ratio",
        "stock_on_hand",
        "reorder_proxy",
        "stock_ratio",
    ]

    print(
        result[columns].to_string(index=False)
    )

    output_dir = BACKEND_ROOT / "data"
    output_dir.mkdir(exist_ok=True)

    output_path = output_dir / "poc_products.csv"
    result[columns].to_csv(output_path, index=False)

    print()
    print(f"Saved to: {output_path}")
    print(f"Products selected: {len(result)}")


if __name__ == "__main__":
    main()