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

    existing_approvals = {}
    with engine.connect() as conn:
        try:
            rows = conn.execute(
                text(
                    "SELECT product_id, approval_status, approval_updated_at "
                    "FROM inventory_recommendations"
                )
            ).mappings().all()
            for r in rows:
                if r["product_id"] is not None:
                    existing_approvals[int(r["product_id"])] = (
                        r["approval_status"],
                        r["approval_updated_at"],
                    )
        except Exception:
            existing_approvals = {}

    if "approval_status" not in df.columns:
        df["approval_status"] = df["product_id"].map(
            lambda pid: (
                existing_approvals.get(int(pid), ("pending", None))[0]
                if pd.notna(pid) and int(pid) in existing_approvals
                else "pending"
            )
        )
    if "approval_updated_at" not in df.columns:
        df["approval_updated_at"] = df["product_id"].map(
            lambda pid: (
                existing_approvals.get(int(pid), ("pending", None))[1]
                if pd.notna(pid) and int(pid) in existing_approvals
                else None
            )
        )

    df.to_sql(
        "inventory_recommendations",
        engine,
        if_exists="replace",
        index=False,
    )

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE inventory_recommendations
                ADD COLUMN IF NOT EXISTS approval_status VARCHAR(20)
                    NOT NULL DEFAULT 'pending';

                ALTER TABLE inventory_recommendations
                ADD COLUMN IF NOT EXISTS approval_updated_at TIMESTAMP NULL;
                """
            )
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

    try:
        from app.odoo.product_group_service import _get_odoo_engine
        odoo_engine = _get_odoo_engine()
        with odoo_engine.connect() as odoo_conn:
            stock_rows = odoo_conn.execute(
                text(
                    """
                    SELECT
                        sq.product_id,
                        SUM(CASE WHEN slt.is_cut_piece IS TRUE THEN sq.quantity ELSE 0 END) AS cut_piece_qty,
                        SUM(CASE WHEN slt.is_cut_piece IS NOT TRUE THEN sq.quantity ELSE 0 END) AS usable_qty
                    FROM stock_quant sq
                    JOIN stock_location sl ON sl.id = sq.location_id
                    LEFT JOIN stock_lot slt ON slt.id = sq.lot_id
                    WHERE sl.usage = :usage
                    GROUP BY sq.product_id
                    """
                ),
                {"usage": "internal"},
            ).mappings().all()
            stock_map = {
                row["product_id"]: {
                    "cut_piece_qty": float(row["cut_piece_qty"] or 0.0),
                    "usable_qty": float(row["usable_qty"] or 0.0),
                }
                for row in stock_rows
            }
    except Exception:
        stock_map = {}

    for record in records:
        product_stock = stock_map.get(record["product_id"])
        if product_stock:
            record["usable_qty"] = product_stock["usable_qty"]
            record["cut_piece_qty"] = product_stock["cut_piece_qty"]
        else:
            record["usable_qty"] = float(record.get("current_stock") or 0.0)
            record["cut_piece_qty"] = 0.0
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


def get_all_draft_pos() -> list[dict[str, Any]]:
    engine = get_poc_engine()
    query = """
        SELECT
            id,
            po_number,
            product_id,
            product_name,
            quantity,
            status,
            created_at
        FROM draft_purchase_orders
        ORDER BY id DESC;
    """
    df = pd.read_sql(query, engine)
    if df.empty:
        return []
    df = df.astype(object).where(pd.notna(df), None)
    return df.to_dict(orient="records")


def create_group_po_for_template(
    main_product_template_id: int,
    quantity: float,
) -> dict[str, Any]:
    from app.odoo.product_group_service import get_group_members, get_product_group

    if quantity <= 0:
        raise ValueError("Quantity must be a positive number")

    members = get_group_members(main_product_template_id)
    if not members:
        raise ValueError(f"No group members found for template {main_product_template_id}")

    canonical_member = next(
        (m for m in members if m["product_template_id"] == main_product_template_id or m["is_main_similar"]),
        members[0],
    )
    product_id = int(canonical_member["product_id"])
    product_name = str(canonical_member["product_name"] or f"Product {product_id}")

    # Validate group
    group = get_product_group(product_id)
    if not group or not group.get("group_valid", True):
        issues = group.get("validation_issues", []) if group else []
        if issues:
            raise ValueError(f"Cannot create PO for invalid group: {'; '.join(issues)}")

    engine = get_poc_engine()
    with engine.begin() as conn:
        # Check if draft PO exists for this canonical product
        check_po = text("""
            SELECT id, po_number, status, quantity, created_at
            FROM draft_purchase_orders
            WHERE product_id = :product_id
            ORDER BY id DESC LIMIT 1
        """)
        existing = conn.execute(check_po, {"product_id": product_id}).mappings().first()
        if existing:
            conn.execute(
                text("""
                    UPDATE draft_purchase_orders
                    SET quantity = :quantity, status = 'confirmed', created_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {"quantity": round(quantity, 1), "id": existing["id"]},
            )
            conn.execute(
                text("""
                    UPDATE group_inventory_recommendations
                    SET approval_status = 'approved', approval_updated_at = CURRENT_TIMESTAMP
                    WHERE main_product_template_id = :template_id
                """),
                {"template_id": main_product_template_id},
            )
            return {
                "po_number": existing["po_number"],
                "product_id": product_id,
                "product_name": product_name,
                "quantity": quantity,
                "status": "confirmed",
                "created_at": existing["created_at"],
            }

        insert_po = text("""
            INSERT INTO draft_purchase_orders (po_number, product_id, product_name, quantity, status, created_at)
            VALUES ('TEMP', :product_id, :product_name, :quantity, 'confirmed', CURRENT_TIMESTAMP)
            RETURNING id, status, created_at
        """)
        res = conn.execute(insert_po, {
            "product_id": product_id,
            "product_name": product_name,
            "quantity": round(quantity, 1),
        }).first()
        po_id = res[0]
        status = res[1]
        created_at = res[2]

        po_number = f"POC-PO-{po_id:03d}"
        conn.execute(
            text("UPDATE draft_purchase_orders SET po_number = :po_number WHERE id = :id"),
            {"po_number": po_number, "id": po_id},
        )

        conn.execute(
            text("""
                UPDATE group_inventory_recommendations
                SET approval_status = 'approved', approval_updated_at = CURRENT_TIMESTAMP
                WHERE main_product_template_id = :template_id
            """),
            {"template_id": main_product_template_id},
        )

        return {
            "po_number": po_number,
            "product_id": product_id,
            "product_name": product_name,
            "quantity": quantity,
            "status": status,
            "created_at": created_at,
        }
