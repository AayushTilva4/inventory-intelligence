# Historical Similar Product Discovery

Read-only snapshot of Odoo database `dazzlefabrics_v17_2026-08-12`. Latest qualifying sale month: **2026-08-01**. Recent/new means an active product template created in the 12 months ending at the latest sales month (cutoff 2025-08-01). The catalog's `create_date` and first sale are proxies; neither proves the real commercial launch date.

## Findings

- Active product templates/variants: **10,637** of 12,289 total. This database currently has exactly one product variant per template.
- Active products with at least one qualifying historical sale: **7,188**. Across the catalog, qualifying sales span 2023-06-01 through 2026-08-01.
- Active new products in the 12-month window: **1,502**.
- Recorded newer-to-older candidate relationships: **289** across **255** new products. **235** new products have at least one old linked product with sales.
- Strong-signal relationships: **147**; ambiguous/weak-history relationships: **142**. Strong signal means a recorded Odoo relationship plus at least six distinct months with sales for the older product. It is not proof of equivalence.
- Separate name-family heuristic: **9,549** same parsed name-family/same-category pairs across **389** new products; **6,917** pairs have old-product sales and **2,760** have six or more selling months. These are weak, broad family leads and are not included in the primary 289 Odoo-linked relationship count.
- New products with 2+ analogues: **26**; with 3+: **7**. With 2+ selling analogues: **18**; with 3+: **6**.
- Unique older linked products: **284**, of which **255** have recorded sales: **123,194.93** units over **6,448** order lines and **2,796** product-months. These are totals across distinct analogues, not links.
- Strong-signal unique older products: **146**, with **117,306.28** units. Median elapsed months since last sale: **2**; **23** have no observed sale for at least six months and **5** for at least twelve months.

## Real Strong-Signal Examples

Selected by older-product selling-month count and quantity. Evidence describes stored links and observed metadata; category differences are retained rather than hidden.

| New product | Old analogue | Evidence | Old history | New history |
| --- | --- | --- | --- | --- |
| 447-22 (ID 21919) | 379-09 (ID 6626) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 36 distinct months | 36 selling months; 2023-06-01 to 2026-08-01; 8,456.0 units | 6.0 selling months; last sale 2026-08-07 |
| 448-21 (ID 22643) | 380-02 (ID 6683) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 36 distinct months | 36 selling months; 2023-06-06 to 2026-08-06; 1,075.5 units | n/a selling months; last sale n/a |
| 447-16 (ID 21913) | 379-03 (ID 6620) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 35 distinct months | 35 selling months; 2023-06-24 to 2026-06-10; 13,976.6 units | 3.0 selling months; last sale 2026-07-16 |
| 431-03 (ID 22571) | 325-02 (ID 819) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 35 distinct months | 35 selling months; 2023-06-07 to 2026-08-03; 2,216.6 units | n/a selling months; last sale n/a |
| 448-22 (ID 22644) | 380-03 (ID 6684) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 35 distinct months | 35 selling months; 2023-06-06 to 2026-07-01; 763.0 units | n/a selling months; last sale n/a |
| 431-02 (ID 22570) | 325-03 (ID 820) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 34 distinct months | 34 selling months; 2023-06-03 to 2026-06-25; 2,099.0 units | n/a selling months; last sale n/a |
| 447-14 (ID 21911) | 379-01 (ID 6618) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 33 distinct months | 33 selling months; 2023-06-01 to 2026-06-02; 3,966.0 units | 3.0 selling months; last sale 2026-06-12 |
| 447-17 (ID 21914) | 379-04 (ID 6621) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 33 distinct months | 33 selling months; 2023-06-02 to 2026-07-15; 3,868.2 units | 3.0 selling months; last sale 2026-06-04 |
| 447-25 (ID 21922) | 379-12 (ID 6629) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 33 distinct months | 33 selling months; 2023-06-06 to 2026-06-25; 3,056.0 units | 4.0 selling months; last sale 2026-06-22 |
| 448-23 (ID 22645) | 380-04 (ID 6691) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 33 distinct months | 33 selling months; 2023-06-24 to 2026-04-16; 1,150.0 units | n/a selling months; last sale n/a |
| 447-20 (ID 21917) | 379-07 (ID 6624) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 32 distinct months | 32 selling months; 2023-06-01 to 2026-07-22; 4,681.9 units | 4.0 selling months; last sale 2026-07-27 |
| 448-12 (ID 22638) | 380-14 (ID 6701) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 32 distinct months | 32 selling months; 2023-06-06 to 2026-08-07; 1,077.5 units | n/a selling months; last sale n/a |
| 448-26 (ID 22648) | 380-06 (ID 6693) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 32 distinct months | 32 selling months; 2023-06-12 to 2026-07-31; 648.3 units | n/a selling months; last sale n/a |
| 448-31 (ID 22650) | 380-09 (ID 6696) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 31 distinct months | 31 selling months; 2023-06-06 to 2026-07-28; 1,005.5 units | n/a selling months; last sale n/a |
| 448-24 (ID 22646) | 380-05 (ID 6692) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 31 distinct months | 31 selling months; 2023-06-22 to 2026-07-22; 810.5 units | n/a selling months; last sale n/a |
| 448-07 (ID 22636) | 380-19 (ID 6706) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 31 distinct months | 31 selling months; 2023-07-24 to 2026-08-08; 762.0 units | n/a selling months; last sale n/a |
| 447-18 (ID 21915) | 379-05 (ID 6622) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 30 distinct months | 30 selling months; 2023-06-10 to 2026-01-10; 2,791.2 units | 4.0 selling months; last sale 2026-05-16 |
| 447-21 (ID 21918) | 379-08 (ID 6625) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 30 distinct months | 30 selling months; 2023-06-09 to 2026-04-13; 2,603.6 units | 5.0 selling months; last sale 2026-07-23 |
| 431-40 (ID 22579) | 325-28 (ID 845) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 30 distinct months | 30 selling months; 2023-06-01 to 2026-07-15; 1,745.0 units | n/a selling months; last sale n/a |
| 448-03 (ID 22632) | 380-20 (ID 6707) | Recorded Odoo similarity/main-product relationship; category differs; old product sold in 30 distinct months | 30 selling months; 2023-06-06 to 2026-08-11; 715.5 units | n/a selling months; last sale n/a |

## Ambiguous Cases

These have a stored relationship but do not meet the six-selling-month threshold. Treat them as candidates requiring review, not analogues suitable for demand transfer.

| New product | Older linked product | Observed evidence |
| --- | --- | --- |
| 431-22 (ID 22578) | 202-25 (ID 1625) | product_template_similar_rel; category DF-431 / DF-202; old history 1.0 selling months |
| 431-19 (ID 22576) | V5-49 (ID 7963) | product_template_similar_rel; category DF-431 / DE-V5; old history 1.0 selling months |
| 423-55 (ID 22567) | 409-60 (ID 14337) | all_similar_products, product_template_similar_rel; category DF-423 / DF-409; old history 1.0 selling months |
| 423-52 (ID 22566) | 409-39 (ID 14316) | all_similar_products, product_template_similar_rel; category DF-423 / DF-409; old history 1.0 selling months |
| 423-35 (ID 22561) | 409-17 (ID 14294) | all_similar_products, product_template_similar_rel; category DF-423 / DF-409; old history 1.0 selling months |

## POC Cold Starts

The two POC forecasts marked cold-start are **2** products. The table reports Odoo recorded links and same-name-family/same-category matches separately as weak discovery leads.

| scenario | product_id | product_name | forecast_status | poc_history_months | possible_historical_analogues |
| --- | --- | --- | --- | --- | --- |
| fast_moving | 16697 | 413-11 | ok | 23 |  |
| rising_demand | 16905 | 415-39 | ok | 22 | 415-32 (ID 16753, 21 selling months; weak name/category match); 415-40 (ID 16755, 17 selling months; weak name/category match); 415-36 (ID 16754, 7 selling months; weak name/category match); 415-26 (ID 16749, 16 selling months; weak name/category match); 415-29 (ID 16751, 23 selling months; weak name/category match); 415-31 (ID 16752, 14 selling months; weak name/category match); 415-01 (ID 16744, 13 selling months; weak name/category match); 415-02 (ID 16745, 7 selling months; weak name/category match); 415-21 (ID 16746, 9 selling months; weak name/category match); 415-24 (ID 16747, 12 selling months; weak name/category match); 415-25 (ID 16748, 11 selling months; weak name/category match); 415-28 (ID 16750, 16 selling months; weak name/category match) |
| falling_demand | 17402 | 419-33 | ok | 19 |  |
| low_demand | 9220 | 392-31 | ok | 26 |  |
| reorder_needed | 22596 | Buckby Latte - AW | cold_start_category_average | 2 | Buckby Silver - AW (ID 20484, 1 selling months; weak name/category match); Buckby Graphite - AW (ID 18354, 1 selling months; weak name/category match) |
| excess_stock | 9436 | Naples-03 | ok | 32 |  |
| intermittent | 5448 | 353-20 | ok | 39 | 353-04 (ID 5432, 22 selling months; weak name/category match); 353-14 (ID 5442, 14 selling months; weak name/category match); 353-16 (ID 5444, 8 selling months; weak name/category match); 353-19 (ID 5447, 17 selling months; weak name/category match); 353-11 (ID 5439, 14 selling months; weak name/category match); 353-13 (ID 5441, 21 selling months; weak name/category match); 353-15 (ID 5443, 11 selling months; weak name/category match); 353-07 (ID 5435, 13 selling months; weak name/category match); 353-06 (ID 5434, 14 selling months; weak name/category match); 353-02 (ID 5430, 18 selling months; weak name/category match); 353-08 (ID 5436, 7 selling months; weak name/category match); 353-01 (ID 5429, 16 selling months; weak name/category match); 353-12 (ID 5440, 19 selling months; weak name/category match); 353-05 (ID 5433, 19 selling months; weak name/category match); 353-10 (ID 5438, 20 selling months; weak name/category match); 353-09 (ID 5437, 14 selling months; weak name/category match); 353-17 (ID 5445, 12 selling months; weak name/category match); 353-18 (ID 5446, 10 selling months; weak name/category match) |
| dead_stock_candidate | 1047 | 314-09 | ok | 39 | 314-05 (ID 1043, 2 selling months; weak name/category match); 314-02 (ID 1040, 1 selling months; weak name/category match); 314-03 (ID 1041, 7 selling months; weak name/category match); 314-04 (ID 1042, 1 selling months; weak name/category match); 314-06 (ID 1044, 4 selling months; weak name/category match); 314-07 (ID 1045, 2 selling months; weak name/category match); 314-08 (ID 1046, 4 selling months; weak name/category match) |
| cold_start | 22662 | 433-47 | cold_start_category_average | 1 | 433-37 (ID 21243, 1 selling months; weak name/category match); 433-03 (ID 21229, 1 selling months; weak name/category match); 351-42 (ID 54, 14.0 selling months; recorded link) |
| normal_healthy | 604 | 330-08 | ok | 39 | 330-03 (ID 599, 17 selling months; weak name/category match); 330-01 (ID 597, 6 selling months; weak name/category match); 330-02 (ID 598, 23 selling months; weak name/category match); 330-07 (ID 603, 8 selling months; weak name/category match); 330-05 (ID 601, 14 selling months; weak name/category match); 330-06 (ID 602, 10 selling months; weak name/category match); 330-04 (ID 600, 2 selling months; weak name/category match) |

Assessment: `433-47` has a recorded link to `351-42`; the latter has 14 selling months, 333 units, and last sold 2026-06-09. The new product itself has one sale month in the POC. `Buckby Latte - AW` has same-family/same-category peers `Buckby Silver - AW` and `Buckby Graphite - AW`, but each older peer has only one sale month (6 and 3 units respectively). That is weak evidence, not a usable demand history.

## Lifecycle Check

The lifecycle CSV contains zero-filled monthly quantities from each strong-signal older product's first observed sale month through 2026-08-01. `month_since_launch_proxy` is one-based from first sale month, not verified launch. The data supports lifecycle-aligned exploration. Product creation dates are unreliable launch labels: many catalog products share bulk-import dates, and some first sales occur months later.

No-sale tails can be measured but are not necessarily true zero demand: lack of sales may reflect stockouts, catalog withdrawal, or missing data. Current Odoo `active` flags do not mean the product was still selling; all older products in this recent candidate set are marked active, including those with long no-sale tails.

Example for the POC recorded link `433-47 → 351-42` (month 1 is first observed sale month):

| month_since_launch | sale_month | sales_quantity |
| --- | --- | --- |
| 1 | 2023-10-01 | 46.5 |
| 2 | 2023-11-01 | 0.0 |
| 3 | 2023-12-01 | 0.0 |
| 4 | 2024-01-01 | 0.0 |
| 5 | 2024-02-01 | 0.0 |
| 6 | 2024-03-01 | 0.0 |
| 7 | 2024-04-01 | 0.0 |
| 8 | 2024-05-01 | 0.0 |
| 9 | 2024-06-01 | 0.0 |
| 10 | 2024-07-01 | 0.0 |
| 11 | 2024-08-01 | 17.0 |
| 12 | 2024-09-01 | 1.0 |

The full sample through the latest month, including zero-sale tail months, is in the lifecycle CSV.

## Available Similarity Fields

`product_template` provides `name` (JSONB), `default_code`, `description`, `description_sale`, `description_purchase`, `categ_id`, `brand_id`, `quality`, `composition`, `gsm`, `martindale`, `washing_instruction`, `special_treatment`, `vendor_reference`, `width`, `product_app_description`, `create_date`, `active`, `main_product`, `is_main_similar`, `is_self_main`, and `is_catalogue`. Other useful product fields include `type`, `detailed_type`, `sale_ok`, and `purchase_ok`.

`product_product` provides `product_tmpl_id`, `default_code`, `barcode`, `active`, `create_date`, and variant-combination fields. Only **2** active template references and **2** active variant references are populated. Barcode is populated on 10,633 active variants; POC sample values look like product IDs, not lineage codes.

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
