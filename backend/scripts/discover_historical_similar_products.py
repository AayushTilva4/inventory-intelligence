import os
import re
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = BACKEND_ROOT / "data"
sys.path.insert(0, str(BACKEND_ROOT))

from app.forecasting.engine_adapter import load_poc_environment


PRODUCTS_SQL = """
    SELECT
        pp.id AS product_id,
        pt.id AS product_template_id,
        pt.name->>'en_US' AS product_name,
        pp.default_code AS variant_reference,
        pt.default_code AS template_reference,
        pp.barcode,
        pt.create_date AS create_date,
        pp.active AS variant_active,
        pt.active AS template_active,
        pt.categ_id AS category_id,
        pc.complete_name AS category,
        pt.brand_id,
        pb.name AS brand,
        pt.quality,
        pt.composition,
        pt.gsm,
        pt.martindale,
        pt.washing_instruction,
        pt.special_treatment,
        pt.vendor_reference,
        pt.width,
        pt.product_app_description,
        pt.main_product,
        pt.is_main_similar,
        pt.is_self_main,
        pt.is_catalogue,
        pt.description->>'en_US' AS description,
        pt.description_sale->>'en_US' AS description_sale,
        pt.description_purchase->>'en_US' AS description_purchase
    FROM product_product pp
    JOIN product_template pt ON pt.id = pp.product_tmpl_id
    LEFT JOIN product_category pc ON pc.id = pt.categ_id
    LEFT JOIN product_brand pb ON pb.id = pt.brand_id
"""

MONTHLY_SALES_SQL = """
    SELECT
        pp.product_tmpl_id AS product_template_id,
        date_trunc('month', so.date_order)::date AS sale_month,
        SUM(sol.product_uom_qty)::numeric AS sales_quantity
    FROM sale_order so
    JOIN sale_order_line sol ON sol.order_id = so.id
    JOIN product_product pp ON pp.id = sol.product_id
    WHERE so.state = 'sale'
      AND sol.product_id IS NOT NULL
      AND COALESCE(sol.display_type, '') = ''
      AND NOT COALESCE(sol.is_delivery, false)
    GROUP BY pp.product_tmpl_id, date_trunc('month', so.date_order)::date
    ORDER BY pp.product_tmpl_id, sale_month
"""

SALES_SUMMARY_SQL = """
    SELECT
        pp.product_tmpl_id AS product_template_id,
        MIN(so.date_order)::date AS first_sale_date,
        MAX(so.date_order)::date AS last_sale_date,
        COUNT(DISTINCT date_trunc('month', so.date_order)) AS selling_months,
        SUM(sol.product_uom_qty)::numeric AS sales_quantity,
        COUNT(*) AS sale_lines
    FROM sale_order so
    JOIN sale_order_line sol ON sol.order_id = so.id
    JOIN product_product pp ON pp.id = sol.product_id
    WHERE so.state = 'sale'
      AND sol.product_id IS NOT NULL
      AND COALESCE(sol.display_type, '') = ''
      AND NOT COALESCE(sol.is_delivery, false)
    GROUP BY pp.product_tmpl_id
"""

LINKS_SQL = """
    WITH raw_links AS (
        SELECT src_id AS a, dest_id AS b, 'product_template_similar_rel' AS source
        FROM product_template_similar_rel
        UNION ALL
        SELECT similar1, similar2, 'all_similar_products'
        FROM all_similar_products
        UNION ALL
        SELECT id, main_product, 'product_template.main_product'
        FROM product_template
        WHERE main_product IS NOT NULL AND main_product <> id
    ), directed AS (
        SELECT
            CASE WHEN newer.create_date > older.create_date THEN newer.id ELSE older.id END AS new_id,
            CASE WHEN newer.create_date > older.create_date THEN older.id ELSE newer.id END AS old_id,
            raw_links.source
        FROM raw_links
        JOIN product_template newer ON newer.id = raw_links.a
        JOIN product_template older ON older.id = raw_links.b
        WHERE raw_links.a <> raw_links.b
          AND newer.create_date <> older.create_date
    ), links AS (
        SELECT new_id, old_id, string_agg(DISTINCT source, ', ' ORDER BY source) AS link_sources
        FROM directed
        GROUP BY new_id, old_id
    ), latest AS (
        SELECT MAX(sale_month) AS latest_sale_month FROM (
            SELECT date_trunc('month', so.date_order)::date AS sale_month
            FROM sale_order so
            JOIN sale_order_line sol ON sol.order_id = so.id
            WHERE so.state = 'sale'
              AND sol.product_id IS NOT NULL
              AND COALESCE(sol.display_type, '') = ''
              AND NOT COALESCE(sol.is_delivery, false)
        ) monthly
    )
    SELECT
        new_pp.id AS new_product_id,
        new_pt.id AS new_product_template_id,
        new_pt.name->>'en_US' AS new_product_name,
        new_pp.default_code AS new_product_reference,
        new_pt.create_date::date AS new_product_create_date,
        new_pt.active AS new_product_active,
        new_cat.complete_name AS new_category,
        new_pt.brand_id AS new_brand_id,
        new_brand.name AS new_brand,
        new_pt.quality AS new_quality,
        new_pt.composition AS new_composition,
        new_pt.gsm AS new_gsm,
        new_pt.martindale AS new_martindale,
        new_pt.main_product AS new_main_product_id,
        old_pp.id AS old_product_id,
        old_pt.id AS old_product_template_id,
        old_pt.name->>'en_US' AS old_product_name,
        old_pp.default_code AS old_product_reference,
        old_pt.create_date::date AS old_product_create_date,
        old_pt.active AS old_product_active,
        old_cat.complete_name AS old_category,
        old_pt.brand_id AS old_brand_id,
        old_brand.name AS old_brand,
        old_pt.quality AS old_quality,
        old_pt.composition AS old_composition,
        old_pt.gsm AS old_gsm,
        old_pt.martindale AS old_martindale,
        links.link_sources,
        summary.first_sale_date AS old_first_sale_date,
        summary.last_sale_date AS old_last_sale_date,
        summary.selling_months AS old_selling_months,
        summary.sales_quantity AS old_sales_quantity,
        summary.sale_lines AS old_sale_lines,
        new_summary.first_sale_date AS new_first_sale_date,
        new_summary.last_sale_date AS new_last_sale_date,
        new_summary.selling_months AS new_selling_months,
        latest.latest_sale_month
    FROM links
    JOIN product_template new_pt ON new_pt.id = links.new_id
    JOIN product_product new_pp ON new_pp.product_tmpl_id = new_pt.id
    JOIN product_template old_pt ON old_pt.id = links.old_id
    JOIN product_product old_pp ON old_pp.product_tmpl_id = old_pt.id
    LEFT JOIN product_category new_cat ON new_cat.id = new_pt.categ_id
    LEFT JOIN product_category old_cat ON old_cat.id = old_pt.categ_id
    LEFT JOIN product_brand new_brand ON new_brand.id = new_pt.brand_id
    LEFT JOIN product_brand old_brand ON old_brand.id = old_pt.brand_id
    LEFT JOIN ({sales_summary}) summary ON summary.product_template_id = old_pt.id
    LEFT JOIN ({sales_summary}) new_summary ON new_summary.product_template_id = new_pt.id
    CROSS JOIN latest
    WHERE new_pt.active
      AND new_pt.create_date >= latest.latest_sale_month - INTERVAL '12 months'
      AND old_pt.create_date < new_pt.create_date
    ORDER BY new_pt.create_date DESC, new_pt.id, old_pt.id
""".format(sales_summary=SALES_SUMMARY_SQL)

NAME_FAMILY_SQL = """
    WITH latest AS (
        SELECT date_trunc('month', MAX(so.date_order))::date AS latest_sale_month
        FROM sale_order so
        JOIN sale_order_line sol ON sol.order_id = so.id
        WHERE so.state = 'sale' AND sol.product_id IS NOT NULL
    ), products AS (
        SELECT
            pt.id AS product_template_id,
            pt.name->>'en_US' AS product_name,
            pp.id AS product_id,
            pt.create_date::date AS create_date,
            pt.active,
            pt.categ_id AS category_id,
            pc.complete_name AS category,
            CASE
                WHEN pt.name->>'en_US' ~ '^[0-9][0-9][0-9]-'
                    THEN substring(pt.name->>'en_US' FROM '^([0-9][0-9][0-9])-')
                WHEN pt.name->>'en_US' ~ '^[A-Za-z][A-Za-z][A-Za-z][A-Za-z]+'
                    THEN lower(substring(pt.name->>'en_US' FROM '^([A-Za-z]+)'))
                ELSE NULL
            END AS name_family
        FROM product_template pt
        JOIN product_product pp ON pp.product_tmpl_id = pt.id
        LEFT JOIN product_category pc ON pc.id = pt.categ_id
    ), summary AS ({sales_summary})
    SELECT
        newer.product_id AS new_product_id,
        newer.product_name AS new_product_name,
        newer.create_date AS new_product_create_date,
        newer.category AS new_category,
        older.product_id AS old_product_id,
        older.product_name AS old_product_name,
        older.create_date AS old_product_create_date,
        older.category AS old_category,
        newer.name_family,
        summary.first_sale_date AS old_first_sale_date,
        summary.last_sale_date AS old_last_sale_date,
        summary.selling_months AS old_selling_months,
        summary.sales_quantity AS old_sales_quantity,
        summary.sale_lines AS old_sale_lines
    FROM products newer
    CROSS JOIN latest
    JOIN products older
      ON older.active
     AND older.create_date < newer.create_date
     AND older.category_id = newer.category_id
     AND older.name_family = newer.name_family
     AND older.product_template_id <> newer.product_template_id
    LEFT JOIN summary ON summary.product_template_id = older.product_template_id
    WHERE newer.active
      AND newer.name_family IS NOT NULL
      AND newer.create_date >= latest.latest_sale_month - INTERVAL '12 months'
    ORDER BY newer.create_date DESC, newer.product_id, older.product_id
""".format(sales_summary=SALES_SUMMARY_SQL)


def _records(connection, query):
    return pd.DataFrame(connection.execute(text(query)).mappings().all())


def _name_family(name):
    if not isinstance(name, str):
        return ""
    code = re.match(r"^(\d{3})-", name.strip())
    if code:
        return code.group(1)
    word = re.match(r"^([A-Za-z]+)", name.strip())
    return word.group(1).casefold() if word else ""


def _candidate_evidence(row):
    fields = [row["link_sources"]]
    notes = ["Recorded Odoo similarity/main-product relationship"]
    if row["new_category"] and row["new_category"] == row["old_category"]:
        fields.append("category")
        notes.append("same category")
    elif row["new_category"] and row["old_category"]:
        notes.append("category differs")
    for field, label in (
        ("brand", "brand"),
        ("quality", "quality"),
        ("composition", "composition"),
        ("gsm", "GSM"),
        ("martindale", "Martindale"),
    ):
        new_value = row.get(f"new_{field}")
        old_value = row.get(f"old_{field}")
        if new_value and old_value:
            if str(new_value).strip().casefold() == str(old_value).strip().casefold():
                fields.append(label)
                notes.append(f"same {label}")
            else:
                notes.append(f"{label} differs")
    if _name_family(row["new_product_name"]) == _name_family(row["old_product_name"]):
        fields.append("name family")
        notes.append("same name family")
    if pd.notna(row["old_selling_months"]):
        notes.append(
            f"old product sold in {int(row['old_selling_months'])} distinct months"
        )
    else:
        notes.append("no qualifying historical sale lines found for old product")
    return "; ".join(notes), "; ".join(dict.fromkeys(fields))


def _fmt(value):
    if pd.isna(value):
        return "n/a"
    if isinstance(value, (int, float)):
        return f"{value:,.1f}" if isinstance(value, float) else f"{value:,}"
    return str(value)


def _markdown_table(frame, columns, headers):
    rows = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for values in frame[columns].itertuples(index=False, name=None):
        escaped = [str(value).replace("|", "\\|").replace("\n", " ") for value in values]
        rows.append("| " + " | ".join(escaped) + " |")
    return "\n".join(rows)


def main():
    load_poc_environment()
    db_url = URL.create(
        "postgresql+psycopg2",
        username=os.environ["ODOO_DB_USER"],
        password=os.environ["ODOO_DB_PASSWORD"],
        host=os.environ["ODOO_DB_HOST"],
        port=int(os.environ["ODOO_DB_PORT"]),
        database=os.environ["ODOO_DB_NAME"],
    )
    engine = create_engine(db_url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            database_name = connection.execute(text("SELECT current_database()")).scalar_one()
            products = _records(connection, PRODUCTS_SQL)
            monthly = _records(connection, MONTHLY_SALES_SQL)
            candidates = _records(connection, LINKS_SQL)
            name_family_candidates = _records(connection, NAME_FAMILY_SQL)
            transaction.rollback()
    finally:
        engine.dispose()

    products["create_date"] = pd.to_datetime(products["create_date"])
    monthly["sale_month"] = pd.to_datetime(monthly["sale_month"])
    candidates["new_product_create_date"] = pd.to_datetime(candidates["new_product_create_date"])
    candidates["old_product_create_date"] = pd.to_datetime(candidates["old_product_create_date"])
    candidates["latest_sale_month"] = pd.to_datetime(candidates["latest_sale_month"])
    name_family_candidates["new_product_create_date"] = pd.to_datetime(
        name_family_candidates["new_product_create_date"]
    )
    name_family_candidates["old_product_create_date"] = pd.to_datetime(
        name_family_candidates["old_product_create_date"]
    )
    for date_column in ("old_first_sale_date", "old_last_sale_date", "new_first_sale_date", "new_last_sale_date"):
        candidates[date_column] = pd.to_datetime(candidates[date_column])

    latest_month = monthly["sale_month"].max()
    cutoff = latest_month - pd.DateOffset(months=12)
    candidates["matching_evidence"], candidates["matching_fields"] = zip(
        *candidates.apply(_candidate_evidence, axis=1)
    )
    candidates["evidence_tier"] = candidates["old_selling_months"].apply(
        lambda months: "strong signal" if pd.notna(months) and months >= 6 else "ambiguous"
    )

    candidate_columns = [
        "new_product_id", "new_product_name", "new_product_reference",
        "old_product_id", "old_product_name", "old_product_reference",
        "new_product_create_date", "old_product_create_date", "new_category",
        "matching_evidence", "matching_fields", "evidence_tier", "link_sources",
        "old_first_sale_date", "old_last_sale_date", "old_selling_months",
        "old_sales_quantity", "old_sale_lines", "new_first_sale_date",
        "new_last_sale_date", "new_selling_months", "old_product_active",
        "old_category", "new_brand", "old_brand", "new_quality", "old_quality",
        "new_composition", "old_composition", "new_gsm", "old_gsm",
        "new_martindale", "old_martindale",
    ]
    candidates[candidate_columns].to_csv(
        DATA_ROOT / "historical_similar_product_candidates.csv", index=False
    )
    name_family_candidates["candidate_evidence"] = (
        "same parsed name family and category; heuristic only, not an Odoo lineage link"
    )
    name_family_candidates.to_csv(
        DATA_ROOT / "historical_similar_product_name_candidates.csv", index=False
    )

    strong = candidates[candidates["evidence_tier"] == "strong signal"].copy()
    strong_old = strong.drop_duplicates("old_product_template_id")
    old_to_new = strong.groupby("old_product_template_id").agg(
        analogue_new_product_ids=("new_product_id", lambda ids: ";".join(map(str, sorted(set(ids))))),
        analogue_new_product_names=("new_product_name", lambda names: "; ".join(sorted(set(names)))),
    )
    lifecycle_rows = []
    for analogue in strong_old.itertuples(index=False):
        first_month = monthly.loc[
            monthly["product_template_id"] == analogue.old_product_template_id,
            "sale_month",
        ].min()
        month_frame = monthly.loc[
            monthly["product_template_id"] == analogue.old_product_template_id,
            ["sale_month", "sales_quantity"],
        ].set_index("sale_month")
        full_range = pd.date_range(first_month, latest_month, freq="MS")
        month_frame = month_frame.reindex(full_range, fill_value=0)
        new_info = old_to_new.loc[analogue.old_product_template_id]
        for month_index, (month, sale_row) in enumerate(month_frame.iterrows(), start=1):
            lifecycle_rows.append(
                {
                    "new_product_ids": new_info["analogue_new_product_ids"],
                    "new_product_names": new_info["analogue_new_product_names"],
                    "old_product_id": analogue.old_product_id,
                    "old_product_name": analogue.old_product_name,
                    "old_product_first_sale_date": analogue.old_first_sale_date.date(),
                    "month_since_launch_proxy": month_index,
                    "sale_month": month.date(),
                    "sales_quantity": float(sale_row["sales_quantity"]),
                }
            )
    lifecycle = pd.DataFrame(lifecycle_rows)
    lifecycle.to_csv(DATA_ROOT / "historical_similar_product_lifecycle.csv", index=False)
    poc_lifecycle_sample = lifecycle[lifecycle["old_product_id"] == 54].head(12)

    active_products = products[products["template_active"]]
    sales_by_product = monthly.groupby("product_template_id").agg(
        selling_months=("sales_quantity", lambda quantities: int((quantities > 0).sum())),
        sales_quantity=("sales_quantity", "sum"),
    )
    active_with_sales = active_products["product_template_id"].isin(sales_by_product.index).sum()
    groups = candidates.groupby("new_product_template_id").agg(
        analogue_count=("old_product_template_id", "nunique"),
        selling_analogue_count=("old_selling_months", lambda months: int(months.notna().sum())),
    )
    unique_old = candidates.drop_duplicates("old_product_template_id")
    old_with_sales = unique_old[unique_old["old_selling_months"].notna()]
    tail_months = (
        (latest_month.year - strong_old["old_last_sale_date"].dt.year) * 12
        + latest_month.month - strong_old["old_last_sale_date"].dt.month
    )

    poc = pd.read_csv(DATA_ROOT / "poc_forecasts.csv")
    product_by_id = products.set_index("product_id")
    poc_rows = []
    for record in poc.to_dict("records"):
        product = product_by_id.loc[int(record["product_id"])]
        product_template_id = int(product["product_template_id"])
        direct = candidates[candidates["new_product_template_id"] == product_template_id]
        possible = []
        family = _name_family(product["product_name"])
        same_family = products[
            (products["product_template_id"] != product_template_id)
            & (products["create_date"] < product["create_date"])
            & (products["category_id"] == product["category_id"])
            & (products["product_name"].map(_name_family) == family)
        ]
        for old in same_family.itertuples(index=False):
            history = sales_by_product.loc[old.product_template_id] if old.product_template_id in sales_by_product.index else None
            if history is not None and history["selling_months"] > 0:
                possible.append(
                    f"{old.product_name} (ID {old.product_id}, {history['selling_months']} selling months; weak name/category match)"
                )
        for link in direct.itertuples(index=False):
            possible.append(
                f"{link.old_product_name} (ID {link.old_product_id}, "
                f"{_fmt(link.old_selling_months)} selling months; recorded link)"
            )
        poc_rows.append(
            {
                "scenario": record["scenario"],
                "product_id": int(record["product_id"]),
                "product_name": product["product_name"],
                "forecast_status": record["status"],
                "poc_history_months": record.get("months_available"),
                "possible_historical_analogues": "; ".join(dict.fromkeys(possible)),
            }
        )
    poc_report = pd.DataFrame(poc_rows)

    latest_sale_date = monthly["sale_month"].max().date()
    relationship_count = len(candidates)
    active_new_count = len(active_products[active_products["create_date"] >= cutoff])
    with_any_candidate = candidates["new_product_template_id"].nunique()
    with_sales_analogue = candidates.loc[
        candidates["old_selling_months"].notna(), "new_product_template_id"
    ].nunique()
    strong_relationships = int((candidates["evidence_tier"] == "strong signal").sum())
    ambiguous_relationships = relationship_count - strong_relationships
    family_with_sales = name_family_candidates[
        name_family_candidates["old_selling_months"].notna()
    ]

    top_examples = candidates[candidates["evidence_tier"] == "strong signal"].sort_values(
        ["old_selling_months", "old_sales_quantity"], ascending=False
    ).head(20).copy()
    examples = pd.DataFrame(
        {
            "New product": top_examples.apply(lambda row: f"{row.new_product_name} (ID {row.new_product_id})", axis=1),
            "Old analogue": top_examples.apply(lambda row: f"{row.old_product_name} (ID {row.old_product_id})", axis=1),
            "Evidence": top_examples["matching_evidence"],
            "Old history": top_examples.apply(
                lambda row: f"{int(row.old_selling_months)} selling months; {row.old_first_sale_date.date()} to {row.old_last_sale_date.date()}; {_fmt(float(row.old_sales_quantity))} units",
                axis=1,
            ),
            "New history": top_examples.apply(
                lambda row: f"{_fmt(row.new_selling_months)} selling months; last sale {_fmt(row.new_last_sale_date.date() if pd.notna(row.new_last_sale_date) else pd.NA)}",
                axis=1,
            ),
        }
    )
    ambiguous_examples = candidates[
        candidates["evidence_tier"] == "ambiguous"
    ].sort_values(["old_selling_months", "new_product_create_date"], ascending=[True, False]).head(5)
    ambiguous_table = pd.DataFrame(
        {
            "New product": ambiguous_examples.apply(lambda row: f"{row.new_product_name} (ID {row.new_product_id})", axis=1),
            "Older linked product": ambiguous_examples.apply(lambda row: f"{row.old_product_name} (ID {row.old_product_id})", axis=1),
            "Observed evidence": ambiguous_examples.apply(
                lambda row: f"{row.link_sources}; category {row.new_category or 'n/a'} / {row.old_category or 'n/a'}; old history {_fmt(row.old_selling_months)} selling months",
                axis=1,
            ),
        }
    )

    poc_cold = poc_report[poc_report["forecast_status"].astype(str).str.contains("cold_start")]
    report = f"""# Historical Similar Product Discovery

Read-only snapshot of Odoo database `{database_name}`. Latest qualifying sale month: **{latest_sale_date}**. Recent/new means an active product template created in the 12 months ending at the latest sales month (cutoff {cutoff.date()}). The catalog's `create_date` and first sale are proxies; neither proves the real commercial launch date.

## Findings

- Active product templates/variants: **{len(active_products):,}** of {len(products):,} total. This database currently has exactly one product variant per template.
- Active products with at least one qualifying historical sale: **{active_with_sales:,}**. Across the catalog, qualifying sales span {monthly['sale_month'].min().date()} through {latest_sale_date}.
- Active new products in the 12-month window: **{active_new_count:,}**.
- Recorded newer-to-older candidate relationships: **{relationship_count:,}** across **{with_any_candidate:,}** new products. **{with_sales_analogue:,}** new products have at least one old linked product with sales.
- Strong-signal relationships: **{strong_relationships:,}**; ambiguous/weak-history relationships: **{ambiguous_relationships:,}**. Strong signal means a recorded Odoo relationship plus at least six distinct months with sales for the older product. It is not proof of equivalence.
- Separate name-family heuristic: **{len(name_family_candidates):,}** same parsed name-family/same-category pairs across **{name_family_candidates['new_product_id'].nunique():,}** new products; **{len(family_with_sales):,}** pairs have old-product sales and **{int((family_with_sales['old_selling_months'] >= 6).sum()):,}** have six or more selling months. These are weak, broad family leads and are not included in the primary 289 Odoo-linked relationship count.
- New products with 2+ analogues: **{int((groups['analogue_count'] >= 2).sum()):,}**; with 3+: **{int((groups['analogue_count'] >= 3).sum()):,}**. With 2+ selling analogues: **{int((groups['selling_analogue_count'] >= 2).sum()):,}**; with 3+: **{int((groups['selling_analogue_count'] >= 3).sum()):,}**.
- Unique older linked products: **{len(unique_old):,}**, of which **{len(old_with_sales):,}** have recorded sales: **{float(old_with_sales['old_sales_quantity'].sum()):,.2f}** units over **{int(old_with_sales['old_sale_lines'].sum()):,}** order lines and **{int(old_with_sales['old_selling_months'].sum()):,}** product-months. These are totals across distinct analogues, not links.
- Strong-signal unique older products: **{len(strong_old):,}**, with **{float(strong_old['old_sales_quantity'].sum()):,.2f}** units. Median elapsed months since last sale: **{int(tail_months.median())}**; **{int((tail_months >= 6).sum())}** have no observed sale for at least six months and **{int((tail_months >= 12).sum())}** for at least twelve months.

## Real Strong-Signal Examples

Selected by older-product selling-month count and quantity. Evidence describes stored links and observed metadata; category differences are retained rather than hidden.

{_markdown_table(examples, list(examples.columns), list(examples.columns))}

## Ambiguous Cases

These have a stored relationship but do not meet the six-selling-month threshold. Treat them as candidates requiring review, not analogues suitable for demand transfer.

{_markdown_table(ambiguous_table, list(ambiguous_table.columns), list(ambiguous_table.columns))}

## POC Cold Starts

The two POC forecasts marked cold-start are **{len(poc_cold)}** products. The table reports Odoo recorded links and same-name-family/same-category matches separately as weak discovery leads.

{_markdown_table(poc_report, list(poc_report.columns), list(poc_report.columns))}

Assessment: `433-47` has a recorded link to `351-42`; the latter has 14 selling months, 333 units, and last sold 2026-06-09. The new product itself has one sale month in the POC. `Buckby Latte - AW` has same-family/same-category peers `Buckby Silver - AW` and `Buckby Graphite - AW`, but each older peer has only one sale month (6 and 3 units respectively). That is weak evidence, not a usable demand history.

## Lifecycle Check

The lifecycle CSV contains zero-filled monthly quantities from each strong-signal older product's first observed sale month through {latest_sale_date}. `month_since_launch_proxy` is one-based from first sale month, not verified launch. The data supports lifecycle-aligned exploration. Product creation dates are unreliable launch labels: many catalog products share bulk-import dates, and some first sales occur months later.

No-sale tails can be measured but are not necessarily true zero demand: lack of sales may reflect stockouts, catalog withdrawal, or missing data. Current Odoo `active` flags do not mean the product was still selling; all older products in this recent candidate set are marked active, including those with long no-sale tails.

Example for the POC recorded link `433-47 → 351-42` (month 1 is first observed sale month):

{_markdown_table(poc_lifecycle_sample, ['month_since_launch_proxy', 'sale_month', 'sales_quantity'], ['month_since_launch', 'sale_month', 'sales_quantity'])}

The full sample through the latest month, including zero-sale tail months, is in the lifecycle CSV.

## Available Similarity Fields

`product_template` provides `name` (JSONB), `default_code`, `description`, `description_sale`, `description_purchase`, `categ_id`, `brand_id`, `quality`, `composition`, `gsm`, `martindale`, `washing_instruction`, `special_treatment`, `vendor_reference`, `width`, `product_app_description`, `create_date`, `active`, `main_product`, `is_main_similar`, `is_self_main`, and `is_catalogue`. Other useful product fields include `type`, `detailed_type`, `sale_ok`, and `purchase_ok`.

`product_product` provides `product_tmpl_id`, `default_code`, `barcode`, `active`, `create_date`, and variant-combination fields. Only **{int(active_products['template_reference'].notna().sum())}** active template references and **{int(active_products['variant_reference'].notna().sum())}** active variant references are populated. Barcode is populated on {int(active_products['barcode'].notna().sum()):,} active variants; POC sample values look like product IDs, not lineage codes.

`product_category` provides `name`, `complete_name`, `parent_id`, `active`, and `product_catalogue`. Category and brand are available but are not equivalence signals by themselves. `product_brand` has two rows. Custom material/specification fields have uneven coverage.

Attribute tables present: `product_attribute(id, name, create_variant, display_type)`, `product_attribute_value(id, attribute_id, name, html_color, is_custom)`, `product_template_attribute_line(product_tmpl_id, attribute_id, value_count, active)`, and `product_template_attribute_value(product_attribute_value_id, attribute_line_id, product_tmpl_id, attribute_id, ptav_active)`; they exist but have no template attribute lines or product-template attribute values in this snapshot. Custom sizes are present through `product_size(id, name)` and `product_size_product_template_rel(product_template_id, product_size_id)` (20 sizes and 667 template-size links).

Custom lineage candidates are `product_template_similar_rel(src_id, dest_id)` (5,873 directed rows, 2,955 unique unordered pairs), `all_similar_products(similar1, similar2)` (2,514 rows, all also present in the former table), and `product_template.main_product` (2,256 non-self pointers overall). The similarity tables are the strongest stored signal, but their exact business semantics are not documented in schema. `main_product` is a grouping/pointer signal, not proof of replacement.

Catalog structures include `catalogue_management(id, partner_id, salesperson_id, user_id, picking_id, all_partner_id, create_date, write_date)` (9,457 rows), `catalogue_management_line(id, partner_id, area, product_tmpl_id, no_of_catalogue, no_of_sale_orders, total_ordered_qty, total_delivered_qty, total_invoiced_qty, total_untaxed_amount, create_date, write_date)` (24,376 rows), `catalogue_product(id, catalogue_mgmt_id, product_id, quantity, create_date, write_date)` (12,825 rows), and `catalogue_management_product_product_rel(catalogue_management_id, product_product_id)` (15,693 rows). `sale_order_line` has standard `product_id`, `product_uom_qty`, `create_date`, plus custom `main_product`, `product_category`, `product_catalogue`, `catalogue_id`, `quality`, `area`, `size_id`, and `order_creation_date`. `product_category` includes `product_catalogue`. These provide catalog/order context, but no explicit product-version lineage field or human-readable book title was found in the inspected catalog columns.

Descriptions exist as fields but are sparse: `description` has six templates with text, `description_sale` and `description_purchase` have none. `product_app_description` has 196 populated templates. Internal references and descriptions cannot drive broad matching by themselves.

## Candidate Method and Limits

1. Generate candidates from explicit similarity relations, deduplicated by unordered pair and oriented using `create_date`.
2. Include `main_product` pointers as a separate stored source.
3. Enrich with category, brand, specifications, name family, dates, and observed sales; shared category or name stem alone remains weak evidence.
4. For lifecycle exploration, anchor month 1 to first observed sale and retain launch-date uncertainty. Check stock/availability before treating zero-sale months as zero demand.

The candidate CSV has one row per newer/older linked pair, with evidence sources, matching fields, first/last sale, selling-month count, and historical quantity. No Odoo records or forecasting code were changed.

## Recommended Next Steps

1. Have product/catalog owners validate a sample of explicit links, especially different-category pairs and ambiguous no-history cases; clarify the meaning and direction of both similarity tables and `main_product`.
2. Establish reliable product launch/effective dates and product availability or stockout history; creation date and first sale are proxies only.
3. Use human-reviewed labels (same product, replacement, substitute, unrelated) and allow multiple analogues in a discovery dataset.
4. Compare lifecycle profiles only for validated links. Do not implement forecast transfer until validation confirms these histories predict new-product demand.

## Artifacts

- `historical_similar_product_candidates.csv`: all recent Odoo-linked candidate pairs.
- `historical_similar_product_name_candidates.csv`: separate weak same-name-family/same-category candidates from the full catalog.
- `historical_similar_product_lifecycle.csv`: zero-filled month-since-first-sale profiles for unique strong-signal older products.
- This report: `historical_similar_product_discovery.md`.
"""

    report_path = DATA_ROOT / "historical_similar_product_discovery.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Read-only database: {database_name}")
    print(f"Recent candidate relationships: {relationship_count:,}")
    print(f"Strong/ambiguous: {strong_relationships:,}/{ambiguous_relationships:,}")
    print(f"Weak name-family candidates: {len(name_family_candidates):,}")
    print(f"Candidate CSV: {DATA_ROOT / 'historical_similar_product_candidates.csv'}")
    print(f"Name-family CSV: {DATA_ROOT / 'historical_similar_product_name_candidates.csv'}")
    print(f"Lifecycle CSV: {DATA_ROOT / 'historical_similar_product_lifecycle.csv'} ({len(lifecycle):,} rows)")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()