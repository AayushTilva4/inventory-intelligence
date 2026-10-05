"""Historical analogue helpers for cold-start demand forecasting.

All Odoo access in this module is READ-ONLY.  The module only executes
SELECT statements and keeps the derived analogue data in memory.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.db import get_engine


MIN_OLD_SELLING_MONTHS = 6
DEFAULT_RECENT_MONTHS = 12
DEFAULT_MAX_ANALOGUES = 5


def fetch_historical_similarity_candidates(
    recent_months: int = DEFAULT_RECENT_MONTHS,
    min_old_selling_months: int = MIN_OLD_SELLING_MONTHS,
) -> pd.DataFrame:
    """Fetch recent products and their useful older Odoo-linked products.

    The query is intentionally read-only.  It uses the two strongest stored
    lineage signals currently identified in the Odoo snapshot:
    ``product_template.main_product`` and ``product_template_similar_rel``.

    Product IDs returned here are ``product_product.id`` so they match the
    IDs already used by ``monthly_df`` in the existing forecasting pipeline.
    """
    if recent_months <= 0:
        raise ValueError("recent_months must be greater than 0")
    if min_old_selling_months <= 0:
        raise ValueError("min_old_selling_months must be greater than 0")

    engine = get_engine()

    query = """
        WITH latest_month AS (
            SELECT DATE_TRUNC('month', MAX(so.date_order)) AS month
            FROM sale_order so
            WHERE so.state = 'sale'
        ),
        relationships AS (
            /* Explicit main_product pointer: orient newer -> older. */
            SELECT
                newer.id AS new_template_id,
                older.id AS old_template_id,
                'main_product' AS source
            FROM product_template newer
            JOIN product_template older
                ON older.id = newer.main_product
            WHERE newer.main_product IS NOT NULL
              AND newer.id <> older.id
              AND newer.create_date > older.create_date

            UNION ALL

            /* Similar relation: normalize direction using create_date. */
            SELECT
                CASE
                    WHEN src.create_date > dest.create_date THEN src.id
                    ELSE dest.id
                END AS new_template_id,
                CASE
                    WHEN src.create_date > dest.create_date THEN dest.id
                    ELSE src.id
                END AS old_template_id,
                'similar_relation' AS source
            FROM product_template_similar_rel rel
            JOIN product_template src
                ON src.id = rel.src_id
            JOIN product_template dest
                ON dest.id = rel.dest_id
            WHERE src.id <> dest.id
              AND src.create_date <> dest.create_date
        ),
        deduped_relationships AS (
            SELECT
                new_template_id,
                old_template_id,
                STRING_AGG(DISTINCT source, ', ' ORDER BY source) AS link_sources
            FROM relationships
            GROUP BY new_template_id, old_template_id
        ),
        sales_by_template AS (
            SELECT
                pp.product_tmpl_id AS template_id,
                MIN(so.date_order)::date AS first_sale_date,
                MAX(so.date_order)::date AS last_sale_date,
                SUM(sol.product_uom_qty)::double precision AS sales_quantity,
                COUNT(DISTINCT DATE_TRUNC('month', so.date_order))::int AS selling_months,
                COUNT(*)::int AS sale_lines
            FROM sale_order_line sol
            JOIN sale_order so
                ON so.id = sol.order_id
            JOIN product_product pp
                ON pp.id = sol.product_id
            WHERE so.state = 'sale'
              AND sol.product_id IS NOT NULL
              AND sol.display_type IS NULL
            GROUP BY pp.product_tmpl_id
        )
        SELECT
            pp_new.id AS new_product_id,
            new_template.name->>'en_US' AS new_product_name,
            new_template.create_date AS new_product_create_date,
            new_template.categ_id AS new_category_id,

            pp_old.id AS old_product_id,
            old_template.name->>'en_US' AS old_product_name,
            old_template.create_date AS old_product_create_date,
            old_template.categ_id AS old_category_id,
            old_template.active AS old_product_active,

            rel.link_sources,

            old_sales.first_sale_date AS old_first_sale_date,
            old_sales.last_sale_date AS old_last_sale_date,
            COALESCE(old_sales.selling_months, 0) AS old_selling_months,
            COALESCE(old_sales.sales_quantity, 0) AS old_sales_quantity,
            COALESCE(old_sales.sale_lines, 0) AS old_sale_lines,

            new_sales.first_sale_date AS new_first_sale_date,
            new_sales.last_sale_date AS new_last_sale_date,
            COALESCE(new_sales.selling_months, 0) AS new_selling_months,
            COALESCE(new_sales.sales_quantity, 0) AS new_sales_quantity,
            COALESCE(new_sales.sale_lines, 0) AS new_sale_lines

        FROM deduped_relationships rel
        JOIN product_template new_template
            ON new_template.id = rel.new_template_id
        JOIN product_template old_template
            ON old_template.id = rel.old_template_id
        JOIN product_product pp_new
            ON pp_new.product_tmpl_id = new_template.id
        JOIN product_product pp_old
            ON pp_old.product_tmpl_id = old_template.id
        LEFT JOIN sales_by_template old_sales
            ON old_sales.template_id = old_template.id
        LEFT JOIN sales_by_template new_sales
            ON new_sales.template_id = new_template.id
        CROSS JOIN latest_month lm

        WHERE new_template.create_date >= (
                  lm.month - make_interval(months => %(recent_months)s)
              )
          AND COALESCE(old_sales.selling_months, 0) >= %(min_old_selling_months)s

        ORDER BY new_template.create_date DESC,
                 old_sales.selling_months DESC,
                 pp_new.id,
                 pp_old.id;
    """

    return pd.read_sql(
        query,
        engine,
        params={
            "recent_months": int(recent_months),
            "min_old_selling_months": int(min_old_selling_months),
        },
    )


def load_similarity_candidates(csv_path: str | Path) -> pd.DataFrame:
    """Load a previously generated read-only candidate snapshot from CSV."""
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Similarity candidate CSV not found: {path}")

    df = pd.read_csv(path)
    required = {"new_product_id", "old_product_id", "old_selling_months"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Similarity CSV is missing columns: {sorted(missing)}")

    return df


def _lifecycle_series(product_id: int, monthly_df: pd.DataFrame, end_month) -> pd.Series:
    """Return a continuous lifecycle series from first sale through end_month."""
    group = monthly_df[monthly_df["product_id"] == product_id].copy()
    if group.empty:
        return pd.Series(dtype=float)

    group["month"] = pd.to_datetime(group["month"])
    group = group.sort_values("month")

    start = group["month"].min()
    end = pd.Timestamp(end_month)
    if start > end:
        return pd.Series(dtype=float)

    full_months = pd.date_range(start=start, end=end, freq="MS")
    series = (
        group.set_index("month")["total_quantity"]
        .reindex(full_months)
        .fillna(0.0)
        .astype(float)
    )
    series.index.name = "month"
    return series.reset_index(drop=True)


def _scaled_lifecycle_signal(
    own_sales: pd.Series,
    old_sales: pd.Series,
    age_months: int,
) -> float | None:
    """Estimate next demand from an old lifecycle, scaled to own early sales."""
    if age_months < 0 or len(old_sales) <= age_months:
        return None

    # Use only the portion of the analogue lifecycle that would have been
    # observable by the current product age.
    own_obs = own_sales.iloc[:age_months].astype(float)
    old_obs = old_sales.iloc[:age_months].astype(float)

    if age_months == 0:
        scale = 1.0
    else:
        old_total = float(old_obs.sum())
        own_total = float(own_obs.sum())

        if old_total <= 0 or own_total <= 0:
            scale = 1.0
        else:
            scale = own_total / old_total
            # Prevent a tiny early sample from multiplying an analogue by
            # an unrealistic factor.
            scale = float(np.clip(scale, 0.25, 4.0))

    # Smooth the next 1-3 lifecycle months.  This keeps one unusual month
    # from dominating the cold-start forecast while staying easy to explain.
    future = old_sales.iloc[age_months : age_months + 3].astype(float)
    if future.empty:
        return None

    weights = np.array([0.60, 0.30, 0.10], dtype=float)[: len(future)]
    weights = weights / weights.sum()
    lifecycle_signal = float(np.dot(future.to_numpy(), weights))

    return max(lifecycle_signal * scale, 0.0)


def historical_analogue_forecast(
    product_id: int,
    product_df: pd.DataFrame,
    monthly_df: pd.DataFrame,
    similarity_candidates: pd.DataFrame,
    min_old_selling_months: int = MIN_OLD_SELLING_MONTHS,
    max_analogues: int = DEFAULT_MAX_ANALOGUES,
) -> dict:
    """Forecast a new/short-history product from Odoo-linked old products.

    This function deliberately uses only explicit Odoo relationships and
    older products with enough historical sales.  Name-only matches are not
    used here.
    """
    if max_analogues <= 0:
        raise ValueError("max_analogues must be greater than 0")

    candidates = similarity_candidates.copy()
    candidates["new_product_id"] = pd.to_numeric(candidates["new_product_id"], errors="coerce")
    candidates["old_product_id"] = pd.to_numeric(candidates["old_product_id"], errors="coerce")
    candidates["old_selling_months"] = pd.to_numeric(
        candidates["old_selling_months"], errors="coerce"
    ).fillna(0)

    candidates = candidates[
        (candidates["new_product_id"] == int(product_id))
        & (candidates["old_selling_months"] >= min_old_selling_months)
    ].copy()

    if candidates.empty:
        return {
            "status": "cold_start_no_analogue",
            "confidence": "very_low",
            "next_month_forecast": 0.0,
            "trend": "unknown",
            "trend_pct_change": None,
            "reorder_point": 0.0,
            "avg_monthly_demand": 0.0,
            "analogue_count": 0,
            "analogue_products": [],
        }

    # Prefer older products with more historical selling months.  The score
    # is only used to limit the number of candidates; final estimates are
    # averaged to avoid over-trusting one relationship.
    candidates = (
        candidates
        .sort_values("old_selling_months", ascending=False)
        .drop_duplicates(subset=["old_product_id"])
        .head(max_analogues)
    )

    own_sales = product_df["total_quantity"].astype(float).reset_index(drop=True)
    age_months = len(own_sales)
    end_month = product_df["month"].max()

    forecasts: list[float] = []
    analogue_names: list[str] = []
    usable_rows: list[dict] = []

    for _, row in candidates.iterrows():
        old_id = int(row["old_product_id"])
        old_lifecycle = _lifecycle_series(old_id, monthly_df, end_month)
        signal = _scaled_lifecycle_signal(own_sales, old_lifecycle, age_months)

        if signal is None:
            continue

        forecasts.append(signal)
        analogue_names.append(str(row.get("old_product_name") or old_id))
        usable_rows.append(
            {
                "old_product_id": old_id,
                "old_product_name": row.get("old_product_name"),
                "old_selling_months": float(row["old_selling_months"]),
                "forecast_signal": round(signal, 4),
                "link_sources": row.get("link_sources"),
            }
        )

    if not forecasts:
        return {
            "status": "cold_start_no_usable_analogue",
            "confidence": "very_low",
            "next_month_forecast": 0.0,
            "trend": "unknown",
            "trend_pct_change": None,
            "reorder_point": 0.0,
            "avg_monthly_demand": 0.0,
            "analogue_count": 0,
            "analogue_products": [],
        }

    # Median is deliberately used instead of summing analogue demand.  Each
    # analogue is a reference pattern, not an additive demand source.
    analogue_forecast = float(np.median(forecasts))

    # A small amount of own observed demand keeps the forecast connected to
    # the actual new product when 1-3 months of sales already exist.
    own_recent_avg = float(own_sales.tail(min(3, len(own_sales))).mean()) if len(own_sales) else 0.0
    own_weight = 0.25 if len(own_sales) >= 2 else 0.15 if len(own_sales) == 1 else 0.0

    final_forecast = (1.0 - own_weight) * analogue_forecast + own_weight * own_recent_avg
    final_forecast = max(float(final_forecast), 0.0)

    confidence = "low" if len(forecasts) == 1 else "normal"

    return {
        "status": "cold_start_historical_analogue",
        "confidence": confidence,
        "next_month_forecast": round(final_forecast, 1),
        "trend": "unknown",
        "trend_pct_change": None,
        "reorder_point": round(final_forecast * 4.0, 1),
        "avg_monthly_demand": round(final_forecast, 1),
        "analogue_count": len(forecasts),
        "analogue_products": analogue_names,
        "analogue_details": usable_rows,
    }
