import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.forecasting.engine_adapter import (
    EXISTING_ENGINE_ROOT,
    load_poc_environment,
)


def _get_odoo_engine():
    load_poc_environment()

    engine_root = str(EXISTING_ENGINE_ROOT)
    if engine_root not in sys.path:
        sys.path.insert(0, engine_root)

    from src.db import get_engine

    return get_engine()


def _get_product(connection, product_id: int) -> dict[str, Any] | None:
    row = connection.execute(
        text(
            """
            SELECT
                pp.id AS product_id,
                pp.product_tmpl_id AS product_template_id,
                pt.name->>'en_US' AS product_name,
                pt.main_product AS main_product_id,
                pt.is_main_similar,
                pt.active AS template_active,
                pp.active AS variant_active
            FROM product_product pp
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE pp.id = :product_id
            """
        ),
        {"product_id": product_id},
    ).mappings().first()
    return dict(row) if row else None


def _get_template(connection, template_id: int) -> dict[str, Any] | None:
    row = connection.execute(
        text(
            """
            SELECT
                id AS product_template_id,
                name->>'en_US' AS product_name,
                main_product AS main_product_id,
                is_main_similar,
                active AS template_active
            FROM product_template
            WHERE id = :template_id
            """
        ),
        {"template_id": template_id},
    ).mappings().first()
    return dict(row) if row else None


def _get_group_members(
    connection,
    main_product_id: int,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        text(
            """
            SELECT
                pp.id AS product_id,
                pp.product_tmpl_id AS product_template_id,
                pt.name->>'en_US' AS product_name,
                pt.is_main_similar,
                pt.main_product AS main_product_id,
                pt.active AS template_active,
                pp.active AS variant_active,
                COALESCE(stock.current_stock, 0) AS current_stock
            FROM product_template pt
            JOIN product_product pp ON pp.product_tmpl_id = pt.id
            LEFT JOIN (
                SELECT
                    sq.product_id,
                    SUM(sq.quantity) AS current_stock
                FROM stock_quant sq
                JOIN stock_location sl ON sl.id = sq.location_id
                WHERE sl.usage = 'internal'
                GROUP BY sq.product_id
            ) stock ON stock.product_id = pp.id
            WHERE pt.main_product = :main_product_id
            ORDER BY pt.id, pp.id
            """
        ),
        {"main_product_id": main_product_id},
    ).mappings().all()

    return [dict(row) for row in rows]


def _get_asymmetric_similarity_links(
    connection,
    product_template_ids: list[int],
) -> list[tuple[int, int]]:
    if not product_template_ids:
        return []

    rows = connection.execute(
        text(
            """
            SELECT src_id, dest_id
            FROM product_template_similar_rel
            WHERE src_id = ANY(:template_ids)
               OR dest_id = ANY(:template_ids)
            """
        ),
        {"template_ids": product_template_ids},
    ).mappings().all()

    links = {(row["src_id"], row["dest_id"]) for row in rows}
    asymmetric_links = []
    for source_id, target_id in links:
        if source_id == target_id or (target_id, source_id) in links:
            continue
        if source_id in product_template_ids or target_id in product_template_ids:
            asymmetric_links.append((source_id, target_id))

    return sorted(asymmetric_links)


def get_main_product(product_id: int) -> dict[str, Any] | None:
    engine = _get_odoo_engine()
    with engine.connect() as connection:
        product = _get_product(connection, product_id)
        if product is None:
            return None

        main_product_id = product["main_product_id"]
        if main_product_id is None:
            main_product_id = product["product_template_id"]

        return _get_template(connection, int(main_product_id))


def get_group_members(main_product_id: int) -> list[dict[str, Any]]:
    engine = _get_odoo_engine()
    with engine.connect() as connection:
        return _get_group_members(connection, main_product_id)


def _validate_group(
    main_product_id: int,
    requested_product_id: int | None = None,
) -> tuple[list[str], list[str]]:
    engine = _get_odoo_engine()
    with engine.connect() as connection:
        main_product = _get_template(connection, main_product_id)
        members = _get_group_members(connection, main_product_id)
        member_template_ids = sorted(
            {member["product_template_id"] for member in members}
            | {main_product_id}
        )
        asymmetric_links = _get_asymmetric_similarity_links(
            connection,
            member_template_ids,
        )
        requested_product = (
            _get_product(connection, requested_product_id)
            if requested_product_id is not None
            else None
        )

    issues: list[str] = []
    warnings: list[str] = []
    if main_product is None:
        issues.append(f"Main product template {main_product_id} does not exist.")

    if requested_product_id is not None and requested_product is None:
        issues.append(f"Requested product {requested_product_id} does not exist.")
    elif requested_product is not None and requested_product["main_product_id"] is None:
        issues.append(
            "Requested product template "
            f"{requested_product['product_template_id']} has main_product NULL."
        )

    if main_product is not None:
        assigned_main_id = main_product["main_product_id"]
        if assigned_main_id is not None and assigned_main_id != main_product_id:
            issues.append(
                f"Main product template {main_product_id} points to another "
                f"main_product template ({assigned_main_id})."
            )
        if not main_product["template_active"]:
            issues.append(f"Main product template {main_product_id} is inactive.")

    template_ids = [member["product_template_id"] for member in members]
    if main_product_id not in template_ids:
        issues.append(
            f"Main product template {main_product_id} is not included in its own group."
        )

    product_ids = [member["product_id"] for member in members]
    if len(product_ids) != len(set(product_ids)):
        issues.append("The group contains duplicate product members.")

    if any(member["main_product_id"] != main_product_id for member in members):
        issues.append("Group member main_product assignments disagree.")

    main_similar_templates = {
        member["product_template_id"]
        for member in members
        if member["is_main_similar"]
    }
    if len(main_similar_templates) > 1:
        issues.append(
            "Multiple group members have is_main_similar=True: "
            + ", ".join(str(value) for value in sorted(main_similar_templates))
            + "."
        )
    elif not main_similar_templates:
        issues.append("No group member has is_main_similar=True.")

    missing_main_similar = sorted(
        {
            member["product_template_id"]
            for member in members
            if member["product_template_id"] != main_product_id
            and member["is_main_similar"] is None
        }
    )
    if missing_main_similar:
        warnings.append(
            "Non-main group members have NULL is_main_similar: "
            + ", ".join(str(value) for value in missing_main_similar)
            + "."
        )

    inactive_ids = sorted(
        member["product_id"]
        for member in members
        if not member["template_active"] or not member["variant_active"]
    )
    if inactive_ids:
        issues.append(
            "Inactive group product variants found: "
            + ", ".join(str(value) for value in inactive_ids)
            + "."
        )

    if asymmetric_links:
        links = ", ".join(
            f"{source_id}->{target_id}"
            for source_id, target_id in asymmetric_links
        )
        issues.append(
            "One-way similar_product_ids relations found "
            f"(not used for group membership): {links}."
        )

    return issues, warnings


def validate_group(
    main_product_id: int,
    requested_product_id: int | None = None,
) -> list[str]:
    issues, _ = _validate_group(main_product_id, requested_product_id)
    return issues


def get_product_group(product_id: int) -> dict[str, Any] | None:
    engine = _get_odoo_engine()
    with engine.connect() as connection:
        product = _get_product(connection, product_id)
        if product is None:
            return None

        stored_main_product_id = product["main_product_id"]
        main_product_id = stored_main_product_id
        if main_product_id is None:
            main_product_id = product["product_template_id"]

        main_product = _get_template(connection, int(main_product_id))
        members = _get_group_members(connection, int(main_product_id))

    validation_issues, validation_warnings = _validate_group(
        int(main_product_id),
        requested_product_id=product_id,
    )

    if stored_main_product_id is None:
        validation_issues.insert(
            0,
            "The requested product has no stored main_product assignment; "
            "its own template is used only as a lookup anchor.",
        )

    return {
        "product_id": product["product_id"],
        "template_id": product["product_template_id"],
        "product_name": product["product_name"],
        "main_product_id": main_product_id,
        "main_product_template_id": main_product_id,
        "main_product_name": (
            main_product["product_name"] if main_product is not None else None
        ),
        "is_main_similar": product["is_main_similar"],
        "group_members": [
            {
                "product_id": member["product_id"],
                "template_id": member["product_template_id"],
                "product_name": member["product_name"],
                "is_main_similar": member["is_main_similar"],
                "main_product_id": member["main_product_id"],
                "main_product_template_id": member["main_product_id"],
                "current_stock": float(member["current_stock"]),
            }
            for member in members
        ],
        "template_count": len(
            {member["product_template_id"] for member in members}
        ),
        "variant_count": len(members),
        "group_size": len(members),
        "group_valid": not validation_issues,
        "validation_issues": validation_issues,
        "validation_warnings": validation_warnings,
    }