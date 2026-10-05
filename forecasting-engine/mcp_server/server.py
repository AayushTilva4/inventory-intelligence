import sys
from pathlib import Path

# ============================================================
# ADD PROJECT ROOT TO PYTHON PATH
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# IMPORTS
# ============================================================

from mcp.server import MCPServer
from sqlalchemy import text

from src.db import get_engine


# ============================================================
# MCP SERVER
# ============================================================

mcp = MCPServer("Odoo Forecasting")


# ============================================================
# TEST DATABASE CONNECTION
# ============================================================

@mcp.tool()
def test_database_connection() -> str:
    """
    Test whether the MCP server can connect to PostgreSQL.
    """

    try:
        engine = get_engine()

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return "PostgreSQL connection successful!"

    except Exception as e:
        return f"PostgreSQL connection failed: {str(e)}"


# ============================================================
# GET PRODUCT INFORMATION
# ============================================================

@mcp.tool()
def get_product_info(product_code: str) -> dict:
    """
    Get basic information for one Odoo product.

    The supplied product identifier can match either:
    - Odoo default_code
    - Odoo product name

    This allows identifiers such as 351-02 and 201-03
    used by the forecasting system.
    """

    engine = get_engine()

    query = """
        SELECT
            pp.id AS product_id,
            pp.default_code AS default_code,
            pt.name->>'en_US' AS product_name
        FROM product_product pp
        JOIN product_template pt
            ON pt.id = pp.product_tmpl_id
        WHERE
            pp.default_code = :product_code
            OR pt.name->>'en_US' = :product_code
        ORDER BY
            CASE
                WHEN pp.default_code = :product_code THEN 0
                ELSE 1
            END
        LIMIT 1;
    """

    try:
        with engine.connect() as connection:

            result = connection.execute(
                text(query),
                {
                    "product_code": product_code
                }
            )

            row = result.fetchone()

            if row is None:
                return {
                    "found": False,
                    "product_code": product_code,
                    "message": f"Product '{product_code}' was not found."
                }

            return {
                "found": True,
                "product_id": int(row.product_id),
                "product_code": (
                    row.default_code
                    if row.default_code is not None
                    else None
                ),
                "product_name": row.product_name,
                "requested_identifier": product_code,
            }

    except Exception as e:

        return {
            "found": False,
            "product_code": product_code,
            "error": str(e)
        }


# ============================================================
# GET MONTHLY SALES HISTORY
# ============================================================

@mcp.tool()
def get_product_sales_history(
    product_code: str,
    months: int = 36,
) -> dict:
    """
    Get monthly sales history for one Odoo product.

    The product can be identified using either:
    - Odoo default_code
    - Odoo product name

    Only monthly aggregated quantities are returned.

    Months with no sales are explicitly returned as zero.
    Raw sale order lines are never exposed to the agent.

    Maximum history returned: 36 months.
    """

    # --------------------------------------------------------
    # Validate months
    # --------------------------------------------------------

    if months <= 0:
        months = 1

    if months > 36:
        months = 36

    engine = get_engine()

    query = """
        WITH selected_product AS (
            SELECT
                pp.id AS product_id,
                pp.default_code,
                pt.name->>'en_US' AS product_name
            FROM product_product pp
            JOIN product_template pt
                ON pt.id = pp.product_tmpl_id
            WHERE
                pp.default_code = :product_code
                OR pt.name->>'en_US' = :product_code
            ORDER BY
                CASE
                    WHEN pp.default_code = :product_code THEN 0
                    ELSE 1
                END
            LIMIT 1
        ),

        months AS (
            SELECT
                generate_series(
                    DATE_TRUNC(
                        'month',
                        CURRENT_DATE
                    ) - (:months * INTERVAL '1 month'),

                    DATE_TRUNC(
                        'month',
                        CURRENT_DATE
                    ) - INTERVAL '1 month',

                    INTERVAL '1 month'
                )::date AS month
        ),

        monthly_sales AS (
            SELECT
                DATE_TRUNC(
                    'month',
                    so.date_order
                )::date AS month,

                SUM(
                    sol.product_uom_qty
                ) AS total_quantity

            FROM sale_order so

            JOIN sale_order_line sol
                ON sol.order_id = so.id

            JOIN selected_product sp
                ON sp.product_id = sol.product_id

            WHERE so.state = 'sale'

              AND so.date_order >=
                  DATE_TRUNC(
                      'month',
                      CURRENT_DATE
                  ) - ((:months - 1) * INTERVAL '1 month')

              AND so.date_order <
                  DATE_TRUNC(
                      'month',
                      CURRENT_DATE
                  )

            GROUP BY
                DATE_TRUNC(
                    'month',
                    so.date_order
                )
        )

        SELECT
            m.month,
            COALESCE(
                ms.total_quantity,
                0
            ) AS total_quantity

        FROM months m

        LEFT JOIN monthly_sales ms
            ON ms.month = m.month

        ORDER BY m.month;
    """

    try:

        with engine.connect() as connection:

            # First verify the product exists.
            product_result = connection.execute(
                text("""
                    SELECT
                        pp.id AS product_id,
                        pp.default_code AS default_code,
                        pt.name->>'en_US' AS product_name
                    FROM product_product pp
                    JOIN product_template pt
                        ON pt.id = pp.product_tmpl_id
                    WHERE
                        pp.default_code = :product_code
                        OR pt.name->>'en_US' = :product_code
                    ORDER BY
                        CASE
                            WHEN pp.default_code = :product_code
                            THEN 0
                            ELSE 1
                        END
                    LIMIT 1;
                """),
                {
                    "product_code": product_code
                }
            )

            product_row = product_result.fetchone()

            if product_row is None:
                return {
                    "found": False,
                    "product_code": product_code,
                    "months_requested": months,
                    "sales": [],
                    "message": (
                        f"Product '{product_code}' was not found."
                    )
                }

            result = connection.execute(
                text(query),
                {
                    "product_code": product_code,
                    "months": months,
                }
            )

            rows = result.fetchall()

            sales = []

            for row in rows:

                sales.append(
                    {
                        "month": str(row.month),
                        "total_quantity": float(
                            row.total_quantity
                        ),
                    }
                )

            return {
                "found": True,
                "product_id": int(product_row.product_id),
                "product_name": product_row.product_name,
                "product_code": (
                    product_row.default_code
                    if product_row.default_code is not None
                    else None
                ),
                "requested_identifier": product_code,
                "months_requested": months,
                "number_of_months": len(sales),
                "sales": sales,
            }

    except Exception as e:

        return {
            "found": False,
            "product_code": product_code,
            "error": str(e),
        }


# ============================================================
# GET SMALL SALES SUMMARY
# ============================================================

@mcp.tool()
def get_product_sales_summary(
    product_code: str,
) -> dict:
    """
    Return a small summary of a product's sales.

    This tool is intentionally small so the agent does not
    need to retrieve the complete sales history when it only
    needs a quick overview.
    """

    engine = get_engine()

    query = """
        WITH selected_product AS (
            SELECT
                pp.id AS product_id,
                pp.default_code AS default_code,
                pt.name->>'en_US' AS product_name
            FROM product_product pp
            JOIN product_template pt
                ON pt.id = pp.product_tmpl_id
            WHERE
                pp.default_code = :product_code
                OR pt.name->>'en_US' = :product_code
            ORDER BY
                CASE
                    WHEN pp.default_code = :product_code THEN 0
                    ELSE 1
                END
            LIMIT 1
        )

        SELECT

            sp.product_id,

            sp.default_code,

            sp.product_name,

            COUNT(
                DISTINCT so.id
            ) AS sales_records,

            COALESCE(
                SUM(sol.product_uom_qty),
                0
            ) AS total_quantity,

            MAX(
                so.date_order
            )::date AS last_sale_date

        FROM selected_product sp

        LEFT JOIN sale_order_line sol
            ON sol.product_id = sp.product_id

        LEFT JOIN sale_order so
            ON so.id = sol.order_id
            AND so.state = 'sale'

        GROUP BY
            sp.product_id,
            sp.default_code,
            sp.product_name;
    """

    try:

        with engine.connect() as connection:

            result = connection.execute(
                text(query),
                {
                    "product_code": product_code
                }
            )

            row = result.fetchone()

            if row is None:

                return {
                    "found": False,
                    "product_code": product_code,
                    "message": (
                        f"Product '{product_code}' was not found."
                    )
                }

            return {
                "found": True,
                "product_id": int(row.product_id),
                "product_code": (
                    row.default_code
                    if row.default_code is not None
                    else None
                ),
                "product_name": row.product_name,
                "requested_identifier": product_code,
                "sales_records": int(
                    row.sales_records
                ),
                "total_quantity": float(
                    row.total_quantity
                ),
                "last_sale_date": (
                    str(row.last_sale_date)
                    if row.last_sale_date
                    else None
                ),
            }

    except Exception as e:

        return {
            "found": False,
            "product_code": product_code,
            "error": str(e),
        }


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":
    mcp.run()