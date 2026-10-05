import pandas as pd

from src.db import get_engine


def fetch_sales_data():
    engine = get_engine()

    query = """
        SELECT
            so.id AS order_id,
            so.date_order::date AS order_date,
            sol.product_id,
            pp.default_code AS product_code,
            pt.name->>'en_US' AS product_name,
            sol.product_uom_qty AS quantity
        FROM sale_order so
        JOIN sale_order_line sol
            ON sol.order_id = so.id
        JOIN product_product pp
            ON pp.id = sol.product_id
        JOIN product_template pt
            ON pt.id = pp.product_tmpl_id
        WHERE so.state = 'sale'
          AND sol.product_id IS NOT NULL
        ORDER BY so.date_order;
    """

    return pd.read_sql(query, engine)


def create_monthly_sales(df):
    df = df.copy()

    df["order_date"] = pd.to_datetime(df["order_date"])

    monthly_sales = (
        df.groupby(
            [
                pd.Grouper(key="order_date", freq="MS"),
                "product_id",
                "product_name",
            ],
            as_index=False,
        )["quantity"]
        .sum()
        .rename(
            columns={
                "order_date": "month",
                "quantity": "total_quantity",
            }
        )
    )

    return monthly_sales

def complete_product_series(product_df, end_date=None):
    product_df = product_df.copy()

    product_df["month"] = pd.to_datetime(product_df["month"])
    product_df = product_df.sort_values("month")

    # Extend to a shared end date (e.g. the latest month across the
    # whole dataset) rather than this product's own last sale month —
    # otherwise every product's series trivially "ends" on a nonzero
    # value and dead stock can never be detected.
    series_end = pd.to_datetime(end_date) if end_date is not None else product_df["month"].max()

    full_months = pd.date_range(
        start=product_df["month"].min(),
        end=series_end,
        freq="MS",
    )

    product_df = (
        product_df
        .set_index("month")
        .reindex(full_months)
        .rename_axis("month")
        .reset_index()
    )

    product_df["product_id"] = product_df["product_id"].ffill()
    product_df["product_name"] = product_df["product_name"].ffill()

    product_df["had_sales_record"] = (
        product_df["total_quantity"].notna()
    )

    product_df["total_quantity"] = (
        product_df["total_quantity"].fillna(0)
    )

    return product_df

def fetch_product_categories() -> dict:
    """
    Returns {product_id: category_name} for every product, pulled from
    Odoo's product_category via product_template. Used for cold-start
    fallback forecasting on products with too little sales history.
    """
    engine = get_engine()

    query = """
        SELECT
            pp.id AS product_id,
            pc.complete_name AS category
        FROM product_product pp
        JOIN product_template pt
            ON pt.id = pp.product_tmpl_id
        LEFT JOIN product_category pc
            ON pc.id = pt.categ_id;
    """

    df = pd.read_sql(query, engine)

    return dict(zip(df["product_id"], df["category"]))


def fetch_stock_on_hand() -> pd.DataFrame:
    """
    Returns current on-hand stock quantity per product from Odoo's
    stock_quant table (only counting quantities in internal/storage
    locations, not e.g. supplier or customer locations).
    """
    engine = get_engine()

    query = """
        SELECT
            sq.product_id,
            SUM(sq.quantity) AS stock_on_hand
        FROM stock_quant sq
        JOIN stock_location sl
            ON sl.id = sq.location_id
        WHERE sl.usage = 'internal'
        GROUP BY sq.product_id;
    """

    df = pd.read_sql(query, engine)
    return df