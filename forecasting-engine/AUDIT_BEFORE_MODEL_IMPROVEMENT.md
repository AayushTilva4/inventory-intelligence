# Pre-Improvement Forecasting Engine & Benchmark Audit

**Date:** October 7, 2026  
**Status:** Read-Only Audit Complete  
**Scope:** `forecasting-engine/`, `backend/app/forecasting/`, and `backend/app/forecasting/benchmark_v2/`  

---

## 1. Executive Summary

This audit evaluates the existing forecasting architecture, statistical models, evaluation pipelines, and benchmarking infrastructure across the codebase before beginning active model development.

### Core Audit Takeaways:
1. **Quantity Definition Inconsistency:** The forecasting engine forecasts **ordered quantity** (`sale_order_line.product_uom_qty`), whereas `group_demand_service.py` forecasts **delivered quantity** (`sale_order_line.qty_delivered`).
2. **Current Model Accuracy:** Existing baseline models perform poorly on the catalog, exhibiting portfolio WAPEs ranging from **120.3% to 250.7%**. This is driven by intermittent, lumpy fabric demand, uncalibrated parameters, and inappropriate seasonal assumptions.
3. **Evaluation Vulnerabilities:** The legacy V1 pipeline (`evaluation.py` / `pipeline.py`) suffers from selection bias (reporting validation-set errors as model performance), a critical zero-division bug in `wape()` (returning 0.0% error when actual demand is 0), and unstable MASE scaling ($N=1$ lag-12 differences on short series).
4. **Benchmarking Path Forward:** **Benchmark V2 (`backend/app/forecasting/benchmark_v2/`) is mature, leak-free, and suitable as the primary experimental platform**, offering rolling-origin backtesting, 1-to-5 month horizons, demand pattern segmentation, and PostgreSQL persistence.

---

## 2. Current Architecture Overview

```
                                      +-------------------------------+
                                      |   Odoo PostgreSQL Database    |
                                      +---------------+---------------+
                                                      |
                          +---------------------------+---------------------------+
                          |                                                       |
        [sale_order_line.product_uom_qty]                       [sale_order_line.qty_delivered]
                          v                                                       v
       +------------------------------------+                  +------------------------------------+
       |  forecasting-engine (Legacy V1)    |                  | backend/app/odoo/                  |
       |  - src/sales_data.py               |                  | - group_demand_service.py          |
       |  - src/forecasting.py              |                  | - product_group_service.py         |
       +------------------+-----------------+                  +------------------+-----------------+
                          |                                                       |
                          v                                                       v
       +------------------------------------+                  +------------------------------------+
       |  V1 Single 6-Month Walk-Forward    |                  | Group-Level Forecast Service       |
       |  - src/evaluation.py               |                  | - backend/app/forecasting/         |
       |  - src/pipeline.py                 |                  |   group_forecast_service.py        |
       +------------------+-----------------+                  +------------------------------------+
                          |
                          v
       +------------------------------------+
       |  Forecast & Inventory Post-Process |
       |  - src/reorder.py (4x avg demand)  |
       |  - src/trend.py (3m vs 3m moving)  |
       |  - src/dead_stock.py               |
       |  - src/similar_products.py         |
       +------------------+-----------------+
                          |
                          v
+-------------------------------------------------------------------------------------------------------+
|  Benchmark V2 Infrastructure (backend/app/forecasting/benchmark_v2/ & scripts/run_benchmark_v2.py)     |
|  - Multi-origin rolling evaluation (6 origins)                                                        |
|  - Multi-horizon evaluation (1 to 5 months)                                                           |
|  - As-of-origin 8-class demand pattern segmentation                                                   |
|  - In-sample MASE scaling, Pooled & Macro WAPEs, Bias, Under/Over-forecast rates                       |
|  - Persistence in POC PostgreSQL: benchmark_runs, benchmark_forecasts, benchmark_metrics              |
+-------------------------------------------------------------------------------------------------------+
```

### Component Details:
- **`sales_data.py`:** Pulls confirmed sales orders (`so.state = 'sale'`) from Odoo, groups them into monthly frequency (`MS`), and uses `complete_product_series()` to pad missing intermediate months with 0.
- **`forecasting.py`:** Implements 5 baseline models: Previous Month, Moving Average (window=3), Seasonal Naive (season=12), Croston ($\alpha=0.1$), and Exponential Smoothing (Holt-Winters with damped trend).
- **`evaluation.py` & `pipeline.py`:** Runs a single walk-forward test over the last 6 months of data, selects the model with the minimum MASE, and uses that model to forecast month $T+1$.
- **`reorder.py` & `trend.py`:** Computes reorder point using a deterministic heuristic: $(3\text{ months lead time} + 1\text{ month safety stock}) \times \text{6-month trailing average demand}$.

---

## 3. Detailed Audit Findings (Specific Audit Items)

### 3.1. Demand Quantity Forecasted (Requested vs. Delivered)
- **Engine Query (`forecasting-engine/src/sales_data.py:16`):**
  Uses `sol.product_uom_qty AS quantity`. This represents **unconstrained customer requested demand** at order confirmation.
- **Group Service Query (`backend/app/odoo/group_demand_service.py:99`):**
  Uses `SUM(sol.qty_delivered) AS actual`. This represents **fulfilled / shipped quantity**.
- **Assessment:**
  - `product_uom_qty` is the theoretically correct target for unconstrained demand forecasting because `qty_delivered` is censored by stockouts, supply constraints, and logistics delays.
  - However, having SKU-level forecasting modeling *ordered quantity* while group-level forecasting models *delivered quantity* introduces a fundamental discrepancy across the platform.
  - Furthermore, `group_demand_service.py` filters `sol.display_type IS NULL` (excluding section/note rows in Odoo), whereas `sales_data.py` only filters `sol.product_id IS NOT NULL`.

### 3.2. Missing Months and Zero-Demand Handling
- **Series Completion (`sales_data.py:complete_product_series`):**
  - Starts strictly at `product_df["month"].min()`. Products are **not** zero-padded prior to their first recorded sale.
  - Intermediate missing months between first sale and `end_date` are filled with `0.0`.
  - **Trailing Zero Masking Risk:** In `inspect_product.py`, `complete_product_series(product_df)` is called without `end_date`. The series truncates at the product's last sale month, completely masking dormancy and trailing zeros.
  - **Artificial History in `backtest_product.py`:** Hardcodes `HISTORY_START = "2023-08-01"`. Products introduced in 2024 or 2025 have their history prepended with artificial zeros back to August 2023, distorting training metrics.
- **Model Behavior on Zero Demand:**
  - `previous_month`: If the preceding month was 0, it forecasts 0.
  - `croston`: If entire history is 0, returns 0. If there was a single historical order long ago, it continuously predicts a non-zero demand rate indefinitely.
  - `exponential_smoothing`: Fitting Holt-Winters with additive trend/seasonality on intermittent data produces negative values (clipped to 0 via `max(forecast, 0.0)`) and triggers frequent `ConvergenceWarning` and `RuntimeWarning`.

### 3.3. Data Leakage and Model Selection Optimism
- **V1 Selection Bias / Leakage (`pipeline.py:61-65`):**
  - All 5 models are evaluated on the last 6 months of data (`test_size=6`).
  - The model with the lowest MASE on those 6 months is selected as `best_model`.
  - **The reported error metrics (`MAE`, `WAPE`, `MASE`) in the output table are the error metrics of the chosen model evaluated on the very validation set used to choose it.** This introduces classical optimistic selection bias ($E[\min_i X_i] < E[X_i]$).
  - There is no separate out-of-sample holdout to evaluate whether the selection generalizes.
- **Trivial-Zero Optimization (`pipeline.py:79-83`):**
  - When a product is dormant during the 6-month test period (actual demand is 0 each month), `previous_month` forecasts 0 each month.
  - Its MAE is 0.0, WAPE is 0.0, and MASE is 0.0. `pick_best_model()` crowns `previous_month` as the "best model" with a "trivial_zero" tag, even though it possesses zero predictive skill.
- **Benchmark V2 Hygiene (`benchmark_v2/runner.py`):**
  - Benchmark V2 eliminates selection leakage: it evaluates every model independently across multiple rolling origins ($T$) and horizons ($T+1 \dots T+5$).
  - As-of-origin classification (`as_of_origin_pattern`) strictly uses data available up to origin date with stock set to 0 to prevent lookahead leakage.

### 3.4. MASE Calculation, Scaling, and Ranking
- **Small-Sample Scale Instability (`forecasting.py:196` / `metrics.py:31`):**
  ```python
  naive_errors = np.abs(train[season_length:] - train[:-season_length])
  scale = naive_errors.mean()
  ```
  - `season_length = 12` is hardcoded.
  - Minimum required history in V1 is $6 + 12 = 18$ months, meaning `len(train)` can be as short as 12–14 months.
  - When `len(train) == 13`, `len(train[12:] - train[:-12]) == 1`. **The MASE scaling denominator is calculated from a single historical observation difference!**
  - If that single difference is small (e.g., 0.1), MASE explodes. If it is 0, MASE becomes `NaN`.
- **Ranking Equivalence Within a Product:**
  - For a single product, the MASE denominator (`scale`) is identical for all candidate models.
  - Therefore: $\operatorname{argmin}_m(\text{MASE}_m) \equiv \operatorname{argmin}_m(\text{MAE}_m)$.
  - Ranking models per product by MASE is mathematically identical to ranking by MAE.
- **Cross-Product Macro Averaging Risk:**
  - In `backtest_product.py:488` and `all_products_overall_model_scores.csv`, overall MASE is reported as the arithmetic mean of product MASEs.
  - A single product with a near-zero scale (e.g., scale = 0.05, error = 5.0 $\to$ MASE = 100) severely distorts the macro average.

### 3.5. 6-Month Holdout Sufficiency
- **Sample Size Too Small:** 6 monthly observations per product provide insufficient statistical power ($N=6$). A single customer order spike skews the metric for the entire evaluation.
- **Calendar Seasonality Bias:** Evaluating solely on Jan–Jun 2026 tests only one half of the annual calendar cycle.
- **Excessive Catalog Disqualification:** Requiring $6 + 12 = 18$ months of history immediately rejects products introduced in the past 1.5 years, relegating them to crude cold-start fallbacks.
- **Horizon Mismatch with Supply Chain:** The V1 holdout tests 1-step-ahead walk-forward forecasting ($h=1$). The client's procurement lead time is ~3 months. 1-step forecasting does not test cumulative 3-to-5 month horizon accuracy.

### 3.6. Current Model Configurations
| Model | Current Configuration | Hyperparameters / Tuning | Primary Failure Modes |
|---|---|---|---|
| **`previous_month`** | $\hat{y}_{t+h} = y_t$ | None | Severe lag; high error on volatile series; trivially predicts 0 on dormant series. |
| **`moving_average_3`** | $\hat{y}_{t+h} = \text{mean}(y_{t-2:t})$ | Window fixed at 3; no tuning | Lags sharp shifts; smooths away intermittent peaks. |
| **`seasonal_naive`** | $\hat{y}_{t+h} = y_{t+h-12}$ | Seasonality fixed at 12; falls back to lag-1 if $<12$m | Fails completely on non-annual or project-based fabric orders (WAPE > 200%). |
| **`croston`** | Classical Croston ($z/p$) | Smoothing factor fixed at $\alpha=0.1$; no tuning | Upward bias on intermittent demand; fails to decay on obsolete products (no TSB/SBA). |
| **`exponential_smoothing`** | Statsmodels Holt-Winters (`trend="add"`, `damped=True`, `seasonal="add"` if $\ge 24$m) | Additive trend & season; optimizer `optimized=True` | Fits noise; negative predictions clipped at 0; frequent convergence failures on sparse data. |

### 3.7. Where Models Are Underperforming
Based on `all_products_overall_model_scores.csv`:
```csv
model,MAE,WAPE,MASE
previous_month,18.92,156.3%,0.82
moving_average_3,14.57,120.3%,0.63
seasonal_naive,25.83,213.4%,1.03
croston,30.34,250.7%,2.81
exponential_smoothing,24.90,205.7%,0.98
```
- **Every existing model has a portfolio WAPE exceeding 120%.**
- **Intermittent demand mismatch:** Most fabric SKUs exhibit sparse, irregular demand. Holt-Winters and Seasonal Naive assume continuous, periodic patterns and suffer massive penalties on sudden zero-periods.
- **Croston bias:** Classical Croston produces the worst WAPE (250.7%) and MASE (2.81) because it perpetually predicts positive fractional demand across prolonged zero periods.

### 3.8. Evaluation of Benchmark V2 as the Main Experiment Framework
- **Verdict: Highly Recommended.**
- Benchmark V2 (`backend/app/forecasting/benchmark_v2/`):
  - Already implements rolling-origin backtesting (default 6 origins).
  - Already supports multi-step horizons (1 to 5 months out).
  - Categorizes products into 8 operational demand patterns using strict as-of-origin data.
  - Computes robust metrics: MAE, RMSE, Pooled WAPE, Macro WAPE (product and horizon), MASE, Bias, and Stockout/Excess risks.
  - Directly stores run results in PostgreSQL tables (`benchmark_runs`, `benchmark_forecasts`, `benchmark_metrics`).
- **Prerequisites for Benchmark V2 before modeling experiments:**
  1. Refine `calculate_mase_scale()` in `metrics.py` to require at least 24 months before using lag-12 differences, otherwise default to lag-1 naive scaling.
  2. Implement batching or model caching when running with `--all-products` to avoid slow sequential Holt-Winters fitting.

### 3.9. Additional Issues Making Model Comparisons Unreliable
- **Critical Bug in V1 `forecasting.py:wape()` (Line 165):**
  ```python
  denominator = np.sum(np.abs(actual))
  if denominator == 0:
      return 0.0
  ```
  If actual test sales sum to 0, `wape()` returns `0.0` (0% error), regardless of how large the forecast error was. (Fixed in Benchmark V2 to return `NaN`).
- **Heuristic Reorder Point (`reorder.py`):**
  `reorder_point = avg_monthly_demand * 4.0`. Ignores demand variance, forecast errors, lead time variability, and statistical safety stock ($z \times \sigma_L$).
- **Discrepant POC Product Lists:**
  `forecasting-engine/data/poc_products.csv` defines 10 representative POC products (e.g., IDs 16697, 16905, 17402, 9220), whereas `backtest_product.py` hardcodes an older set of 10 IDs (14, 15, 120, etc.).

---

## 4. Ranked Issues (High / Medium / Low)

| Severity | Issue Description | Impact | Location |
|---|---|---|---|---|
| **HIGH** | **Quantity Definition Mismatch** | Engine forecasts ordered qty (`product_uom_qty`), while group demand forecasts delivered qty (`qty_delivered`). | `sales_data.py:16` vs `group_demand_service.py:99` |
| **HIGH** | **V1 Zero-Division Bug in WAPE** | Returns 0.0% error when actual demand is 0, concealing large model misses on dormant products. | `forecasting-engine/src/forecasting.py:165` |
| **HIGH** | **MASE Scaling Instability on Short Series** | Lag-12 scaling on 13–18 month series uses 1 to 6 data points, causing wild swings or `NaN`s in MASE. | `forecasting.py:196`, `metrics.py:31` |
| **HIGH** | **Optimistic Model Selection & No Holdout** | Winning model is chosen on the test set and its test-set score is reported as performance. | `forecasting-engine/src/pipeline.py:61` |
| **HIGH** | **Inadequate 1-Step 6-Month Fixed Evaluation** | Single test split fails to evaluate 3–5 month procurement lead time horizons and ignores seasonality. | `evaluation.py`, `backtest_product.py` |
| **HIGH** | **Severe Baseline Underperformance (WAPE > 120%)** | All 5 baseline models fail on intermittent, lumpy fabric sales. | `forecasting.py` |
| **MEDIUM** | **Trivial-Zero Model Misattribution** | Inactive products select `previous_month` with MAE=0 and are labelled as accurate forecasts. | `pipeline.py:79-84`, `evaluation.py:73` |
| **MEDIUM** | **Uncalibrated Model Parameters** | Fixed $\alpha=0.1$ in Croston; fixed window=3 in MA; fixed season=12 in Holt-Winters. | `forecasting.py:17, 52, 90` |
| **MEDIUM** | **Croston Upward Bias & Lack of SBA/TSB** | Standard Croston over-forecasts intermittent items and fails to decay on dead stock. | `forecasting.py:52` |
| **MEDIUM** | **Holt-Winters Numerical Divergence on Intermittent Data** | Additive trend/seasonality triggers optimization warnings and negative forecasts on sparse data. | `forecasting.py:121-141` |
| **MEDIUM** | **Trailing Zero Truncation in Inspection Tool** | `inspect_product.py` omits `end_date`, hiding recent dormant periods. | `inspect_product.py:22` |
| **MEDIUM** | **Artificial Zero-Padding in Backtest Script** | Hardcoded `HISTORY_START` injects artificial leading zeros into recently created products. | `backtest_product.py:163` |
| **LOW** | **POC Product List Inconsistency** | `poc_products.csv` (10 scenarios) differs from `backtest_product.py` product IDs. | `backtest_product.py:25` |
| **LOW** | **Missing Odoo Line Filter** | `sol.display_type IS NULL` omitted in `sales_data.py`. | `sales_data.py:24` |
| **LOW** | **Static Reorder Multiplier** | `reorder.py` uses fixed 4x average demand instead of service-level safety stock. | `reorder.py:18` |

---

## 5. Recommended Order of Improvements

### Phase 1: Benchmark Framework Standardization & Metric Fixes
1. **Adopt Benchmark V2 as the Single Source of Truth:**
   Retire the legacy single-split script (`backtest_product.py`) for benchmarking in favor of `backend/scripts/run_benchmark_v2.py`.
2. **Fix Metric Calculations:**
   - In `backend/app/forecasting/benchmark_v2/metrics.py`: Require at least 24 months of training data before applying lag-12 seasonal naive scaling in MASE; otherwise fall back to lag-1 naive scaling.
   - In `forecasting-engine/src/forecasting.py`: Align `wape()` to return `float('nan')` instead of `0.0` when actual demand sum is 0.
3. **Harmonize Target Demand Quantity:**
   Establish whether unconstrained customer demand (`sol.product_uom_qty`) or delivered demand (`sol.qty_delivered`) is the organization-wide target. Update `group_demand_service.py` to match.

### Phase 2: Intermittent & Baseline Model Modernization
1. **Enhance Intermittent Demand Baselines:**
   - Add **Syntetos-Boylan Approximation (SBA)** to remove Croston's positive bias.
   - Add **Teunter-Syntetos-Babai (TSB)** method to handle obsolescence / decaying demand.
2. **Add Auto-Selected Smoothing Baselines:**
   - Simple Exponential Smoothing (SES) with optimized $\alpha$.
   - Auto-ETS / Auto-ARIMA selection via AICc on non-intermittent series.
   - Robust median baseline and zero baseline for low/dead stock patterns.

### Phase 3: Demand Classification & Model Routing
1. **Dynamic Model Routing by As-Of-Origin Demand Pattern:**
   Use the 8 demand patterns from `classification.py` to route SKUs:
   - *Intermittent / Lumpy* $\to$ Croston-SBA / TSB.
   - *Fast-Moving / Normal* $\to$ Optimized Holt-Winters / SES / Auto-ETS.
   - *Dead Stock / Falling to 0* $\to$ Zero forecast / TSB decay.
   - *Cold Start* $\to$ Historical analogue model (`similar_products.py`).

### Phase 4: Group & Hierarchical Forecasting Reconciliation
1. **Evaluate Top-Down vs Bottom-Up Accuracy:**
   Use Benchmark V2 to evaluate whether forecasting at the canonical main-product group level and disaggregating by SKU proportions outperforms direct SKU-level forecasting.

### Phase 5: Machine Learning & Exogenous Features (If Required)
1. If statistical baselines plateau, introduce rolling-origin LightGBM / CatBoost models incorporating lag features, catalogue groupings, price points, and promotional indicators.

---

## 6. Exact Files That Will Need Modification Later

| File Path | Planned Modifications |
|---|---|
| `backend/app/forecasting/benchmark_v2/metrics.py` | Add $\ge 24$-month threshold for seasonal MASE scale; standardize macro metric aggregations. |
| `backend/app/forecasting/benchmark_v2/models.py` | Add Croston-SBA, Croston-TSB, SES, and model routing wrappers. |
| `backend/app/forecasting/benchmark_v2/runner.py` | Add batching for catalog-wide runs; add model router evaluation. |
| `backend/app/odoo/group_demand_service.py` | Align demand column (`product_uom_qty` vs `qty_delivered`) with engine. |
| `forecasting-engine/src/forecasting.py` | Fix `wape()` zero-division bug; fix MASE minimum scale threshold; add SBA and TSB algorithms. |
| `forecasting-engine/src/evaluation.py` | Modernize `run_walk_forward()` to support multi-step horizons and eliminate selection leakage. |
| `forecasting-engine/src/pipeline.py` | Integrate pattern-based model routing; eliminate trivial-zero selection bias. |
| `forecasting-engine/src/sales_data.py` | Ensure `sol.display_type IS NULL` is filtered; enforce consistent `end_date` padding. |
| `forecasting-engine/src/reorder.py` | Transition from static multiplier to statistical safety stock ($z \cdot \sigma_{\text{lead time}}$). |
| `forecasting-engine/inspect_product.py` | Pass `end_date` to `complete_product_series()` to properly display trailing zeros. |
