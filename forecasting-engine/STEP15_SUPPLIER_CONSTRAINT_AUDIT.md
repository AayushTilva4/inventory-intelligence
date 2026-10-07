# STEP 15: Odoo Supplier Constraint & Procurement Data Audit

## 1. Executive Summary & Objective

The objective of **Step 15 Task 1** is to perform a comprehensive, read-only audit of the vendor and procurement data currently present in the Dazzle Fabrics Odoo database.

In previous phases (Steps 10–14), the decision engine used realistic baseline procurement assumptions:
- $50\,\text{m}$ standard roll length
- $50\text{--}100\,\text{m}$ minimum order quantity (MOQ)
- $90$-day maritime import lead time

This audit evaluates what procurement data actually exists in Odoo vs. what must be supplied by portal configuration or documented fallback assumptions.

---

## 2. Odoo Schema & Table Inspection

The audit queried Odoo database schema tables with **100% READ-ONLY SQL queries**:
- `product_supplierinfo`: Stores vendor-product mappings, vendor pricelists, vendor codes, minimum order quantities (`min_qty`), and vendor lead times (`delay`).
- `res_partner`: Stores vendor identity, contact, and company information.
- `uom_uom`: Stores unit of measure definitions (`m`, `Units`, `m²`, `mm`).
- `purchase_order` / `purchase_order_line`: Stores historical and active purchase orders and pending receipts.

---

## 3. Detailed Data Coverage Analysis (Full Catalog: 12,331 Physical Products)

| Procurement Field | Records in Odoo | Proportion | Evaluation & Trustworthiness |
|---|---|---|---|
| **Total Physical Stockable Products** | **12,331** | $100.0\%$ | Complete physical catalog in Dazzle Odoo |
| **Products with Vendor Mapping (`partner_id`)** | **7,169** | **$58.1\%$** | **58 distinct suppliers** found in `product_supplierinfo` |
| **Products Lacking Vendor Information** | **5,162** | **$41.9\%$** | Zero vendor records in Odoo; requires portal assignment |
| **Products with Usable Purchase UOM** | **12,330** | **$100.0\%$** | $11,923$ meters ($96.7\%$), $353$ Units ($2.9\%$), $54$ $\text{m}^2$ ($0.4\%$) |
| **Products with Explicit Vendor MOQ ($>1$)** | **255** | **$2.1\%$** | Only 1 vendor (Zenda-Bob, ID 8813) configured real MOQ ($\sim 1,000\,\text{m}$) |
| **Products with Default / Missing MOQ ($\le 1$)** | **12,076** | **$97.9\%$** | $5,197$ have `min_qty = 1.0` (Odoo dummy default); $6,879$ have $0$ or null |
| **Products with Vendor Lead Time (`delay > 0`)** | **2,043** | **$16.6\%$** | Recorded delay is dummy ($0.4\text{--}0.7$ days); real sea freight is unconfigured |
| **Products with Pending Inbound Shipments** | **615** | **$5.0\%$** | **$196,528.31\,\text{meters}$** currently in transit across $1,787$ open POs |

---

## 4. Analysis of Top Suppliers in Odoo

The top 10 vendors account for **5,431 products** ($75.8\%$ of mapped products):

| Partner ID | Supplier Name | Mapped Products | Configured Delay (`delay`) | Configured MOQ (`min_qty`) | Real MOQ $>1$ |
|---|---|---|---|---|---|
| **6024** | Sam Haining | 1,060 | 0.5 days | 0.52 m | 0 |
| **6025** | Weiwei | 1,035 | 0.4 days | 0.62 m | 0 |
| **5510** | Manuel Revert | 819 | 0.4 days | 0.57 m | 0 |
| **6023** | Lisa | 559 | 0.5 days | 0.49 m | 0 |
| **6101** | Michel | 555 | 0.6 days | 0.42 m | 0 |
| **8813** | Zenda-Bob (Hangzhou Yingboer) | 268 | 0.0 days | 1,033.6 m | **255** |
| **6022** | Amaris | 245 | 0.7 days | 0.32 m | 0 |
| **5905** | Homec Tissus | 229 | 0.1 days | 0.91 m | 0 |
| **7128** | Morgan | 212 | 0.0 days | 0.98 m | 0 |
| **7568** | W FABRICS | 210 | 0.6 days | 0.38 m | 0 |

### Crucial Findings:
1. **Zenda-Bob (Partner 8813)** is the ONLY vendor where explicit commercial MOQs were ever entered into Odoo ($1,000\,\text{m}$ minimum orders).
2. All other suppliers have `min_qty` set to $1.0$ or fractions, which represents Odoo's internal single-unit default, **not real mill manufacturing constraints**.
3. All suppliers have `delay` set to $0$ or $< 1$ day. Dazzle Fabrics imports goods via maritime freight (30–90 days), but their operations team never configured delivery delays into Odoo master data.

---

## 5. Separation of Actual vs Default Constraints

To maintain audit integrity, the decision pipeline now explicitly classifies the provenance of all constraint parameters:

- `ODOO_VENDOR_DATA`: Constraint originated from a verified master record in Odoo (e.g. Zenda-Bob MOQ $= 1,000\,\text{m}$, purchase UOM $= \text{meters}$).
- `PORTAL_CONFIGURED`: Constraint explicitly configured by an inventory planner inside the POC database.
- `DEFAULT_ASSUMPTION`: Standard textile industry fallback applied because Odoo data is unconfigured (e.g. $50\,\text{m}$ roll length, $50\,\text{m}$ fallback MOQ, $90$-day maritime lead time).
- `MISSING`: Critical parameter is entirely absent (e.g. product has no vendor assigned), which raises a blocking exception in the planner queue.

---

## 6. Recommendations for Procurement Console Integration

1. **Vendor Assignment Queue**: $5,162$ products ($41.9\%$) lack vendor mappings. A dedicated planner exception `missing_supplier` must prevent automatic PO creation until assigned.
2. **Vendor Master Data Enhancement**: The POC portal must allow planners to define mill-level roll sizes and contract MOQs per vendor, replacing generic $50\,\text{m}$ defaults.
3. **Inbound PO Awareness**: Inbound purchase visibility must be incorporated into stock position calculations for the $615$ products with pending container shipments.
