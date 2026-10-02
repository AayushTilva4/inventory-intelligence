from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.odoo.product_group_service import (
    _get_odoo_engine,
    get_main_product,
)


def _resolve_main_product_template(product_id: int) -> dict[str, Any] | None:
    main_product = get_main_product(product_id)
    if main_product is not None:
        return main_product

    engine = _get_odoo_engine()
    with engine.connect() as connection:
        template = connection.execute(
            text(
                """
                SELECT id, main_product
                FROM product_template
                WHERE id = :template_id
                """
            ),
            {"template_id": product_id},
        ).mappings().first()
        if template is None:
            return None

        main_product_template_id = template["main_product"] or template["id"]
        return connection.execute(
            text(
                """
                SELECT
                    id AS product_template_id,
                    name->>'en_US' AS product_name,
                    main_product AS main_product_id
                FROM product_template
                WHERE id = :template_id
                """
            ),
            {"template_id": main_product_template_id},
        ).mappings().first()


def get_group_monthly_demand(
    main_product_template_id: int,
) -> dict[str, Any] | None:
    engine = _get_odoo_engine()
    with engine.connect() as connection:
        main_product = connection.execute(
            text(
                """
                SELECT id, name->>'en_US' AS product_name
                FROM product_template
                WHERE id = :main_product_template_id
                """
            ),
            {"main_product_template_id": main_product_template_id},
        ).mappings().first()
        if main_product is None:
            return None

        rows = connection.execute(
            text(
                """
                WITH group_monthly AS (
                    SELECT
                        date_trunc('month', so.date_order)::date AS month,
                        SUM(sol.qty_delivered) AS actual
                    FROM sale_order_line sol
                    JOIN sale_order so ON so.id = sol.order_id
                    WHERE so.state = 'sale'
                      AND sol.product_id IS NOT NULL
                      AND sol.display_type IS NULL
                      AND sol.main_product = :main_product_template_id
                    GROUP BY date_trunc('month', so.date_order)::date
                ), series_bounds AS (
                    SELECT
                        MIN(month) AS first_month,
                        (
                            SELECT MAX(date_trunc('month', sales_order.date_order)::date)
                            FROM sale_order_line sales_line
                            JOIN sale_order sales_order
                                ON sales_order.id = sales_line.order_id
                            WHERE sales_order.state = 'sale'
                              AND sales_line.product_id IS NOT NULL
                              AND sales_line.display_type IS NULL
                        ) AS last_month
                    FROM group_monthly
                ), complete_months AS (
                    SELECT generate_series(
                        series_bounds.first_month::timestamp,
                        series_bounds.last_month::timestamp,
                        INTERVAL '1 month'
                    )::date AS month
                    FROM series_bounds
                    WHERE first_month IS NOT NULL
                      AND last_month IS NOT NULL
                      AND first_month <= last_month
                )
                SELECT
                    to_char(complete_months.month, 'YYYY-MM') AS month,
                    COALESCE(group_monthly.actual, 0) AS actual
                FROM complete_months
                LEFT JOIN group_monthly
                    ON group_monthly.month = complete_months.month
                ORDER BY complete_months.month
                """
            ),
            {"main_product_template_id": main_product_template_id},
        ).mappings().all()

    months = [
        {"month": row["month"], "actual": float(row["actual"])}
        for row in rows
    ]
    total_demand = float(
        sum((row["actual"] for row in rows), Decimal("0"))
    )

    return {
        "main_product_template_id": main_product["id"],
        "main_product_name": main_product["product_name"],
        "months": months,
        "total_demand": total_demand,
        "months_with_demand": sum(row["actual"] > 0 for row in rows),
    }


def get_group_demand_history(product_id: int) -> dict[str, Any] | None:
    main_product = _resolve_main_product_template(product_id)
    if main_product is None:
        return None

    return get_group_monthly_demand(
        int(main_product["product_template_id"])
    )