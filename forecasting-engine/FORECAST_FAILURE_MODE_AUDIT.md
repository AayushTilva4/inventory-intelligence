# Forecast Failure Mode & Operational Risk Audit

**Project:** Inventory Intelligence — Dazzle Fabrics Odoo Catalog  
**Step:** Step 12 — Task 2  
**Scope:** Complete Identification of Edge Cases and Structural Failure Modes  
**Date:** October 2026  
**Status:** COMPLETE (Pre-Remediation Baseline)

---

## 1. Executive Summary

This audit catalogs all failure modes, edge cases, and risk factors present across the complete 8,485-product catalog. 

Without explicit hardening:
1. **11.8% of products (1,003 items)** lack any historical sales, which crashes traditional time-series methods.
2. **1.0% of products (87 items)** have $< 3$ months history, causing out-of-bounds indexing or empty array slicing in 3-month windowing models.
3. **47.9% of products (4,066 items)** are dormant dead stock with physical stock on hand; without hard clamping, models recommend catastrophic phantom replenishment.
4. **20.3% of products (1,726 items)** have only a single lifetime sales observation, causing trimmed-mean outlier removal to discard the only real signal.
5. **1.7% of products (143 items)** suffer from stockout-suppressed demand where zero sales is an artifact of zero stock rather than zero customer interest.

---

## 2. Failure Mode Catalog

### FM-01: Zero Lifetime Sales History (Cold Introduction / Dormant Catalog Items)
- **Condition:** `has_sales_history == False` ($0$ sales transactions in Odoo).
- **Affected Product Count:** **1,003 products (11.82%)**
- **Example Product IDs:** `[28, 31, 32, 142, 150]`
- **Current Behavior:** Time-series algorithms crash or raise `ValueError: empty series`. If unhandled, creates `NaN` or unhandled exceptions.
- **Expected Safe Behavior:** Deterministic fallback:
  - If item has no stock and no sales: assign `forecast = 0.0`, `buffer = 0.0`, `target = 0.0`, `purchase = 0.0` (Dormant).
  - If item is a newly introduced SKU with initial target requirement: assign analogue/category fallback baseline.
- **Severity:** **HIGH**
- **Fallback Required:** **YES** (`Strategy: analogue_or_category_fallback` or `zero_demand_safe_floor`).

---

### FM-02: Extremely Short History ($< 3$ Months)
- **Condition:** `has_sales_history == True` and calendar history span $< 3$ months.
- **Affected Product Count:** **87 products (1.03%)**
- **Example Product IDs:** `[1930, 4248, 7635, 8108, 13344]`
- **Current Behavior:** `trimmed_mean_3` slices the last 3 months; if history length $< 3$, slice produces fewer than 3 observations. When trimming max and min on an array of length 1 or 2, array becomes empty, leading to `NaN` or zero division.
- **Expected Safe Behavior:** Fallback to simple mean of available positive months or last observation carry-forward.
- **Severity:** **HIGH**
- **Fallback Required:** **YES** (`Strategy: recent_mean_fallback`).

---

### FM-03: Insufficient History for Seasonality (3–11 Months)
- **Condition:** Calendar history span between 3 and 11 months.
- **Affected Product Count:** **709 products (8.36%)**
- **Example Product IDs:** `[22, 41, 418, 421, 588]`
- **Current Behavior:** Seasonal algorithms (SARIMA, Seasonal Naive, 12-month lag models) crash with `ValueError: series length < seasonal_period (12)`.
- **Expected Safe Behavior:** Explicit history gate: restrict model candidates to non-seasonal methods (`trimmed_mean_3`, `median_baseline`, `recent_mean_fallback`).
- **Severity:** **MEDIUM**
- **Fallback Required:** **YES** (Eligibility filter).

---

### FM-04: Single Positive Observation in Lifetime
- **Condition:** `positive_months_count == 1`.
- **Affected Product Count:** **1,726 products (20.34%)**
- **Example Product IDs:** `[10, 18, 21, 37, 41]`
- **Current Behavior:** If the single observation occurred within the last 3 months, `trimmed_mean_3` (which trims the maximum and minimum) may trim the single positive value as the maximum, collapsing the forecast to $0.0$. If it occurred $> 12$ months ago, product is dead stock.
- **Expected Safe Behavior:** 
  - If single sale is dormant ($> 12$ months ago): hard clamp to $0.0$.
  - If single sale is recent ($< 3$ months ago): evaluate as sporadic/one-off demand; use conservative single-event rate or median fallback rather than collapsing to $0.0$ unexpectedly.
- **Severity:** **MEDIUM**
- **Fallback Required:** **YES** (`Strategy: single_event_fallback` or `dead_stock_zero_clamp`).

---

### FM-05: Dead Stock with Latent Inventory
- **Condition:** `months_since_last_sale >= 12` and `stock_on_hand > 0`.
- **Affected Product Count:** **4,066 products (47.92%)**
- **Example Product IDs:** `[10, 12, 13, 18, 19]`
- **Current Behavior:** Legacy systems calculating lifetime average sales or unsegmented moving averages generate positive forecasts (e.g. 1.2 units/mo) and trigger recurring reorders for products that have not sold in years.
- **Expected Safe Behavior:** Strict hard clamp: `forecast = 0.0`, `safety_buffer = 0.0`, `target_stock = 0.0`, `suggested_purchase = 0.0`.
- **Severity:** **CRITICAL**
- **Fallback Required:** **NO** (Hard Deterministic Guardrail).

---

### FM-06: Reactivated Demand After Dormancy
- **Condition:** No sales for $\ge 6$ months, followed by positive sales in the last 1–2 months.
- **Affected Product Count:** **1,137 products (13.40%)**
- **Example Product IDs:** `[14, 47, 49, 50, 53]`
- **Current Behavior:** Pattern classification based solely on a 12-month or 24-month inactive window may classify the product as `dead_stock`, suppressing replenishment even when sales have resumed.
- **Expected Safe Behavior:** Reactivation rule: if sales in the last 1–2 months are $> 0$, override `dead_stock` to `intermittent` or `rising`, allowing the forecast to adapt immediately.
- **Severity:** **MEDIUM**
- **Fallback Required:** **YES** (Pattern override rule).

---

### FM-07: Stockout-Suppressed Demand
- **Condition:** `stock_on_hand == 0`, recent 3 months sales $= 0$, but previous 12 months sales $> 0$.
- **Affected Product Count:** **143 products (1.69%)**
- **Example Product IDs:** `[87, 305, 386, 491, 494]`
- **Current Behavior:** Engine sees 0 recent sales and forecasts 0. Stock remains 0. Product enters a permanent stockout death-spiral (lost demand is interpreted as zero demand).
- **Expected Safe Behavior:** Stockout awareness flag: if zero stock coincides with zero sales for a historically active SKU, maintain minimum baseline target based on historical active run rate, flagging for planner review.
- **Severity:** **HIGH**
- **Fallback Required:** **YES** (Stockout-aware diagnostic flag & baseline safeguard).

---

### FM-08: Missing Calendar Months in Raw Transactions
- **Condition:** Products with non-consecutive sales transactions in Odoo (gaps in raw order line months).
- **Affected Product Count:** **7,453 products (87.84%)**
- **Example Product IDs:** `[10, 12, 13, 14, 18]`
- **Current Behavior:** If fed directly into time series without continuous calendar zero-padding, elapsed time collapses. A product that sold 10 units in Jan 2024 and 10 units in Jan 2026 appears as consecutive months $[10, 10]$, artificially quadrupling the apparent velocity.
- **Expected Safe Behavior:** `complete_product_series` with continuous monthly date range and zero-fill must be strictly applied before any feature calculation or model execution.
- **Severity:** **HIGH**
- **Fallback Required:** **NO** (Mandatory Preprocessing Invariant).

---

### FM-09: Negative Ledger Quantities in Inventory
- **Condition:** `stock_on_hand < 0`.
- **Affected Product Count:** **2 products (<0.1%)**
- **Example Product IDs:** `[404, 519]`
- **Current Behavior:** Negative stock inflates net requirement: $\text{suggested\_purchase} = \text{target} - (-5) = \text{target} + 5$, causing over-purchasing to offset inventory ledger errors.
- **Expected Safe Behavior:** Enforce non-negative inventory floor: `effective_stock = max(0.0, stock_on_hand)`.
- **Severity:** **MEDIUM**
- **Fallback Required:** **NO** (Mandatory Guardrail).

---

## 3. Risk & Mitigation Matrix

| Failure Mode | Affected SKUs | Severity | Mitigation Strategy | Enforcement Layer |
| :--- | :---: | :---: | :--- | :--- |
| **FM-01: Zero Lifetime Sales** | 1,003 | HIGH | Category/Analogue Fallback or Zero Floor | History Sufficiency Layer |
| **FM-02: Extremely Short History** | 87 | HIGH | Recent Mean Fallback | History Sufficiency Layer |
| **FM-03: Insufficient Seasonal History**| 709 | MEDIUM | Seasonal Model Disqualification | Eligibility Filter |
| **FM-04: Single Lifetime Observation** | 1,726 | MEDIUM | Dormancy Check & Single-Event Handling | Fallback Hierarchy |
| **FM-05: Dead Stock Over-Purchase** | 4,066 | CRITICAL | Zero Clamp (`f=0, b=0, t=0, p=0`) | Business Guardrail |
| **FM-06: Latent Reactivation** | 1,137 | MEDIUM | Recency Override on Dead Stock | Classification Hardening |
| **FM-07: Stockout Death-Spiral** | 143 | HIGH | Stockout Awareness Diagnostic Flag | Diagnostic / Recommendation Layer |
| **FM-08: Missing Month Collapse** | 7,453 | HIGH | Calendar Padding (`complete_product_series`)| Preprocessing Invariant |
| **FM-09: Negative Stock Ledgers** | 2 | MEDIUM | `max(0.0, stock_on_hand)` | Inventory Guardrail |
