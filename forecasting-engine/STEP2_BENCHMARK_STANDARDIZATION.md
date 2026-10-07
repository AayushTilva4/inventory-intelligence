# Step 2: Benchmark Standardization & Demand Target

**Date:** October 7, 2026  
**Status:** Completed  
**Scope:** `forecasting-engine/`, `backend/app/forecasting/benchmark_v2/`, and `backend/tests/`  

---

## 1. Executive Summary

In Step 2 of the forecasting improvement project, we performed two critical tasks:
1. **Investigated the Demand Target Mismatch:** Analyzed unconstrained requested demand (`sol.product_uom_qty`) vs. fulfilled delivery (`sol.qty_delivered`) on live Odoo sales data across 10 POC products, the top 100 active products, and the full catalog (7,482 SKUs). Formally established `product_uom_qty` as the canonical target for replenishment forecasting.
2. **Standardized and Stabilized Benchmark V2:** Fixed the small-sample MASE scaling instability, verified undefined WAPE handling on zero actuals, enforced strict as-of-origin temporal hygiene, and added automated unit tests covering 13m, 18m, 24m, intermittent, constant-zero, and zero-demand edge cases.

**Production Forecasting Guarantee:** Zero production forecasting files were altered (`forecasting.py`, `pipeline.py`, `evaluation.py`, `sales_data.py`, and `forecast_service.py` remain untouched). No database schemas or Odoo data were modified.

---

## 2. Demand Target Investigation & Canonical Conclusion

### 2.1. Audit Results Across Cohorts
- **Full Catalog (7,482 products, 53,589 product-months):**
  - Total Ordered: **2,049,695.52 units**
  - Total Delivered: **1,959,769.13 units**
  - **Net Unfulfilled Gap: 89,926.39 units (4.39% unfulfilled)**
  - Fulfillment Ratio: **95.61%**
  - Months with Ordered > 0 but Delivered = 0: **691 months**
  - Months with Partial Fulfillment: **3,337 months**
  - Months with Delivered > Ordered: **0 months (0.00%)**
- **Top 100 Active Products (2,828 product-months):**
  - Total Ordered: **475,078.14 units**
  - Total Delivered: **452,859.60 units**
  - **Net Unfulfilled Gap: 22,218.54 units (4.68% unfulfilled)**
  - Fast-moving cohort fulfillment drops to **93.71%**, with delivery shortfalls occurring in **16.83% of active months**.
- **10 POC Products (83 product-months):**
  - Total Ordered: **8,911.80 units**
  - Total Delivered: **8,298.30 units**
  - **Net Unfulfilled Gap: 613.50 units (6.88% unfulfilled)**
  - Product `16697` (`413-11`) suffered a 462.0-unit shortfall across 6 months, including 1 month completely unfulfilled due to warehouse stockouts.

### 2.2. Canonical Target Decision
**`sol.product_uom_qty` (Ordered / Requested Demand) is the canonical target for Inventory Intelligence.**  
Training on `qty_delivered` would introduce **stockout censoring**: during historical stockouts, delivered quantity drops, falsely teaching the model that customer demand declined and triggering smaller reorder quantities in a vicious cycle. Full analysis documented in [DEMAND_TARGET_ANALYSIS.md](file:///e:/Agent/forecasting-engine/DEMAND_TARGET_ANALYSIS.md).

---

## 3. Benchmark V2 Standardization & Correctness Fixes

### 3.1. MASE Scaling Instability Fix
- **Prior Issue:** The benchmark attempted a 12-month seasonal scale (`mean(|y_t - y_{t-12}|)`) whenever `len(history) > 12`. On a 13-month series, the scale was computed from a **single difference point** ($13 - 12 = 1$). If that single pair differed by a tiny amount, MASE exploded; if they were equal, scale was 0 and MASE became `NaN`.
- **New Rule Implemented in `metrics.py`:**
  ```python
  def calculate_mase_scale(
      train_history: Optional[Sequence[float]],
      season_length: int = 12,
      min_seasonal_history: int = 24,
  ) -> Optional[float]:
  ```
  1. A 12-month seasonal naive scale is **strictly prohibited** unless `len(train_history) >= 24` (at least 2 full seasonal cycles $\to \ge 12$ seasonal differences).
  2. For series with $< 24$ months of history (e.g., 13–23 months), the benchmark falls back to the stable **lag-1 naive scale** (`mean(|y_t - y_{t-1}|)`).
  3. Never uses future observations when computing the scale.
  4. Returns `None` for constant series (where all differences are 0) or histories $\le 1$.

### 3.2. WAPE Zero-Demand Behavior Verified
- When total ground-truth demand in an evaluation window is 0 (`sum(actual) == 0`):
  - WAPE is mathematically undefined (division by zero).
  - Recorded as `None` / `NaN`, **never `0.0`**.
  - Verified that macro WAPE across products/horizons does not treat zero-demand windows as 0.0% error, preventing artificial model score inflation.
  - MAE, RMSE, Bias, and error metrics remain fully available.

### 3.3. As-Of-Origin Temporal Hygiene Verified
- Benchmark V2 enforces strict point-in-time isolation:
  1. **Classification:** Computed strictly on `train_slice` with `stock_on_hand=0.0` to eliminate lookahead leakage from future sales or current stock.
  2. **Scaling:** Computed strictly in-sample on `train_series`.
  3. **Fitting:** Models receive history strictly $\le \text{origin\_date}$.
  4. **Evaluation:** Multi-step forecasts ($h=1 \dots 5$) evaluated strictly against observable future ground truth.

---

## 4. Verification & Unit Tests

The test suite in [backend/tests/test_benchmark_v2_correctness.py](file:///e:/Agent/backend/tests/test_benchmark_v2_correctness.py) was expanded and verified:

1. **13-Month History Test (`test_mase_13_month_history_uses_lag1`):** Verified that lag-12 scale (1 difference) is rejected, and stable lag-1 scale (12 differences) is used.
2. **18-Month History Test (`test_mase_18_month_history_uses_lag1`):** Verified that lag-12 scale (6 differences) is rejected, and stable lag-1 scale (17 differences) is used.
3. **24-Month History Test (`test_mase_24_month_history_uses_seasonal_lag12`):** Verified that series with 24 months correctly uses lag-12 seasonal differences (12 differences).
4. **Constant Zero Series Test (`test_mase_constant_zero_series_is_undefined`):** Verified scale is `None` and MASE is `None` without crashing.
5. **Constant Nonzero Series Test (`test_mase_constant_nonzero_training_history_is_undefined`):** Verified scale is `None`.
6. **Intermittent Series Test (`test_mase_intermittent_series_computes_valid_scale`):** Verified valid lag-1 scale and positive MASE.
7. **All-Zero Evaluation Window Test (`test_wape_all_zero_actual_demand_is_undefined`):** Verified WAPE is `None`, not 0.0 or 1.0.
8. **Macro WAPE Integrity Test (`test_wape_zero_demand_does_not_artificially_improve_macro_score`):** Verified zero-demand items do not artificially improve macro portfolio WAPE.
9. **Leakage Prevention Tests (`test_benchmark_v2_leakage.py` & `TestHistoricalClassification`):** Verified future data alterations do not leak into origin forecasts or classification.

**Test Execution Result:** 15/15 tests passing cleanly in 0.42s.

---

## 5. Before vs. After Benchmark Metrics (10 POC Products)

Run command: `python scripts/run_benchmark_v2.py --poc-only --no-db` (6 origins, horizons 1–5, 1,200 evaluations)

### 5.1. Overall Model Comparison
| Model | MAE | Pooled WAPE | Macro WAPE (Prod) | Macro WAPE (Horiz) | MASE (Before) | MASE (After) | RMSE | Bias | Under-forecast Rate | Over-forecast Rate |
|---|---|---|---|---|---|---|---|---|---|---|
| **`moving_average_3`** | 32.1657 | 0.7287 | 2.0129 | 0.7399 | 2.3247 | **2.5387** | 92.6298 | -8.6691 | 22.92% | 46.25% |
| **`exponential_smoothing`** | 32.2306 | 0.7301 | 1.7123 | 0.7425 | 2.2089 | **2.4218** | 95.4093 | -8.4719 | 26.25% | 32.92% |
| **`previous_month`** | 32.8558 | 0.7443 | 1.9248 | 0.7560 | 2.3939 | **2.6081** | 94.6533 | -9.8575 | 24.17% | 31.67% |
| **`croston`** | 40.5658 | 0.9190 | 92.0892 | 0.9345 | 6.0359 | **6.2784** | 95.1059 | +6.9756 | 13.75% | 86.25% |
| **`seasonal_naive`** | 60.7533 | 1.3763 | 30.1125 | 1.3944 | 2.1504 | **2.3103** | 169.7805 | +7.9075 | 21.67% | 25.83% |

### 5.2. Impact on Pattern-Level MASE
- **Fast Moving:** In the before benchmark, MASE was 0.4616. With stable lag-1 scaling on 13–23m histories, MASE dropped to **0.2732**, reflecting true transition variance rather than artificial 1-point seasonal denominators.
- **Intermittent & Rising/Falling:** Scaled errors are now standardized against consistent historical transitions rather than volatile single-observation differences.

---

## 6. Files Changed in Step 2

| File Path | Description of Change | Production Impact |
|---|---|---|
| `backend/app/forecasting/benchmark_v2/metrics.py` | Added `min_seasonal_history=24` requirement to `calculate_mase_scale()` and `calculate_metrics()`. | Benchmark V2 only. No production forecasting impact. |
| `backend/tests/test_benchmark_v2_correctness.py` | Added test cases for 13m, 18m, 24m histories, constant-zero, intermittent, and zero-demand WAPE. | Test suite only. |
| `forecasting-engine/DEMAND_TARGET_ANALYSIS.md` | Quantitative investigation report comparing `product_uom_qty` vs `qty_delivered`. | Documentation only. |
| `forecasting-engine/STEP2_BENCHMARK_STANDARDIZATION.md` | Summary report of Step 2 benchmark standardization. | Documentation only. |
