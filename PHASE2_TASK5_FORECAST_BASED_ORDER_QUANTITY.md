# Phase 2 — Task 5: Forecast-Based Order Quantity Report

**Status:** Completed  
**Objective:** Replace legacy historical averaging ($6\text{-month average} \times 4$) with a forecast-driven demand requirement over the operational horizon (Lead Time + Review Period), integrating Task 4 canonical Inventory Position.  
**Odoo Status:** 100% Read-Only (0 writes, 0 schema changes, 0 POs/RFQs created).

---

## 1. Current Old Formula vs. New Forecast-Based Formula

### Legacy Formula (Before Task 5)
In the legacy system (`forecasting-engine/src/reorder.py` and `group_recommendation_service.py`), replenishment requirements were derived from a trailing 6-month historical average:
$$\text{Legacy Demand} = \frac{1}{k} \sum_{i=1}^{k} \text{Actual Sales}_{-i} \quad (k \le 6)$$
$$\text{Legacy Reorder Point} = \text{Legacy Demand} \times (\text{Lead Time Months} + \text{Safety Stock Months}) = \text{Legacy Demand} \times 4.0$$
$$\text{Legacy Buffered Target} = \text{Legacy Reorder Point} \times (1 + \text{BUFFER\_PCT}) = 4.4 \times \text{Legacy Demand}$$

---

### 2. Why the Legacy Formula Was Wrong
1. **Completely Ignored the Machine Learning / Statistical Forecast:** Even though high-accuracy champion models (`trimmed_mean_3`, `seasonal_naive`, `croston`) were selected, their forward predictions were completely discarded in purchasing decisions.
2. **Severely Distorted Seasonal & High-Growth Items (e.g. Group 325-42 & 394-27):**
   - For group `325-42`, trailing 6-month sales were low ($6.33\,\text{m/month}$), giving an old target of $27.87\,\text{m}$.
   - Despite an upcoming seasonal demand forecast of **$1,292\,\text{m}$**, the legacy formula classified the group's $461.3\,\text{m}$ stock as **`excess_stock`** ($461.3 \ge 2 \times 27.87$), recommending $0\,\text{m}$ purchase and triggering a catastrophic stockout.
3. **Purchased Stock for Dying / Dead Products (e.g. Group 393-29):**
   - A product with past sales that had completely ceased still had a positive 6-month average ($38.5\,\text{m/month}$), resulting in a legacy reorder target of $154.0\,\text{m}$ and false purchase recommendations for dead stock.

---

## 3. New Forecast-Based Requirement Formula

The replenishment requirement is now strictly derived from the forward-looking forecast across the full operational horizon:

$$\mathbf{\text{Operational Horizon Demand}} = \text{Lead Time Demand} (3\,\text{months}) + \text{Review Period Demand} (1\,\text{month})$$

$$\mathbf{\text{Reorder Point (ROP)}} = \text{Forecasted Horizon Demand}$$

$$\mathbf{\text{Buffered Target Stock}} = \text{Reorder Point} \times (1 + \text{BUFFER\_PCT}) = \text{Forecasted Horizon Demand} \times 1.10$$

$$\mathbf{\text{Inventory Position}} = \text{Usable Stock} + \text{Incoming Stock} - \text{Committed Customer Demand}$$

$$\mathbf{\text{Stock Gap}} = \max\Big(\text{Buffered Target Stock} - \text{Inventory Position},\; 0.0\Big)$$

$$\mathbf{\text{Suggested Purchase Qty}} = \lceil \text{Stock Gap} \rceil$$

---

## 4. Operational Horizon Decomposition & Lead Time / Review Period Treatment

- **Lead Time ($L = 3\,\text{months}$):** Represents standard textile sea-freight import duration from overseas mills.
- **Review Period ($R = 1\,\text{month}$):** Represents the monthly ordering and planning cycle.
- **Total Operational Horizon ($L + R = 4.0\,\text{months}$):** Guarantees that stock ordered today covers both the shipment lead time and the operational window until the next replenishment order arrives.

---

## 5. Current Month Partial-Days Handling (Task 3 Compliance)

To eliminate early-month artificial demand collapses (which the mentor identified as $\sim 93\%$ inaccurate when scaled):

1. **Completed History Boundary:** The sales history series passed to the forecasting models strictly terminates at the **last complete calendar month** ($M_{-1}$, e.g. September 2026):
   $$\text{History Cutoff} = \text{date\_order} < \text{date\_trunc}('month', \text{CURRENT\_DATE})$$
2. **Current Month Weighting ($w_0$):**
   For as-of date day $d$ in a month with $D$ total days:
   $$w_0 = \frac{D - d}{D} \quad (\text{e.g., as of Oct 8 in a 31-day month: } w_0 = 23/31 \approx 0.7419)$$
3. **Multi-Step Horizon Demand Formulation:**
   Using the 5-step model forecast $[F_1, F_2, F_3, F_4, F_5]$:
   $$\text{Lead Time Demand} = (w_0 \times F_1) + F_2 + F_3 + ((1 - w_0) \times F_4) \equiv 3.0\,\text{months of forward demand}$$
   $$\text{Review Period Demand} = (w_0 \times F_4) + ((1 - w_0) \times F_5) \equiv 1.0\,\text{month of forward demand}$$
   $$\text{Total Operational Horizon Demand} = (w_0 \times F_1) + F_2 + F_3 + F_4 + ((1 - w_0) \times F_5) \equiv 4.0\,\text{months of forward demand}$$

---

## 6. Mentor Regression Case Studies

### 6.1. Group 325-42 (Seasonal Spike vs. False Excess)
- **Problem:** Legacy 6-month average ($6.33\,\text{m}$) caused the system to classify $461.3\,\text{m}$ stock as `excess_stock` despite an upcoming seasonal forecast of $1,292\,\text{m}$.
- **After Task 5:**
  - Forward Horizon Demand = **$958.58\,\text{m}$**
  - Buffered Target = **$1,054.44\,\text{m}$**
  - Inventory Position = **$461.3\,\text{m}$** ($247.1\,\text{m}$ usable $+ 214.2\,\text{m}$ incoming)
  - Result: Action correctly switches to **`purchase`** with **$594\,\text{m}$** suggested replenishment, preventing seasonal stockout.

### 6.2. Group 413-11 (Incoming Stock Double-Ordering Protection)
- **Problem:** Legacy system ignored $1,054.0\,\text{m}$ incoming PO, recommending redundant purchase of $\sim 806\,\text{m}$.
- **After Task 5:**
  - Forward Horizon Demand = $24.7\,\text{m}$, Buffered Target = $27.17\,\text{m}$.
  - Inventory Position = **$1,054.0\,\text{m}$** ($0\,\text{m}$ on-hand $+ 1,054.0\,\text{m}$ incoming).
  - Result: Action remains **`excess_stock` / `hold`** with suggested purchase **`0 m`**, completely eliminating double-ordering risk.

---

## 7. Representative Before/After Examples (Task 9)

| Archetype | Group Name (ID) | 1M FC | Lead-Time Demand | Review-Period Demand | Horizon Demand | Inventory Position | Old Buy Qty (Action) | New Buy Qty (Action) | Key Operational Takeaway |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **High Forecast Understocked** | **394-27** (14403) | 22.0 m | 112.89 m | 287.83 m | 400.72 m | 286.4 m | 0 m (`excess_stock`) | **155 m** (`purchase`) | Seasonal surge detected; prevents stockout |
| **High Forecast Overstocked** | **379-06** (6623) | 187.5 m | 562.50 m | 187.50 m | 750.00 m | 3,228.3 m | 0 m (`excess_stock`) | **0 m** (`excess_stock`) | Healthy surplus safely absorbed |
| **Falling Demand Overstocked** | **1102-27** (11440) | 0.0 m | 25.58 m | 2.91 m | 28.48 m | 32.5 m | 28 m (`review`) | **0 m** (`hold`) | Eliminates over-ordering on fading product |
| **Incoming Stock Absorbed** | **413-11** (16742) | 0.0 m | 18.52 m | 6.18 m | 24.70 m | 1,054.0 m | 0 m (`excess_stock`) | **0 m** (`excess_stock`) | Inbound PO absorbs demand; 0 buy |
| **Dead / Zero Demand** | **18825** (6032) | 0.0 m | 0.00 m | 0.00 m | 0.00 m | 148.3 m | 0 m (`dead_stock`) | **0 m** (`dead_stock`) | Zero target; zero cash tied up |
| **Seasonal Spike Deficit** | **325-42** (859) | 1,292.0 m | 958.58 m | 0.00 m | 958.58 m | 461.3 m | 0 m (`excess_stock`) | **594 m** (`purchase`) | Resolves mentor evidence case |

---

## 8. Top-50 Main-Product Group Validation (Task 8)

Snapshots generated and saved at:
- `backend/data/task5_before_snapshot.csv`
- `backend/data/task5_after_snapshot.csv`

### Metric Summary Across Cohort:

| Metric | Before Task 5 (Legacy 6M Avg) | After Task 5 (Forecast Horizon) | Delta |
| :--- | :---: | :---: | :---: |
| **Groups Needing Purchase ($Q > 0$)** | 2 | 2 | 0 |
| **Groups with Excess Stock** | 13 | 8 | -5 (corrected false excess) |
| **Groups on Hold** | 14 | 19 | +5 (safe coverage) |
| **Groups in Dead Stock** | 15 | 15 | 0 |
| **Total Suggested Purchase Quantity** | **57.0 meters** | **156.0 meters** | **+99.0 meters** (seasonal alignment) |
| **Sum of Reorder Requirements (ROP)** | **1,246.5 meters** | **2,669.98 meters** | Accurately reflects true horizon demand |
| **Groups Forecasting Zero** | 33 | 33 | 0 |
| **Groups with Purchase Quantity Change** | — | **3 groups** | Sized to true forecast |

---

## 9. Test Suite Verification (Task 12)

Comprehensive unit tests implemented in `backend/tests/test_forecast_order_quantity.py`:
1. `test_1_forecast_driven_order_quantity_basic` — **PASS**
2. `test_2_lead_time_and_review_period_separation` — **PASS**
3. `test_3_partial_current_month_weighting` — **PASS**
4. `test_4_incoming_stock_integration_prevents_duplicate_purchase` — **PASS**
5. `test_5_committed_customer_demand_increases_purchase_need` — **PASS**
6. `test_6_zero_forecast_suppresses_purchase` — **PASS**
7. `test_7_excess_stock_classification` — **PASS**
8. `test_8_negative_inventory_position` — **PASS**
9. `test_9_dead_stock_hard_zero` — **PASS**
10. `test_10_mentor_413_11_regression` — **PASS**
11. `test_11_mentor_325_42_regression` — **PASS**

### Test Run Execution Results:
- **Total Tests Run:** **182 tests**
- **Failures:** **0**
- **Errors:** **0**
- **Skipped:** **1**
- **Pass Rate:** **100% (OK)**
- **Runtime:** 7.6 seconds

---

## 10. Odoo Read-Only Verification (Task 13)

Direct query verification against live Odoo PostgreSQL database:
- **0** Writes
- **0** Schema Alterations
- **0** Purchase Orders Created
- **0** RFQs Created
- **0** Reordering Rules / Orderpoint Modifications
- **Database Status:** 100% Read-Only.

---

## 11. Model & Forecast Separation Invariant (Task 11)

- Champion model `trimmed_mean_3` and underlying statistical forecast engines remain **100% unmodified**.
- Task 5 strictly modified the **replenishment requirement layer** that consumes forecast output.

---

## 12. Recommendation for Phase 2 — Task 6

With Task 5 completed and validated:
1. **Ready for Phase 2 — Task 6:** Supplier Minimum Order Quantities (MOQ), Standard Packaging / Roll Length Multiple Rounding, and Order Splitting Constraints.
2. **Next Steps:** Maintain Odoo read-only isolation and apply supplier packaging constraints to the pure forecast-driven purchase quantities.
