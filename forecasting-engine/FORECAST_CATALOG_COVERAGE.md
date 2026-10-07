# Full Product Catalog Audit: Forecast Coverage & Demand Topology

**Project:** Inventory Intelligence — Dazzle Fabrics Odoo Catalog  
**Step:** Step 12 — Task 1  
**Scope:** Complete Read-Only Inspection of All 8,485 Available Odoo Products  
**Date:** October 2026  
**Status:** COMPLETE (Read-Only Audit)

---

## 1. Executive Summary

This audit inspects the complete Odoo product and sales catalog (8,485 total items) without sampling or truncating to top sellers. In accordance with strict project guidelines, all analysis was conducted strictly via **read-only** extraction from Odoo.

The catalog exhibits extreme structural skew:
- **11.8% (1,003 products)** have zero lifetime sales history.
- **63.4% (5,376 products)** are dormant dead stock with no sales in $\ge 6$ months.
- **76.1% (6,458 products)** recorded zero sales in the most recent 3 months.
- **Only 23.9% (2,027 products)** are actively circulating in the recent 3-month operational window.
- **20.3% (1,726 products)** have exactly one single positive sales observation across their lifetime.
- **87.8% (7,453 products)** have calendar gaps (missing calendar months) in raw transaction records.

The primary implication is that **traditional time-series algorithms (ARIMA, Holt-Winters, complex ML) are structurally inappropriate for over 90% of the catalog**. The forecasting engine must possess a deterministic, guarded fallback hierarchy to guarantee stability, non-negativity, and zero phantom replenishment.

---

## 2. Complete Catalog Breakdown

### 2.1 Sales History & Recency

| Category | Product Count | Percentage of Total (N=8,485) | Definition / Rule |
| :--- | :---: | :---: | :--- |
| **Total Products** | **8,485** | **100.0%** | Union of `product_product`/`product_template` and stock inventory |
| **Products with Historical Sales** | **7,482** | **88.2%** | At least one sales transaction recorded in Odoo |
| **Products with Zero Lifetime Sales** | **1,003** | **11.8%** | Never sold since inception |
| **Active in Recent 3 Months** | **2,027** | **23.9%** | Positive sales during the last 3 calendar months |
| **Active in Recent 6 Months** | **3,107** | **36.6%** | Positive sales during the last 6 calendar months |
| **Active in Recent 12 Months** | **4,417** | **52.1%** | Positive sales during the last 12 calendar months |
| **Zero Sales in Recent 3 Months** | **6,458** | **76.1%** | Total sales in last 3 months $= 0$ |
| **Zero Sales in Recent 6 Months** | **5,378** | **63.4%** | Total sales in last 6 months $= 0$ |
| **Zero Sales in Recent 12 Months** | **4,068** | **47.9%** | Total sales in last 12 months $= 0$ |

---

### 2.2 History Depth (Span from First Sale to Present)

| History Depth Tier | Product Count | Percentage | Forecasting Implication |
| :--- | :---: | :---: | :--- |
| **No History (`0m`)** | 1,003 | 11.8% | Cold-start / catalogue / analogue fallback required |
| **Extremely Short (`<3m`)** | 87 | 1.0% | Cannot calculate 3-month window; single-point fallback |
| **Short (`3-5m`)** | 248 | 2.9% | Cold-start / short-history; seasonal models invalid |
| **Medium (`6-11m`)** | 461 | 5.4% | Minimum history for rolling median/trimmed mean |
| **Moderate (`12-17m`)** | 519 | 6.1% | Full 1-year history; annual seasonality cannot be cross-validated |
| **Sufficient (`18-23m`)** | 631 | 7.4% | Standard time series eligible |
| **Long (`>=24m`)** | 5,536 | 65.2% | Deep historical depth available |
| **Cumulative `< 12 Months`** | **796** | **9.4%** | Insufficient for annual seasonal decomposition |
| **Cumulative `>= 18 Months`** | **6,167** | **72.7%** | Sufficient span (though many dormant) |

---

### 2.3 Observation Sparsity & Intermittency

| Demand Sparsity Feature | Count | Percentage | Operational Impact |
| :--- | :---: | :---: | :--- |
| **Single Lifetime Observation** | 1,726 | 20.3% | Only 1 active month; sample variance is undefined without zero padding |
| **Few Observations (2–3 Months)** | 1,621 | 19.1% | Extremely high sampling variance |
| **Moderate Observations (4–6 Months)** | 1,379 | 16.3% | Intermittent / sparse handling required |
| **Sustained Observations ($\ge 7$ Months)**| 2,756 | 32.5% | Regular sales history |
| **Missing Calendar Month Gaps** | 7,453 | 87.8% | Raw sales lack calendar continuity; zero-fill padding strictly required |

---

### 2.4 Demand Pattern Classification (Syntetos-Boylan & Operational)

Using the standardized Benchmark V2 operational classification taxonomy:

| Demand Pattern | Product Count | Pct of Catalog | Characteristics |
| :--- | :---: | :---: | :--- |
| **`dead_stock`** | **5,376** | **63.4%** | Dormant $\ge 6$ months with on-hand inventory or total dormancy |
| **`intermittent`** | **2,245** | **26.5%** | Sporadic purchases, $\text{ADI} \ge 1.5$ or active ratio $\le 35\%$, active in last 6m |
| **`cold_start`** | **335** | **3.9%** | Less than 6 months of calendar history from introduction |
| **`falling`** | **257** | **3.0%** | Trend $\le -25\%$ over recent vs previous 6 months |
| **`fast_moving`** | **129** | **1.5%** | Volume $\ge 40$ units/mo and active ratio $\ge 65\%$ |
| **`stable/normal`** | **69** | **0.8%** | Predictable baseline, low volatility, consistent sales |
| **`rising`** | **67** | **0.8%** | Trend $\ge +25\%$ over recent vs previous 6 months |
| **`low_demand`** | **5** | **0.1%** | Active low volume ($0 < \text{recent\_avg} < 5$) |
| **`no_history`** | **2** | <0.1% | Products with zero transactions and zero stock |
| **Total** | **8,485** | **100.0%** | Full catalog coverage |

---

## 3. Stockout Patterns & Inventory Topology

| Inventory Status | Product Count | Pct of Catalog | Description |
| :--- | :---: | :---: | :--- |
| **Stock on Hand $> 0$** | 7,045 | 83.0% | Positive on-hand physical inventory |
| **Stock on Hand $= 0$** | 1,438 | 17.0% | Stockout / zero physical inventory |
| **Stock on Hand $< 0$** | 2 | <0.1% | Negative ledger anomaly in Odoo (requires non-negative floor) |
| **Stockout with Active Demand** | 143 | 1.7% | Active demand in recent 3 months, but currently 0 stock on hand |
| **Dead Stock with Tied-Up Stock** | 4,066 | 47.9% | Zero sales in $\ge 6$ months, yet holding positive stock |

---

## 4. Key Architectural Conclusions

1. **Dead Stock Dominates:** Nearly two-thirds (63.4%) of the catalog is dormant. The engine MUST enforce a deterministic zero-clamp: `forecast = 0.0`, `buffer = 0.0`, `target = 0.0`, `suggested_purchase = 0.0`. Any leakage would result in catastrophic capital misallocation into dead stock.
2. **Calendar Alignment is Mandatory:** 87.8% of products have missing transaction months. If series are not padded with zeroes to a common calendar origin, elapsed time is collapsed and demand rates are artificially inflated.
3. **Short History is Non-Trivial:** 335 cold-start and 87 `<3m` products cannot support 3-month trimmed mean directly. A deterministic fallback (e.g., recent mean, category baseline, or safe zero floor) is strictly required.
4. **Active Purchasing is Concentrated:** Only ~2,000 products represent the active purchasing footprint of Dazzle Fabrics.
