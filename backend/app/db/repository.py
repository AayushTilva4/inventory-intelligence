from typing import Any
import json

import pandas as pd

from app.db.connection import get_poc_engine
from app.forecasting.forecast_service import get_similar_products_for_id
from sqlalchemy import text

def save_forecasts(df: pd.DataFrame) -> None:
    engine = get_poc_engine()

    df.to_sql(
        "forecast_results",
        engine,
        if_exists="replace",
        index=False,
    )


def save_recommendations(df: pd.DataFrame) -> None:
    engine = get_poc_engine()

    df.to_sql(
        "inventory_recommendations",
        engine,
        if_exists="replace",
        index=False,
    )

def get_recommendations() -> list[dict[str, Any]]:
    engine = get_poc_engine()

    query = """
        SELECT
            r.*,
            d.po_number AS draft_po_number,
            d.status AS draft_po_status,
            d.created_at AS draft_po_created_at,
            f.months_available,
            f.confidence,
            f.trend,
            f.best_model,
            f.status AS forecast_status,
            f.months_since_last_sale,
            f.dead_stock,
            f.dead_stock_reason,
            f.analogue_count,
            f.analogue_products,
            f.analogue_details
        FROM inventory_recommendations r
        LEFT JOIN forecast_results f ON r.product_id = f.product_id
        LEFT JOIN draft_purchase_orders d ON r.product_id = d.product_id
        ORDER BY
            CASE r.priority
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
                ELSE 4
            END,
            r.product_id;
    """

    df = pd.read_sql(query, engine)

    if df.empty:
        return []

    # Convert NaN/NaT into JSON-safe None values.
    df = df.astype(object).where(pd.notna(df), None)

    records = df.to_dict(orient="records")

    for record in records:
        reason_codes = record.get("reason_codes")

        # PostgreSQL ARRAY values may be returned as a string
        # depending on how the POC table was created.
        if isinstance(reason_codes, str):
            value = reason_codes.strip()

            if value.startswith("{") and value.endswith("}"):
                value = value[1:-1]

                if value.strip():
                    record["reason_codes"] = [
                        item.strip()
                        for item in value.split(",")
                    ]
                else:
                    record["reason_codes"] = []
            else:
                record["reason_codes"] = [value] if value else []

        val_prods = record.get("analogue_products")
        if isinstance(val_prods, str):
            try:
                record["analogue_products"] = json.loads(val_prods)
            except Exception:
                record["analogue_products"] = [val_prods]
        elif val_prods is None:
            record["analogue_products"] = None

        val_details = record.get("analogue_details")
        if isinstance(val_details, str):
            try:
                record["analogue_details"] = json.loads(val_details)
            except Exception:
                record["analogue_details"] = None
        elif val_details is None:
            record["analogue_details"] = None

        val_count = record.get("analogue_count")
        if val_count is not None and not pd.isna(val_count):
            try:
                record["analogue_count"] = int(val_count)
            except Exception:
                record["analogue_count"] = None
        else:
            record["analogue_count"] = None

        record["similar_products"] = get_similar_products_for_id(record["product_id"])

    return records

def get_product_intelligence(product_id: int) -> dict[str, Any] | None:
    engine = get_poc_engine()

    query = """
        SELECT
            f.product_id,
            f.product_name,
            f.status,
            f.best_model,
            f.ranked_by,
            f."MAE" AS mae,
            f."WAPE" AS wape,
            f."MASE" AS mase,
            f.confidence,
            f.next_month_forecast,
            f.months_available,
            f.trend,
            f.trend_pct_change,
            f.reorder_point,
            f.avg_monthly_demand,
            f.dead_stock,
            f.dead_stock_reason,
            f.suggested_discount_pct,
            f.months_since_last_sale,
            f.stock_on_hand,
            f.analogue_count,
            f.analogue_products,
            f.analogue_details,

            r.action,
            r.priority,
            r.buffered_target_stock,
            r.stock_gap,
            r.coverage_ratio,
            r.suggested_purchase_qty,
            r.reason_codes

        FROM forecast_results f

        JOIN inventory_recommendations r
            ON r.product_id = f.product_id

        WHERE f.product_id = %(product_id)s
        LIMIT 1;
    """

    df = pd.read_sql(
        query,
        engine,
        params={"product_id": product_id},
    )

    if df.empty:
        return None

    record = (
        df.astype(object)
        .where(pd.notna(df), None)
        .iloc[0]
        .to_dict()
    )

    record["forecast_status"] = record.get("status")

    val_prods = record.get("analogue_products")
    if isinstance(val_prods, str):
        try:
            record["analogue_products"] = json.loads(val_prods)
        except Exception:
            record["analogue_products"] = [val_prods]
    elif val_prods is None:
        record["analogue_products"] = None

    val_details = record.get("analogue_details")
    if isinstance(val_details, str):
        try:
            record["analogue_details"] = json.loads(val_details)
        except Exception:
            record["analogue_details"] = None
    elif val_details is None:
        record["analogue_details"] = None

    val_count = record.get("analogue_count")
    if val_count is not None and not pd.isna(val_count):
        try:
            record["analogue_count"] = int(val_count)
        except Exception:
            record["analogue_count"] = None
    else:
        record["analogue_count"] = None

    record["similar_products"] = get_similar_products_for_id(product_id)

    reason_codes = record.get("reason_codes")

    if isinstance(reason_codes, str):
        value = reason_codes.strip()

        if value.startswith("{") and value.endswith("}"):
            value = value[1:-1]

            record["reason_codes"] = (
                [
                    item.strip()
                    for item in value.split(",")
                ]
                if value.strip()
                else []
            )

    return record

def update_approval_status(
    product_id: int,
    status: str,
) -> bool:
    if status not in {"approved", "rejected"}:
        raise ValueError(
            "Approval status must be 'approved' or 'rejected'"
        )

    engine = get_poc_engine()

    query = """
        UPDATE inventory_recommendations
        SET
            approval_status = :status,
            approval_updated_at = CURRENT_TIMESTAMP
        WHERE product_id = :product_id
    """

    with engine.begin() as connection:
        result = connection.execute(
            text(query),
            {
                "status": status,
                "product_id": product_id,
            },
        )

    return result.rowcount > 0

def create_draft_po_for_product(product_id: int) -> dict[str, Any]:
    engine = get_poc_engine()
    with engine.begin() as conn:
        # Check recommendation
        check_rec = text("""
            SELECT product_name, action, approval_status, suggested_purchase_qty
            FROM inventory_recommendations
            WHERE product_id = :product_id
        """)
        rec = conn.execute(check_rec, {"product_id": product_id}).first()
        if not rec:
            raise ValueError("Recommendation not found")
            
        product_name, action, approval_status, suggested_purchase_qty = rec
        
        if approval_status != "approved":
            raise ValueError("Recommendation must be approved")
        if action not in ("purchase", "review"):
            raise ValueError("Action must be 'purchase' or 'review'")
        if suggested_purchase_qty <= 0:
            raise ValueError("Suggested purchase quantity must be > 0")
            
        # Check existing PO
        check_po = text("SELECT po_number, status, quantity FROM draft_purchase_orders WHERE product_id = :product_id")
        po = conn.execute(check_po, {"product_id": product_id}).first()
        if po:
            return {
                "product_id": product_id,
                "product_name": product_name,
                "po_number": po[0],
                "quantity": po[2],
                "status": po[1]
            }
            
        # Create new
        insert_po = text("""
            INSERT INTO draft_purchase_orders (po_number, product_id, product_name, quantity, status)
            VALUES ('TEMP', :product_id, :product_name, :quantity, 'draft')
            RETURNING id, status
        """)
        res = conn.execute(insert_po, {
            "product_id": product_id,
            "product_name": product_name,
            "quantity": suggested_purchase_qty
        }).first()
        po_id = res[0]
        status = res[1]
        
        po_number = f"POC-PO-{po_id:03d}"
        conn.execute(text("UPDATE draft_purchase_orders SET po_number = :po_number WHERE id = :id"), {"po_number": po_number, "id": po_id})
        
        return {
            "product_id": product_id,
            "product_name": product_name,
            "po_number": po_number,
            "quantity": suggested_purchase_qty,
            "status": status
        }