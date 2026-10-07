# Demand Target Analysis: Ordered Quantity vs. Delivered Quantity

**Date:** October 7, 2026  
**Status:** Complete  
**Database:** Odoo Production Replica (`sale_order`, `sale_order_line`)  
**Scope:** 10 POC Products, Top 100 Active Products, and Full Catalog (7,482 Products, 109,585 Sale Lines)  

---

## 1. Executive Summary & Canonical Decision

### Canonical Recommendation
**`sol.product_uom_qty` (Ordered / Requested Quantity) MUST be the canonical forecasting target for Inventory Intelligence and Replenishment Forecasting.**

### Core Rationale
1. **Unconstrained Demand vs. Constrained Supply:** `product_uom_qty` represents true customer demand at the moment of order commitment (`state = 'sale'`). `qty_delivered` represents supply throughput, which is strictly capped by warehouse inventory levels.
2. **The "Stockout Censoring" Feedback Loop:** When warehouse inventory stockouts occur, `qty_delivered` drops to 0 or partial amounts while customer order demand remains high. Forecasting `qty_delivered` would cause the engine to learn that demand is low when products stock out, resulting in lower reorder quantities and perpetuating chronic stockouts.
3. **Observed Discrepancy:** Across the catalog, **89,926.4 units of confirmed customer orders went unfulfilled** (an overall fulfillment ratio of 95.61%). In fast-moving SKUs, fulfillment drops to **93.71%**, with over **16.8% of active months** suffering from delivery shortfalls.

---

## 2. Quantitative Comparison

The table below summarizes the quantitative audit across three cohorts: the 10 POC products, the top 100 products by volume, and the full catalog.

| Metric | 10 POC Products | Top 100 Active Products | Entire Catalog (7,482 SKUs) |
|---|---|---|---|
| **Total Product-Months** | 83 | 2,828 | 53,589 |
| **Total Ordered Quantity (`product_uom_qty`)** | 8,911.80 | 475,078.14 | 2,049,695.52 |
| **Total Delivered Quantity (`qty_delivered`)** | 8,298.30 | 452,859.60 | 1,959,769.13 |
| **Net Unfulfilled Gap** | **613.50 units** | **22,218.54 units** | **89,926.39 units** |
| **Overall Fulfillment Ratio** | **93.12%** | **95.32%** | **95.61%** |
| **Months Ordered > 0 but Delivered = 0 (Stockouts)** | 1 (1.20%) | 39 (1.38%) | 691 (1.29%) |
| **Months Ordered > Delivered (Partial Fulfillment)** | 9 (10.84%) | 476 (16.83%) | 3,337 (6.23%) |
| **Months Delivered > Ordered (Over-delivery / Returns)** | 0 (0.00%) | 0 (0.00%) | 0 (0.00%) |
| **Months Exact Match (Ordered == Delivered)** | 74 (89.16%) | 2,352 (83.17%) | 50,252 (93.77%) |

---

## 3. Product-Level Deep Dive

### 3.1. POC 10 Products Breakdown
In the POC cohort, high-velocity products bear the brunt of delivery shortfalls:

| Product ID | Code / Name | Demand Pattern | Ordered Qty | Delivered Qty | Gap | Fulfillment % | Months Partial | Months Zero Deliv |
|---|---|---|---|---|---|---|---|---|
| **16697** | `413-11` | Fast Moving | 6,784.1 | 6,322.1 | **462.0** | **93.2%** | 5 | 1 |
| **16905** | `415-39` | Fast Moving | 1,078.0 | 978.0 | **100.0** | **90.7%** | 1 | 0 |
| **17402** | `419-33` | Intermittent | 427.0 | 398.0 | **29.0** | **93.2%** | 1 | 0 |
| **604** | `330-08` | Intermittent | 360.0 | 337.5 | **22.5** | **93.8%** | 2 | 0 |
| **9220** | `392-31` | Intermittent | 146.6 | 146.6 | 0.0 | 100.0% | 0 | 0 |
| **22662** | `433-47` | Cold Start | 42.0 | 42.0 | 0.0 | 100.0% | 0 | 0 |
| **9436** | `Naples-03` | Intermittent | 34.6 | 34.6 | 0.0 | 100.0% | 0 | 0 |
| **22596** | `Buckby Latte` | Cold Start | 16.0 | 16.0 | 0.0 | 100.0% | 0 | 0 |
| **1047** | `314-09` | Cold Start | 14.0 | 14.0 | 0.0 | 100.0% | 0 | 0 |
| **5448** | `353-20` | Intermittent | 9.5 | 9.5 | 0.0 | 100.0% | 0 | 0 |

*Key finding:* For product `16697` (the primary fast-moving POC SKU), **462 meters** of customer demand went unfulfilled across 6 different months, including one month where orders were taken but 0 units were delivered due to stockouts.

### 3.2. Top 100 Active Products Analysis
Across the top 100 products, delivery gaps are frequent and substantial:
- **Product 16704 (`413-17`):** Ordered 5,943.0 vs. Delivered 5,055.0 $\to$ **888.0 units missed (85.1% fulfillment)** across 7 months.
- **Product 6620 (`379-03`):** Ordered 13,991.6 vs. Delivered 13,228.6 $\to$ **763.0 units missed (94.5% fulfillment)** across 12 months.
- **Product 1475 (`White Black Out`):** Ordered 9,885.0 vs. Delivered 9,125.0 $\to$ **760.0 units missed (92.3% fulfillment)** across 5 months.
- **Product 396 (`338-04`):** Ordered 8,768.0 vs. Delivered 8,390.4 $\to$ **377.6 units missed (95.7% fulfillment)** across 4 months.

---

## 4. Breakdown by Demand Pattern

Analyzing fulfillment gaps segmented by operational demand pattern reveals that fulfillment shortages are concentrated in high-demand, high-velocity SKUs:

| Demand Pattern | Number of Products | Total Ordered | Total Delivered | Unfulfilled Gap | Fulfillment Ratio | Months with Shortfall |
|---|---|---|---|---|---|---|
| **Fast Moving** | 190 | 379,591.0 | 359,483.3 | **20,107.8** | **94.70%** | 46 zero-deliv months |
| **Falling** | 341 | 443,181.5 | 424,081.0 | **19,100.4** | **95.69%** | 64 zero-deliv months |
| **Intermittent** | 4,400 | 967,735.5 | 926,628.6 | **41,106.9** | **95.75%** | 468 zero-deliv months |
| **Rising** | 118 | 80,256.9 | 76,582.3 | **3,674.8** | **95.42%** | 33 zero-deliv months |
| **Stable / Normal** | 108 | 80,388.2 | 77,204.8 | **3,183.4** | **96.04%** | 20 zero-deliv months |
| **Cold Start** | 2,305 | 97,413.9 | 94,668.2 | **2,745.6** | **97.18%** | 60 zero-deliv months |
| **Low Demand** | 20 | 1,127.6 | 1,120.1 | **7.5** | **99.33%** | 0 zero-deliv months |

### Observations:
1. Fast-moving items show the lowest fulfillment ratio (**94.70%**). These are exactly the items where stockout risk is highest.
2. Delivered quantity never exceeded ordered quantity ($0$ instances out of $53,589$ product-months). The gap is strictly one-directional: unfulfilled customer demand.

---

## 5. Strategic Conclusion for Inventory Intelligence

In supply chain and inventory theory (Silver, Pyke & Peterson; Makridakis et al.):
1. **Unconstrained Demand (`product_uom_qty`):** What customers wanted to buy. This is what safety stock, reorder points, and supplier POs must be sized to fulfill.
2. **Constrained Demand (`qty_delivered`):** What the business managed to deliver.

If the machine learning and statistical models are trained on `qty_delivered`:
- Periods of supplier delays or warehouse stockouts are treated by the model as "reduced customer demand".
- The engine will project lower demand for subsequent seasons, recommending smaller purchase orders.
- This creates an artificial downward spiral in stock availability for top-performing SKUs.

### Architectural Alignment Action Item:
- The SKU engine (`forecasting-engine/src/sales_data.py`) **already correctly uses `sol.product_uom_qty`**.
- The group forecast service (`backend/app/odoo/group_demand_service.py:99`) currently uses `SUM(sol.qty_delivered)`. In a future task, `group_demand_service.py` must be updated to align with `sol.product_uom_qty` (with `sol.display_type IS NULL`).
