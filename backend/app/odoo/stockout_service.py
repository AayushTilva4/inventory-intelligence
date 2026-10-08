import math
from typing import Any
import pandas as pd
import numpy as np
from sqlalchemy import text
from app.db.connection import get_odoo_engine


def reconstruct_group_stock_history(
    main_product_template_id: int,
    connection=None,
) -> pd.DataFrame:
    """
    Reconstructs historical stock movements into internal locations for all variants in the group.
    Returns DataFrame with columns: ['date', 'delta', 'cum_stock']
    """
    close_conn = False
    if connection is None:
        engine = get_odoo_engine()
        connection = engine.connect()
        close_conn = True

    try:
        variants = connection.execute(
            text("""
                SELECT pp.id
                FROM product_product pp
                JOIN product_template pt ON pp.product_tmpl_id = pt.id
                WHERE pt.id = :tid OR pt.main_product = :tid
            """),
            {"tid": main_product_template_id},
        ).scalars().all()

        if not variants:
            return pd.DataFrame(columns=["date", "delta", "cum_stock"])

        moves = connection.execute(
            text("""
                SELECT
                    sm.date,
                    CASE
                        WHEN sl_dest.usage = 'internal' AND sl_src.usage != 'internal' THEN sm.quantity
                        WHEN sl_src.usage = 'internal' AND sl_dest.usage != 'internal' THEN -sm.quantity
                        ELSE 0
                    END AS delta
                FROM stock_move sm
                JOIN stock_location sl_src ON sm.location_id = sl_src.id
                JOIN stock_location sl_dest ON sm.location_dest_id = sl_dest.id
                WHERE sm.product_id IN :vids
                  AND sm.state = 'done'
                ORDER BY sm.date
            """),
            {"vids": tuple(variants)},
        ).mappings().all()

        if not moves:
            return pd.DataFrame(columns=["date", "delta", "cum_stock"])

        df = pd.DataFrame(moves)
        df["date"] = pd.to_datetime(df["date"])
        df["cum_stock"] = df["delta"].cumsum()
        return df
    finally:
        if close_conn:
            connection.close()


def classify_group_monthly_stockouts(
    main_product_template_id: int,
    months: list[dict[str, Any]],
    df_moves: pd.DataFrame | None = None,
    connection=None,
) -> list[dict[str, Any]]:
    """
    Deterministically classifies each month into:
    - NORMAL_DEMAND (actual > 0)
    - STOCKOUT_SUPPRESSED (actual == 0 and stock <= threshold)
    - NORMAL_ZERO_DEMAND (actual == 0 and stock > threshold)
    - UNKNOWN (no stock history or indeterminate)
    """
    if df_moves is None:
        df_moves = reconstruct_group_stock_history(main_product_template_id, connection=connection)

    has_moves = len(df_moves) > 0
    first_move_date = df_moves["date"].min() if has_moves else None

    pos_actuals = [float(m["actual"]) for m in months if float(m.get("actual", 0.0)) > 0]
    median_demand = float(np.median(pos_actuals)) if pos_actuals else 0.0

    if median_demand >= 50.0:
        stock_threshold = 5.0
    elif median_demand > 0:
        stock_threshold = min(5.0, max(1.0, 0.05 * median_demand))
    else:
        stock_threshold = 0.0

    first_sale_idx = None
    for idx, m in enumerate(months):
        if float(m.get("actual", 0.0)) > 0:
            if first_sale_idx is None:
                first_sale_idx = idx

    enriched_months = []
    for idx, m in enumerate(months):
        m_str = m["month"]
        actual = float(m.get("actual", 0.0))
        m_start = pd.Timestamp(m_str + "-01")
        m_end = m_start + pd.offsets.MonthEnd(1) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)

        month_has_stock = has_moves and (m_end >= first_move_date)

        if not month_has_stock:
            stock_start = stock_end = min_stock = max_stock = 0.0
        else:
            stock_start = float(df_moves[df_moves["date"] < m_start]["delta"].sum()) if has_moves else 0.0
            stock_end = float(df_moves[df_moves["date"] <= m_end]["delta"].sum()) if has_moves else 0.0
            in_m = df_moves[(df_moves["date"] >= m_start) & (df_moves["date"] <= m_end)]
            min_stock = float(in_m["cum_stock"].min()) if len(in_m) > 0 else stock_start
            max_stock = float(in_m["cum_stock"].max()) if len(in_m) > 0 else stock_start

        if actual > 0:
            classification = "NORMAL_DEMAND"
            reason = "positive_sales"
            is_stockout = False
        elif not month_has_stock:
            classification = "UNKNOWN"
            reason = "no_stock_history_available"
            is_stockout = False
        elif first_sale_idx is not None and idx < first_sale_idx:
            classification = "NORMAL_ZERO_DEMAND"
            reason = "pre_launch_period"
            is_stockout = False
        elif max_stock <= max(0.0, stock_threshold):
            classification = "STOCKOUT_SUPPRESSED"
            reason = f"zero_sales_with_depleted_stock(max_stock={max_stock:.1f}<=threshold={stock_threshold:.1f})"
            is_stockout = True
        else:
            classification = "NORMAL_ZERO_DEMAND"
            reason = f"zero_sales_with_available_stock(max_stock={max_stock:.1f}>threshold={stock_threshold:.1f})"
            is_stockout = False

        enriched_months.append({
            "month": m_str,
            "actual": actual,
            "classification": classification,
            "is_stockout": is_stockout,
            "stock_start": round(stock_start, 2),
            "stock_end": round(stock_end, 2),
            "min_stock": round(min_stock, 2),
            "max_stock": round(max_stock, 2),
            "reason": reason,
        })

    return enriched_months


def build_missing_demand_series(
    enriched_months: list[dict[str, Any]],
    as_of_idx: int | None = None,
) -> pd.Series:
    """
    Method C: True missing representation.
    Leaves STOCKOUT_SUPPRESSED months as NaN (unobserved) while retaining calendar months.
    """
    sub = enriched_months if as_of_idx is None else enriched_months[:as_of_idx]
    if not sub:
        return pd.Series(dtype=float)

    raw_values = []
    for m in sub:
        if m.get("is_stockout") or m.get("classification") == "STOCKOUT_SUPPRESSED":
            raw_values.append(np.nan)
        else:
            raw_values.append(float(m.get("actual", 0.0)))

    return pd.Series(raw_values, dtype=float)


def build_corrected_demand_series(
    enriched_months: list[dict[str, Any]],
    as_of_idx: int | None = None,
) -> pd.Series:
    """
    Method D: Missing-aware demand representation for model training.
    Filters out unobserved STOCKOUT_SUPPRESSED months when calculating demand estimators,
    preventing artificial zero collapse without inventing arbitrary synthetic values.
    """
    s_nan = build_missing_demand_series(enriched_months, as_of_idx=as_of_idx)
    s_clean = s_nan.dropna()
    if s_clean.empty:
        return pd.Series([0.0] * len(s_nan), dtype=float)
    return s_clean.reset_index(drop=True)
