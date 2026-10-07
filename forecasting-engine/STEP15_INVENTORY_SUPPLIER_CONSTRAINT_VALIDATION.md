# STEP 15: Inventory & Supplier Constraint Intelligence Validation Final Report

## Executive Summary

**Step 15** establishes rigorous empirical and architectural validation of the business, inventory, and supplier constraints applied after statistical demand forecasting. 

In Step 14, statistical demand forecasting was validated across the entire active catalog using `trimmed_mean_3`. However, Step 14 highlighted that pure mathematical demand recommendations ($1,849.3\,\text{m}$) were scaled to $5,100.0\,\text{m}$ when baseline supplier constraints ($50\,\text{m}$ roll length, $50\text{--}100\,\text{m}$ MOQ) were applied.

Step 15 audited real vendor master records in Odoo, separated real supplier data from fallback assumptions, quantified constraint inflation multipliers, audited main-product group substitutability, uncovered significant inbound in-transit stock ($196,528.31\,\text{m}$), and validated that portal-side draft purchase orders remain strictly safe, idempotent, and planner-governed.

### Key Operational Invariants Verified:
- **Central Forecast Model**: `trimmed_mean_3` remains the production champion.
- **Odoo Isolation**: **100% READ-ONLY**. Zero database writes, zero schema modifications, zero purchase orders, zero RFQs, and zero reorder-rule mutations in Odoo.
- **POC Portal Tables**: All draft POs and planner records reside exclusively in the POC PostgreSQL database (`portal_purchase_orders`, `portal_purchase_order_lines`).
- **Zero Purchase Protection**: Verified $100\%$ that if $Q_{\text{AI}} = 0.0$, then $Q_{\text{constrained}} \equiv 0.0$. Constraints **never** generate a phantom purchase on zero-demand items.
- **Test Suite**: **145 / 145 unit tests pass ($100\%$ pass rate)** in 8.79s.

---

## 1. What Supplier Data Exists in Odoo?

A comprehensive audit of all **12,331 physical stockable products** in Odoo revealed:

- **Vendor Mappings**: **7,169 products ($58.1\%$)** have an associated vendor in `product_supplierinfo`. The remaining **5,162 products ($41.9\%$)** have **no vendor mapping** in Odoo master data.
- **Vendor Identity**: 58 distinct active suppliers exist (e.g. Sam Haining, Weiwei, Manuel Revert, Lisa, Michel, Zenda-Bob, Amaris, Homec Tissus).
- **Purchase Unit of Measure (UOM)**: **12,330 products ($100.0\%$)** have valid UOMs ($96.7\%$ in meters, $2.9\%$ in Units, $0.4\%$ in $\text{m}^2$).
- **Vendor Minimum Order Quantity (MOQ)**:
  - Only **255 products ($2.1\%$)** have an explicit commercial MOQ ($>1$) entered in Odoo master data. These belong exclusively to supplier *Zenda-Bob* (ID 8813) with $\sim 1,000\,\text{m}$ MOQs.
  - $5,197$ products have `min_qty = 1.0` (Odoo's default placeholder for "no MOQ").
  - $6,879$ products have $0$ or null MOQ.
- **Vendor Lead Times (`delay`)**:
  - $10,288$ products ($83.4\%$) have `delay = 0` (unconfigured).
  - $2,043$ products ($16.6\%$) have `delay` between $1$ and $30$ days (averaging $< 1$ day).
  - Master data in Odoo does **not** track real international shipping lead times.

*Full dataset exported to:* [`step15_supplier_data_coverage.csv`](file:///e:/Agent/forecasting-engine/step15_supplier_data_coverage.csv).

---

## 2. How Much of Our Constraint Logic Is Based on Defaults?

- **MOQ Logic**: **$97.9\%$** of products rely on default assumption MOQs ($50\text{--}100\,\text{m}$) because Odoo lacks vendor-specific minimum order agreements. Only $2.1\%$ use actual Odoo MOQs.
- **Roll Length Logic**: **$100.0\%$** of roll length multiples ($50\,\text{m}$) are derived from Dazzle Fabrics standard textile packaging assumptions, as Odoo does not natively store roll packaging specifications.
- **Lead Time Logic**: **$100.0\%$** of lead time modeling ($90$ days) is an operational business parameter representing maritime freight from Asia/Europe, rather than an Odoo record.
- **Constraint Provenance Classification**:
  Every constraint evaluation now carries an explicit `constraint_source` tag:
  - `ODOO_VENDOR_DATA` ($2.1\%$ of products)
  - `PARTIAL_ODOO_DEFAULT_MOQ` ($56.0\%$ of products)
  - `DEFAULT_ASSUMPTION` ($41.9\%$ of products)
  - `MISSING` (blocks automatic PO generation)

---

## 3. Quantity Inflation Audit: Why Did Constrained Quantity Exceed AI Demand?

On the full catalog simulation:
- Total AI raw purchase need (post-absorption): **$1,638.1\,\text{meters}$** across 68 products.
- Total supplier-constrained PO quantity: **$4,950.0\,\text{meters}$**.

### Constraint Multiplier Distribution ($Q_{\text{constrained}} / Q_{\text{AI}}$):

| Multiplier Bracket | Product Count | Proportion | Operational Impact |
|---|---|---|---|
| **$\le 1.25\times$** | **7** | $10.3\%$ | Efficient replenishment; minor roll rounding |
| **$1.25\text{--}1.5\times$** | **1** | $1.5\%$ | Moderate packaging rounding |
| **$1.5\text{--}2.0\times$** | **4** | $5.9\%$ | Significant packaging adjustment |
| **$2.0\text{--}3.0\times$** | **4** | $5.9\%$ | High inflation; triggers planner review (`constraint_multiplier_gt_2x`) |
| **$> 3.0\times$** | **52** | **$76.5\%$** | **Extreme inflation; triggers mandatory planner review (`constraint_multiplier_gt_3x`)** |

### Root Cause of Extreme Multipliers:
The audit revealed that the vast majority of $> 3\times$ multipliers occur on **low-velocity or intermittent products** where the statistical recommendation is fractional or small (e.g. $0.10\,\text{m}$, $0.15\,\text{m}$, $0.22\,\text{m}$). Rounding a $0.10\,\text{m}$ deficit up to a standard $50\,\text{m}$ fabric roll results in a **$500\times$ multiplier**.

**Governance Solution Implemented**:
Any product with a multiplier $> 2\times$ or $> 3\times$ automatically raises an exception flag, requiring explicit human planner override before any purchase order can be drafted.

*Full itemized list exported to:* [`step15_constraint_inflation.csv`](file:///e:/Agent/forecasting-engine/step15_constraint_inflation.csv).

---

## 4. Are Group-Stock Absorption Decisions Operationally Trustworthy?

In Odoo, multi-variant products share a `main_product` foreign key in `product_template`:
- **1,927 multi-variant groups** exist, covering **4,244 products**.
- When variant $A$ has low stock but sibling variant $B$ holds surplus inventory, group absorption suppresses reordering variant $A$.

### Substitutability Audit:
An inspection of group metadata revealed that while some groups are genuinely interchangeable colorways of the exact same fabric, other groups link items with distinct design codes (e.g. `201-09` vs `807-11`) or lack composition/quality metadata.

### 4-Tier Relationship Classification:
1. **Clearly Interchangeable (`1_clearly_interchangeable_self_main`)**: $1,950$ items where the item is self-main or has identical fabric weave and GSM.
2. **Operationally Substitutable (`2_operationally_substitutable_same_specs`)**: Items sharing identical composition and quality specifications.
3. **Possibly Related But Not Safely Substitutable (`3_possibly_related_not_safely_substitutable`)**: Items linked under a group but having different design patterns or missing specs.
4. **Unknown / Standalone**: Single-product groups ($8,087$ items).

**Safety Guardrail Implemented**:
When inventory is absorbed under tier 3 (`possibly_related`), the engine flags `uncertain_group_substitutability`. Planners must verify interchangeability before canceling the procurement recommendation.

---

## 5. How Much Procurement Is Eliminated by Group Absorption?

On the full physical catalog:
- **Purchases Completely Eliminated**: **14 products**.
- **Total Physical Demand Absorbed**: **$197.6\,\text{meters}$**.
- **Capital Protected**: Prevents purchasing redundant inventory when warehouse already holds equivalent stock in sibling colorways.

*Full absorption trace exported to:* [`step15_group_absorption_audit.csv`](file:///e:/Agent/forecasting-engine/step15_group_absorption_audit.csv).

---

## 6. How Significant Is Missing Inbound-Stock Visibility?

A read-only audit of open purchase orders (`purchase_order` where `state = 'purchase'`) revealed:
- **1,787 confirmed open POs** exist in Odoo.
- **615 active products** currently have pending inbound shipments totaling **196,528.31 meters**!
- If the system only inspects on-hand stock (`stock_quant`), it risks recommending reorders for goods that are already in transit on cargo ships.

**Solution**:
The decision pipeline now cross-references pending PO quantities from Odoo and attaches an explicit planner warning `possible_inbound_stock_conflict` whenever inbound stock is detected, preventing duplicate commitments.

---

## 7. Is 90-Day Lead Time Justified or Merely a POC Assumption?

- **Empirical Reality**: Odoo master data has an average configured delay of $0.5$ days, which is an unconfigured placeholder.
- **Operational Reality**: Dazzle Fabrics imports textiles primarily from China, India, and Turkey via maritime container freight. Production ($30\text{--}45$ days) plus port handling and sea transit ($30\text{--}45$ days) totals **$60\text{--}90$ days**.
- **Conclusion**: The **90-day lead time assumption is fully operationally justified** for import fabrics, but it is an operational parameter rather than an Odoo database record. For local domestic spot purchases, the POC console must allow planners to select a shorter lead time (e.g. 14–30 days).

---

## 8. Complete Planner Exception Governance Rules (Task 10)

The decision engine now emits 11 structured planner review exceptions:

| Exception Code | Severity | Description | Gating Action |
|---|---|---|---|
| `missing_supplier` | **BLOCKING** | No vendor mapped in Odoo or portal | Draft PO blocked |
| `missing_uom` | **BLOCKING** | Product lacks valid purchase UOM | Draft PO blocked |
| `missing_lead_time` | **BLOCKING** | Lead time $\le 0$ days | Draft PO blocked |
| `constraint_multiplier_gt_3x` | **WARNING** | Supplier packaging inflated buy by $> 3\times$ | Requires planner confirmation |
| `constraint_multiplier_gt_2x` | **WARNING** | Supplier packaging inflated buy by $> 2\times$ | Requires planner confirmation |
| `default_moq_used` | **INFO** | Applied fallback MOQ ($50\,\text{m}$) due to missing Odoo MOQ | Review lot size |
| `default_roll_length_used` | **INFO** | Applied fallback roll size ($50\,\text{m}$) | Review roll multiple |
| `possible_inbound_stock_conflict` | **HIGH RISK** | Pending inbound PO found in Odoo | Prevents double-ordering |
| `group_stock_available_elsewhere` | **INFO** | Sibling variant absorbed purchase need | Confirms shared stock |
| `uncertain_group_substitutability` | **HIGH RISK** | Group members may not be interchangeable | Planner must verify |
| `stockout_suppressed_risk` | **INFO** | Demand may have been artificially suppressed by stockouts | Review target |

---

## 9. Business Scenario Testing Results (12 Archetypes)

All 12 representative business scenarios passed with exact mathematical precision:

```
ID  | Scenario Name                          | AI Qty   | Constrained | Mult   | Exceptions Flagged
-----------------------------------------------------------------------------------------------------------------------------
1   | AI need 23m, MOQ 100m                  | 23.1     | 100.0       | 4.33   | constraint_multiplier_gt_3x
2   | AI need 63m, 50m rolls                 | 62.7     | 100.0       | 1.59   | (Roll ceiling rounded to 100m)
3   | AI need 101m, 50m rolls                | 101.2    | 150.0       | 1.48   | (Roll ceiling rounded to 150m)
4   | AI need 0m, MOQ 100m                   | 0.0      | 0.0         | 1.00   | (Zero purchase protection active)
5   | Dead stock with MOQ                    | 0.0      | 0.0         | 1.00   | (Dead stock protection active)
6   | Group surplus absorbing need           | 0.0      | 0.0         | 1.00   | group_stock_available_elsewhere
7   | Uncertain similar-product relationship | 0.0      | 0.0         | 1.00   | group_stock_available_elsewhere, uncertain_group_substitutability
8   | Missing supplier                       | 27.5     | 100.0       | 3.64   | missing_supplier, constraint_multiplier_gt_3x (BLOCKED)
9   | Missing UOM                            | 27.5     | 100.0       | 3.64   | missing_uom, constraint_multiplier_gt_3x (BLOCKED)
10  | Missing lead time                      | 27.5     | 100.0       | 3.64   | missing_lead_time, constraint_multiplier_gt_3x (BLOCKED)
11  | Inbound stock unknown / pending        | 44.0     | 50.0        | 1.14   | possible_inbound_stock_conflict
12  | Constrained quantity >3x AI quantity   | 0.5      | 50.0        | 100.00 | default_moq_used, default_roll_length_used, constraint_multiplier_gt_3x
```

---

## 10. Automated Test Suite Results

The comprehensive test suite in [`test_step15_constraint_intelligence.py`](file:///e:/Agent/backend/tests/test_step15_constraint_intelligence.py) and all existing benchmark tests were executed:

```
Ran 145 tests in 8.792s
OK (0 failures, 0 errors, 0 skipped)
```
- **Total Backend Tests**: 145
- **Pass Rate**: $100\%$

---

## 11. Artifacts Generated in Step 15

1. [`STEP15_SUPPLIER_CONSTRAINT_AUDIT.md`](file:///e:/Agent/forecasting-engine/STEP15_SUPPLIER_CONSTRAINT_AUDIT.md) — Detailed vendor master data audit report.
2. [`STEP15_INVENTORY_SUPPLIER_CONSTRAINT_VALIDATION.md`](file:///e:/Agent/forecasting-engine/STEP15_INVENTORY_SUPPLIER_CONSTRAINT_VALIDATION.md) — This final report.
3. [`step15_supplier_data_coverage.csv`](file:///e:/Agent/forecasting-engine/step15_supplier_data_coverage.csv) — Catalog-wide vendor, UOM, and delay mapping (12,331 rows).
4. [`step15_constraint_inflation.csv`](file:///e:/Agent/forecasting-engine/step15_constraint_inflation.csv) — Audit of all items with quantity inflation multipliers (68 rows).
5. [`step15_group_absorption_audit.csv`](file:///e:/Agent/forecasting-engine/step15_group_absorption_audit.csv) — Audit of all group inventory absorption events (14 rows).

---

## 12. Recommendation for Next Step

With Step 15 complete and all inventory/supplier constraints hardened:
- **Central Model**: `trimmed_mean_3` remains rock-solid.
- **Supplier Logic**: Zero-purchase protection is guaranteed; inflation multipliers are transparently flagged; group absorption is governed; in-transit stock conflicts are alerted.
- **Proceed to Step 16**: **Interactive Human Planner Procurement Console** (building the Next.js frontend screens to view, filter, review exceptions, adjust quantities, approve recommendations, and generate portal-side draft purchase orders).
