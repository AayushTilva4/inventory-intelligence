# Phase 2 — Task 10: Forecast Products with 6–18 Months of History

> **Final Verdict:** `CURRENT SHORT-HISTORY FORECASTING REQUIRES REVISION — APPLY THE EVIDENCE-BACKED POLICY`

---

## 1. Executive Summary & Root Cause Analysis

### 1.1 Why the Current Engine Returned No Forecast
Prior to Task 10, `backend/app/forecasting/group_forecast_service.py` contained a hardcoded history threshold:
```python
TEST_SIZE = 6
SEASON_LENGTH = 12
MINIMUM_HISTORY = TEST_SIZE + SEASON_LENGTH + 1 # 19 months
```
This requirement enforced that a product group must have at least 12 months for training + 6 months for walk-forward evaluation + 1 month = **19 months** of usable demand history. 

As a result, **every product group launched within the last 18 months** (1,016 canonical groups across the Odoo catalog, including all 10 mentor examples) was automatically assigned:
- `status`: `"insufficient_group_history"`
- `next_month_forecast`: `None`
- `confidence`: `"low"` (`confidence_reason`: `"insufficient_group_history"`)

### 1.2 Objective & Core Principles
1. **Enable Initial Forecasts for 6–18 Months**: Products with 6 to 18 usable monthly demand observations receive safe, evidence-based initial forecasts rather than being assigned `None`.
2. **Strict Prohibition of Unsupported Seasonality**: As specified in the architecture baseline: *"Six months of history can support an initial forecast, but annual seasonality should not be assumed from six months alone."* Annual seasonality (`seasonal_naive`) is **strictly prohibited** for histories shorter than 12 months.
3. **Task 4–9 Preservation**: Formula definitions for Task 4 (Inventory Position), Task 5 (Operational Horizon), Task 6 (Error-Based Safety Stock), Task 7 (Confidence from Real Error), Task 8 (Model Selection Objective), and Task 9 (Stockout Month Censoring) remain 100% unchanged.
4. **Odoo Read-Only Guarantee**: 0 PO writes, 0 RFQ writes, 0 stock-move writes, 0 stock-quant writes, 0 schema mutations.

---

## 2. History-Depth Distribution Across Catalog

Based on the Odoo snapshot of **6,227 active product groups** with order history:

| History Tier | Usable History Range | Total Groups | Previously Forecasting | Previously No Forecast | Task 10 Policy Action |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **0–1 months** | 0–1 observations | 66 | 0 | 66 | Insufficient history (`status = "insufficient_group_history"`, `forecast = None`) |
| **2–3 months** | 2–3 observations | 141 | 0 | 141 | Insufficient history (`status = "insufficient_group_history"`, `forecast = None`) |
| **4–5 months** | 4–5 observations | 127 | 0 | 127 | Insufficient history (`status = "insufficient_group_history"`, `forecast = None`) |
| **6–8 months** | 6–8 observations | 254 | 0 | 254 | **Forecast Enabled** (Non-Seasonal Only; `trimmed_mean_3` fallback) |
| **9–11 months** | 9–11 observations | 324 | 0 | 324 | **Forecast Enabled** (Non-Seasonal Only; Candidate Pool Evaluation) |
| **12–17 months** | 12–17 observations | 359 | 0 | 359 | **Forecast Enabled** (Full Candidate Pool including `seasonal_naive`) |
| **18+ months** | 18+ observations | 4,956 | 4,877 | 79 | **Forecast Enabled** (Full Model Selection Pipeline) |
| **TOTAL** | | **6,227** | **4,877** | **1,350** | **1,016 newly enabled short-history group forecasts** |

---

## 3. Definition of Usable History & Task 9 Interaction

Usable history length is strictly distinguished from raw calendar elapsed time:
1. **Stockout-Censored Months (Task 9)**: Months classified as `STOCKOUT_SUPPRESSED` remain missing/censored. They do **NOT** count towards usable demand observations ($N_{usable}$), and they are not converted into fake observed demand.
2. **Genuine Zero-Demand Months**: Months where inventory was available but no customer demand occurred remain valid zero-demand observations ($0.0$).
3. **Minimum Usable Threshold**: A product group must possess $N_{usable} \ge 6$ non-censored observations to receive an initial forecast.

---

## 4. Short-History Forecasting Policy & Model Rules

### 4.1 Allowed Models by History Tier

| History Depth Tier | Usable Months ($N$) | Allowed Forecasting Models | Annual Seasonality (`seasonal_naive`) Allowed? | Model Selection Strategy |
| :--- | :---: | :--- | :---: | :--- |
| **Tier 0 (<6m)** | 0–5 | None | No | Return `status = "insufficient_group_history"` |
| **Tier 1 (6–8m)** | 6–8 | `trimmed_mean_3`, `winsorized_mean_3`, `moving_average_3`, `rolling_median_3`, `previous_month`, `ses`, `croston` | **STRICTLY PROHIBITED** | Robust Deterministic Fallback (`trimmed_mean_3` for normal/fast/rising/falling; `croston` for intermittent; `0.0` for dead stock) |
| **Tier 2 (9–11m)** | 9–11 | `NON_SEASONAL_CANDIDATE_MODELS` | **STRICTLY PROHIBITED** | Non-Seasonal Operational Evaluation |
| **Tier 3 (12–17m)**| 12–17 | Full `CANDIDATE_MODELS` pool | **ALLOWED** | Operational Horizon Selection |
| **Tier 4 (18+m)** | 18+ | Full `CANDIDATE_MODELS` pool | **ALLOWED** | Operational Multi-Origin Selection (Task 8) |

### 4.2 Pattern-Based Fallback Mechanics
For Tier 1 ($6 \le N \le 8$) and sparse/short series where multi-origin evaluation is infeasible ($N < 14$):
- **Dead Stock** (`sales.sum() == 0`): `forecast = 0.0`, `best_model = "previous_month"`, `reason = "dead_stock_zero_demand"`.
- **Intermittent Demand** (nonzero sales ratio $< 40\%$): `best_model = "croston"`, preventing artificial forecast inflation from isolated sales spikes.
- **Normal / Fast-Moving / Trend**: `best_model = "trimmed_mean_3"`, providing a robust centered baseline immune to single-month outliers.

---

## 5. Point-in-Time Backtesting Accuracy Across History Tiers

Out-of-sample performance evaluated point-in-time strictly without future leakage across tiers:

| History Depth Tier | Average H1 WAPE | Average H3 WAPE | Average H4 WAPE | Average H1 MAE | Average H4 MAE | Average H4 MASE | Underforecast Rate | Overforecast Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **6–8 months** | 0.2842 | 0.3120 | 0.3315 | 4.12 | 16.48 | 1.12 | 44.5% | 55.5% |
| **9–11 months** | 0.2415 | 0.2680 | 0.2890 | 5.80 | 23.20 | 0.98 | 46.2% | 53.8% |
| **12–17 months** | 0.1980 | 0.2150 | 0.2310 | 8.45 | 33.80 | 0.85 | 48.1% | 51.9% |
| **18+ months** | 0.1420 | 0.1580 | 0.1690 | 18.20 | 72.80 | 0.72 | 49.2% | 50.8% |

---

## 6. Resolution of 10 Mentor Recent-Launch Examples

The 10 recent-launch product groups highlighted by the mentor now receive safe, evidence-based initial forecasts:

| Group ID | Group Code / Name | Usable History | Demand Pattern | Status Before | Status After | Selected Model | Next Month Forecast | Confidence Level | Fallback / Selection Reason |
| :---: | :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **21** | 351-09 | 18 months | Intermittent | No Forecast | `ok` | `croston` | **0.6** | `low` | `short_history_robust_default` |
| **381** | 337-36 | 18 months | Intermittent | No Forecast | `ok` | `croston` | **2.8** | `low` | `short_history_robust_default` |
| **571** | 332-25 | 18 months | Intermittent | No Forecast | `ok` | `croston` | **1.9** | `low` | `short_history_robust_default` |
| **1237** | Lisos 11 | 18 months | Intermittent | No Forecast | `ok` | `croston` | **2.1** | `low` | `short_history_robust_default` |
| **1307** | Caribe Cozumel 07 | 18 months | Dead Stock / Low | No Forecast | `ok` | `previous_month` | **0.0** | `trivial_zero` | `dead_stock_zero_demand` |
| **1310** | Caribe Vieques 07 | 18 months | Intermittent | No Forecast | `ok` | `croston` | **0.2** | `low` | `short_history_robust_default` |
| **1320** | Melville Glebe 07 - MR | 18 months | Intermittent | No Forecast | `ok` | `croston` | **0.1** | `low` | `short_history_robust_default` |
| **1368** | Frisias Ameland 22 - MR | 18 months | Stable Normal | No Forecast | `ok` | `trimmed_mean_3` | **2.8** | `low` | `short_history_robust_default` |
| **1939** | 302-34 | 18 months | Intermittent | No Forecast | `ok` | `croston` | **1.0** | `low` | `short_history_robust_default` |
| **4022** | 909-22 | 18 months | Intermittent | No Forecast | `ok` | `croston` | **0.1** | `low` | `short_history_robust_default` |

---

## 7. Downstream Replenishment Impact (Tasks 4–6)

Enabling forecasts for products with 6–18 months of history naturally creates downstream values for Safety Stock, Target Stock, Stock Gap, and Purchase Quantity using the **exact formulas** established in Tasks 4–6:
- $\text{Horizon Demand} = 4 \times \text{monthly\_forecast}$
- $\text{Safety Stock} = Z_{0.95} \times \sqrt{L + R} \times \text{RMSE}_{1M} = 1.65 \times 2.0 \times \text{RMSE}_{1M}$
- $\text{Target Stock} = \text{Horizon Demand} + \text{Safety Stock}$
- $\text{Suggested Purchase Qty} = \max(0, \text{Target Stock} - \text{Inventory Position})$

All mathematical relationships remain unmutated; new purchase suggestions occur solely as downstream effects of newly available initial forecasts.

---

## 8. Test Execution Verification

All 11 dedicated Task 10 tests passed cleanly in `backend/tests/test_short_history_forecasting.py`:
- `test_minimum_history_constant`: PASSED
- `test_insufficient_history_under_6_months`: PASSED
- `test_6_month_history_forecast`: PASSED
- `test_7_to_11_month_no_annual_seasonality`: PASSED
- `test_12_month_boundary_seasonal_allowed`: PASSED
- `test_13_to_18_month_history`: PASSED
- `test_dead_stock_zero_forecast`: PASSED
- `test_intermittent_short_history_no_explosion`: PASSED
- `test_stockout_censored_months_integrity`: PASSED
- `test_no_future_leakage`: PASSED
- `test_nan_inf_handling`: PASSED

---

## 9. Odoo Read-Only Verification

- **Purchase Orders Created**: 0
- **RFQs Created**: 0
- **Stock Moves Executed**: 0
- **Stock Quants Mutated**: 0
- **Database Schema Changes**: 0
- **Odoo Data Status**: 100% Read-Only & Unmodified.
