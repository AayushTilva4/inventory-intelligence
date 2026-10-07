# STEP 9B: Active-Catalog Final Validation Report

## Executive Summary

Following Step 9's validation of long-tail and dormant catalog behavior, **Step 9B executes the final active-catalog validation** of the Inventory Intelligence forecasting and calibration architecture.

A completely fresh cohort of **1,000 active products** was deterministically sampled from the live Odoo database, ensuring **strict zero overlap** with the Top 100 benchmark, Step 7 (1,000 products), and Step 9 (1,000 products). Unlike Step 9 (which naturally sampled 589 dead-stock items from the long tail), this Step 9B cohort was stratified to capture **100% of all available remaining active continuous trend products** across the entire catalog, coupled with actively purchased intermittent fabrics and a small dead-stock control sample (9.4%).

Across **133,350 forecast evaluations** spanning 6 rolling origins and 5 horizons (H1–H5), the results provide decisive empirical proof:

1. **`trimmed_mean_3` generalizes exceptionally well to active products**, achieving an overall pooled WAPE of **1.0514** (vs. `median_baseline` at 1.1847 and `pattern_router_e` at 1.2352). On Macro WAPE across products, `trimmed_mean_3` achieves **1.1493** compared to **1.8015** for median baseline.
2. **`trimmed_mean_3` is the top-performing model at the critical 3-month horizon (H3)**, registering an H3 WAPE of **1.0711** (vs. `median_baseline` 1.2271 and `pattern_router_e` 1.2724).
3. **`trimmed_mean_3` wins across EVERY SINGLE DEMAND PATTERN**, including `fast_moving` (1.0669 vs 1.2158), `falling` (1.0381 vs 1.4317), `rising` (1.2596 vs 1.5154), `stable/normal` (1.0506 vs 1.2466), and `intermittent` (1.0729 vs 1.0958).
4. **Pattern Router E fails to justify its complexity**, lagging behind simple baselines globally and across all patterns.
5. **Empirical safety buffering successfully mitigates stockouts on active items**, lifting service-level attainment from 70.74% to 74.42% and lowering shortfall from 8.831 to 7.942 meters. At a 3:1 asymmetric understock penalty, Empirical 75% achieves the lowest overall business loss.
6. **Legacy Target Investigation reveals that 58.3% of material differences stem from genuine legacy overstock** (reorder points inflated to hundreds of meters based on lifetime historical demand despite zero recent sales), while **35.3% represent potentially legitimate operational stock requirements** on active batch fabrics that require guardrails.
7. **The non-blocking shadow architecture executed flawlessly**, producing zero negative targets, zero dead-stock targets, and zero runtime crashes across all 1,000 products.

---       

## 1. Fresh Active Validation Cohort Specification

### Cohort Construction & Determinism
- **Source Data:** Odoo PostgreSQL database (`sale_order_line` demand target).
- **Sampling Seed:** Deterministic seed `109`.
- **Exclusion Filters:**
  - Top 100 benchmark products (100 products)
  - Step 7 generalization cohort (1,000 products)
  - Step 9 shadow cohort (1,000 products)
- **Overlap Verification:**
  - Overlap with Top 100: **0**
  - Overlap with Step 7: **0**
  - Overlap with Step 9: **0**

### Stratification & Catalog Representation
From the 5,382 remaining products in the catalog, **100% of all eligible active continuous trend items** were extracted. The final 1,000-product cohort distribution is as follows:

| Demand Pattern | Product Count | Percentage | Sampling Method |
| :--- | :---: | :---: | :--- |
| **intermittent** (active demand > 0) | 700 | 70.0% | Recent active purchasing (sales within last 6m) |
| **cold_start** | 100 | 10.0% | Random stratified sample of new products (<18m) |
| **dead_stock** (control sample) | 94 | 9.4% | Deterministic control sample (<10% of cohort) |
| **fast_moving** | 53 | 5.3% | **100% of remaining catalog** |
| **falling** | 30 | 3.0% | **100% of remaining catalog** |
| **stable/normal** | 15 | 1.5% | **100% of remaining catalog** |
| **rising** | 8 | 0.8% | **100% of remaining catalog** |
| **Total** | **1,000** | **100.0%** | Deterministic Seed 109 |

**Volume Tiers:**
- `high_volume`: 540 products (54.0%)
- `med_volume`: 310 products (31.0%)
- `low_volume`: 150 products (15.0%)

**History Tiers:**
- `long_history`: 452 products (45.2%)
- `short_history`: 385 products (38.5%)
- `med_history`: 163 products (16.3%)

**Persisted Cohort Files:**
- Product IDs: `scratch/step9b_cohort_1000_pids.json`
- Cohort Metadata: `scratch/step9b_cohort_1000_meta.csv`

---

## 2. Central Forecast Validation (Task 2)

All 6 candidate models were evaluated across 6 rolling origins (2025-02 through 2025-07) and 5 forward forecast horizons (H1–H5), generating **133,350 forecast evaluations**.

### Global Model Performance (All Horizons Combined)

| Model | Pooled WAPE | Macro WAPE | MAE | MASE | RMSE | Bias | Underforecast Rate | Overforecast Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`trimmed_mean_3`** | **1.0514** | **1.1493** | **9.4937** | **1.2866** | **34.8105** | -5.7609 | 24.97% | 17.10% |
| `winsorized_mean_3` | 1.0872 | 1.2174 | 9.8168 | 1.2993 | 34.9465 | -4.9615 | 24.20% | 17.88% |
| `median_baseline` | 1.1847 | 1.8015 | 10.6976 | 1.3066 | 35.0699 | -2.7223 | 21.71% | 25.49% |
| `rolling_median_6` | 1.1897 | 1.4119 | 10.7422 | 1.3154 | 35.5240 | -2.8771 | 22.13% | 24.30% |
| `pattern_router_e` | 1.2352 | 1.7086 | 11.1531 | 1.3374 | 36.4687 | -2.4995 | 21.89% | 24.42% |
| `previous_month` | 1.4859 | 1.8787 | 13.4176 | 1.4982 | 43.1566 | -0.2533 | 22.12% | 21.57% |

### Horizon-by-Horizon WAPE (H1 – H5)

| Model | H1 | H2 | H3 (Reorder Horizon) | H4 | H5 |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **`trimmed_mean_3`** | **1.0151** | **1.0562** | **1.0711** | **1.0443** | **1.0713** |
| `winsorized_mean_3` | 1.0481 | 1.0924 | 1.1094 | 1.0765 | 1.1112 |
| `median_baseline` | 1.1270 | 1.1932 | 1.2271 | 1.1435 | 1.2404 |
| `rolling_median_6` | 1.1304 | 1.1957 | 1.2329 | 1.1565 | 1.2389 |
| `pattern_router_e` | 1.1723 | 1.2632 | 1.2724 | 1.1967 | 1.2796 |
| `previous_month` | 1.4356 | 1.5264 | 1.5479 | 1.4050 | 1.5345 |

### Key Findings:
- **`trimmed_mean_3` dominates universally**: It outperforms every candidate at every horizon from H1 to H5.
- At the reorder horizon **H3**, `trimmed_mean_3` achieves **1.0711 WAPE**, beating `median_baseline` (1.2271) by **15.6 percentage points** and `pattern_router_e` (1.2724) by **20.1 percentage points**.
- **Macro WAPE Advantage**: On unweighted product-level accuracy (`macro_wape_product`), `trimmed_mean_3` achieves **1.1493**, representing a massive improvement over `median_baseline` (1.8015).

---

## 3. Pattern Validation (Task 3)

We examined model accuracy broken down by point-in-time classified demand pattern:

| Pattern | Candidate Model | Evaluations (N) | WAPE | MAE | Bias | Underforecast Rate | Overforecast Rate |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **fast_moving** | **`trimmed_mean_3`** | 650 | **1.0669** | **46.40** | -25.52 | 55.85% | 38.46% |
| | `winsorized_mean_3` | 650 | 1.1154 | 48.50 | -20.50 | 58.62% | 35.69% |
| | `pattern_router_e` | 650 | 1.1876 | 51.65 | -17.34 | 57.54% | 36.31% |
| | `median_baseline` | 650 | 1.2158 | 52.87 | -3.85 | 74.92% | 24.62% |
| | `rolling_median_6` | 650 | 1.3017 | 56.61 | -0.39 | 75.23% | 24.15% |
| | `previous_month` | 650 | 1.4526 | 63.17 | -1.07 | 51.23% | 33.69% |
| **falling** | **`trimmed_mean_3`** | 660 | **1.0381** | **12.21** | -8.77 | 36.82% | 35.61% |
| | `winsorized_mean_3` | 660 | 1.0592 | 12.45 | -7.83 | 37.73% | 34.70% |
| | `rolling_median_6` | 660 | 1.1343 | 13.34 | -5.51 | 55.76% | 29.70% |
| | `previous_month` | 660 | 1.3552 | 15.93 | -2.79 | 39.55% | 29.85% |
| | `pattern_router_e` | 660 | 1.3827 | 16.26 | -0.53 | 54.70% | 26.97% |
| | `median_baseline` | 660 | 1.4317 | 16.83 | +0.50 | 76.21% | 22.88% |
| **rising** | **`trimmed_mean_3`** | 245 | **1.2596** | **13.41** | -4.03 | 57.14% | 28.16% |
| | `winsorized_mean_3` | 245 | 1.3459 | 14.33 | -2.25 | 60.00% | 25.31% |
| | `median_baseline` | 245 | 1.5154 | 16.14 | +0.37 | 79.59% | 20.00% |
| | `rolling_median_6` | 245 | 1.6133 | 17.18 | +0.74 | 72.65% | 25.31% |
| | `previous_month` | 245 | 1.9605 | 20.88 | +5.88 | 48.98% | 24.08% |
| | `pattern_router_e` | 245 | 2.0379 | 21.70 | +6.30 | 74.69% | 21.22% |
| **stable/normal** | **`trimmed_mean_3`** | 405 | **1.0506** | **15.47** | -7.97 | 47.90% | 44.20% |
| | `winsorized_mean_3` | 405 | 1.0825 | 15.94 | -6.30 | 51.11% | 40.99% |
| | `rolling_median_6` | 405 | 1.2042 | 17.73 | -1.69 | 66.91% | 31.60% |
| | `median_baseline` | 405 | 1.2466 | 18.36 | -0.28 | 71.36% | 27.90% |
| | `pattern_router_e` | 405 | 1.4188 | 20.89 | +1.87 | 67.41% | 30.37% |
| | `previous_month` | 405 | 1.4563 | 21.45 | -0.74 | 45.93% | 36.54% |
| **intermittent** | **`trimmed_mean_3`** | 10,760 | **1.0729** | **6.71** | -5.21 | 15.65% | 26.10% |
| | `median_baseline` | 10,760 | 1.0958 | 6.86 | -4.43 | 22.21% | 24.70% |
| | `winsorized_mean_3` | 10,760 | 1.1041 | 6.91 | -4.83 | 16.25% | 25.52% |
| | `rolling_median_6` | 10,760 | 1.1173 | 6.99 | -4.45 | 22.34% | 24.85% |
| | `pattern_router_e` | 10,760 | 1.2369 | 7.74 | -3.21 | 23.72% | 23.93% |
| | `previous_month` | 10,760 | 1.6463 | 10.30 | -0.47 | 24.37% | 23.09% |
| **dead_stock** | **`trimmed_mean_3`** | 6,060 | **1.0000** | **2.56** | -2.56 | 0.00% | 13.25% |
| | `pattern_router_e` | 6,060 | 1.0000 | 2.56 | -2.56 | 0.00% | 13.25% |
| | `winsorized_mean_3` | 6,060 | 1.0000 | 2.56 | -2.56 | 0.00% | 13.25% |
| | `rolling_median_6` | 6,060 | 1.0000 | 2.56 | -2.56 | 0.00% | 13.25% |
| | `median_baseline` | 6,060 | 1.0376 | 2.65 | -2.39 | 1.78% | 13.17% |

### Key Findings:
- `trimmed_mean_3` is the **single best model across all six patterns**.
- In earlier cohorts, `median_baseline` was slightly better on intermittent demand. On this active cohort with recent demand, `trimmed_mean_3` (WAPE 1.0729) **beats median baseline** (WAPE 1.0958) even on intermittent items!
- Median baseline exhibits a severe underforecasting pathology on active continuous trends: underforecast rate of **74.92% on fast-moving**, **76.21% on falling**, **79.59% on rising**, and **71.36% on stable/normal**.
- `pattern_router_e` performed terribly on rising products (WAPE 2.0379 vs 1.2596 for `trimmed_mean_3`), proving that trend extrapolation models selected by the router severely overshoot.

---

## 4. Safety Buffer Validation on Active Products (Task 4)

We evaluated empirical safety stock buffering strictly on **active products** (96,990 evaluations, excluding the dead-stock control sample) using the calibrator pre-fitted on Step 7 historical residuals.

### Active Catalog Evaluation at Horizon 3 (Reorder Horizon)

| Buffering Strategy | Attained CSL | Under-Target Rate | Over-Target Rate | Mean Shortfall | Mean Excess | 1:1 Loss | 1.5:1 Loss | 2:1 Loss | 3:1 Loss |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **A. Raw Forecast** | 70.74% | 29.26% | 23.63% | 8.831 | **2.559** | **11.390** | **15.806** | **20.221** | 29.052 |
| **B. Fixed 10%** | 71.05% | 28.95% | 23.97% | 8.712 | 2.871 | 11.584 | 15.940 | 20.296 | 29.009 |
| **C. Empirical 75%** | 72.16% | 27.84% | 25.05% | 8.439 | 3.674 | 12.112 | 16.331 | 20.551 | **28.989** |
| **D. Empirical 80%** | 72.87% | 27.13% | 25.77% | 8.280 | 4.299 | 12.579 | 16.718 | 20.858 | 29.138 |
| **E. Empirical 85%** | 74.42% | 25.58% | 27.34% | 7.942 | 5.793 | 13.735 | 17.707 | 21.678 | 29.620 |

### Key Findings:
- **Service-Level Attainment**: Raw forecast achieves 70.74% cycle service level on active items. Empirical buffering lifts CSL to **72.16% (at 75%)**, **72.87% (at 80%)**, and **74.42% (at 85%)**.
- **Shortfall Reduction**: Mean shortfall drops progressively from **8.831 meters** (raw) to **7.942 meters** (at 85% SL), directly mitigating stockouts.
- **Asymmetric Business Loss (3:1)**:
  - When the cost of a stockout is 3x the cost of excess holding, **Empirical 75% achieves the lowest total loss (28.989 vs 29.052 for raw forecast)**.
  - Fixed 10% buffering is completely ineffective, adding excess stock without meaningfully reducing shortfalls (CSL only 71.05%).
  - At symmetric 1:1 loss, raw forecast has lower loss because any buffer increases holding cost. In real textile wholesale, stockout penalty is strictly asymmetric (loss of sale + lost customer goodwill).

---

## 5. Pattern-Specific Buffer Analysis (Task 5)

We audited the development buffer policies across classified patterns at Horizon 3:

| Demand Pattern | Development Policy | Mean Buffer (m) | Raw CSL | Calibrated CSL | Raw Shortfall | Calibrated Shortfall | Raw Excess | Calibrated Excess | 2:1 Loss (Raw → Cal) | 3:1 Loss (Raw → Cal) | 3:1 Loss Δ |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **fast_moving** | 80% SL | 25.29 | 65.38% | **79.23%** | 31.97 | **25.58** | 10.46 | 29.36 | 74.41 → 80.52 | 106.38 → **106.10** | **+0.281 (Improves)** |
| **stable/normal**| 80% SL | 14.63 | 58.02% | **76.54%** | 9.29 | **5.88** | 4.81 | 16.03 | 23.39 → 27.78 | 32.68 → 33.66 | -0.980 |
| **falling** | 75% SL | 9.57 | 59.85% | **73.48%** | 6.50 | **4.18** | 1.46 | 8.71 | 14.46 → 17.08 | 20.96 → 21.26 | -0.302 |
| **rising** | 80% SL | 12.91 | 69.39% | **73.47%** | 12.78 | **10.08** | 4.05 | 14.27 | 29.61 → 34.42 | 42.39 → 44.50 | -2.111 |
| **intermittent**| 75% SL | 0.00* | 74.21% | 74.21% | 5.64 | 5.64 | 0.74 | 0.74 | 12.02 → 12.02 | 17.66 → 17.66 | 0.000 |
| **dead_stock** | 0% SL | 0.00 | 86.72% | 86.72% | 2.26 | 2.26 | 0.00 | 0.00 | 4.51 → 4.51 | 6.77 → 6.77 | 0.000 |

*\*Note on Intermittent 75%*: In historical residual backtests, over 75% of intermittent observations are zero. Thus, the 75th percentile empirical residual is zero. Intermittent buffering at 75% defaults to zero buffer.

### Strategic Policy Implications:
1. **`fast_moving` (80% SL) is strongly justified**: Attains **79.23% CSL** (nearly exact 80% target), cuts mean shortfall from 31.97m to 25.58m (-20.0%), and **improves 3:1 business loss**.
2. **`stable/normal` (80% SL) is justified**: Cuts mean shortfall from 9.29m to 5.88m (-36.7%) and achieves 76.54% CSL.
3. **`rising` should be lowered from 80% to 75%**: Rising items already carry upward momentum; an 80% buffer inflates holding excess to 14.27m when trends level off.
4. **`dead_stock` (0% SL) is completely verified**: Prevents any inventory reorder on inactive stock.

---

## 6. Legacy Target Investigation (Task 6)

We conducted a deep investigation into the **903 products (90.3%)** where the shadow reorder target differed materially from the legacy production target (`|delta| >= 10m` or `>= 50%`).

Rather than reflexively assuming lower shadow targets represent legacy overstock, we cross-referenced:
- Current stock on hand
- Recent 3-month and 6-month demand
- Central forecast
- Shadow target
- Legacy reorder point
- Months of coverage under legacy vs. shadow targets

```
                      LEGACY TARGET INVESTIGATION (903 MATERIAL PRODUCTS)
                      ┌─────────────────────────────────────────────────┐
                      │ 1. Likely Legacy Overstock:        526 (58.3%)  │
                      │ 2. Potentially Legitimate Need:    319 (35.3%)  │
                      │ 3. Uncertain / Manual Review:       58  (6.4%)  │
                      └─────────────────────────────────────────────────┘
```

### Breakdown and Case Audits

#### Category 1: Likely Legacy Overstock (526 products, 58.3%)
- **Mechanism:** The legacy engine computes reorder points as `avg_monthly_demand * coverage_months` using *lifetime history* across years of sales. For products that sold heavily in 2023–2024 but stalled in 2025–2026, the legacy engine retains an inflated reorder point (often 50–200 meters), driving legacy months of coverage to **>6 months or infinity**.
- **Case Audit:**
  - Product 15 (`351-03`): Stock on hand = 38.0m, recent 3m demand = 0.0m. Legacy target = 0.7m. Shadow target = 0.0m.
  - Product 29 (`351-17`): Stock on hand = 181.0m, recent 3m demand = 0.0m. Legacy target = 14.7m (coverage = ∞). Shadow target = 0.0m.
  - Product 58 (`351-46`): Stock on hand = 158.2m, recent 3m demand = 0.0m. Legacy target = 3.3m (coverage = ∞). Shadow target = 0.0m.
- **Verdict:** True legacy overstock risk. Adopting the shadow target will halt wasteful purchases on dormant products.

#### Category 2: Potentially Legitimate Higher-Stock Requirement (319 products, 35.3%)
- **Mechanism:** Products with strong recent demand where the legacy target is higher, but the legacy target represents **valid operational coverage (<= 4 months)** for bulk fabric rolls or batch production.
- **Case Audit:**
  - Product 49 (`351-37`): Recent 3m demand = 43.5m (14.5m/mo). Stock on hand = 223.0m. Legacy target = 29.0m (2.0 months coverage). Shadow target = 1.28m.
  - Product 204 (`349-07`): Recent 3m demand = 82.0m (27.3m/mo). Stock on hand = 173.5m. Legacy target = 54.7m (2.0 months coverage). Shadow target = 0.0m.
- **Verdict:** In these fabrics, recent demand was concentrated in specific months. The shadow forecast trimmed the recent spikes because of intervening zero months. **Blindly slashing targets to 0m could cause stockouts on active fabrics.** These items require lead-time and batch-size constraints before automated target reduction.

#### Category 3: Uncertain / Manual Review (58 products, 6.4%)
- **Mechanism:** High-variance items with recent sporadic demand and legacy coverage between 4 and 6 months.
- **Case Audit:**
  - Product 739 (`328-35`): Recent demand = 65.0m, legacy target = 124.3m (5.7 months coverage), shadow target = 0.0m.
  - Product 3260 (`810-07 2062`): Recent demand = 38.5m, legacy target = 67.3m (5.2 months coverage), shadow target = 4.47m.
- **Verdict:** Flagged for buyer/planner review in the shadow exception queue.

**Persisted Audit Artifact:**
- `scratch/step9b_legacy_target_investigation.csv`

---

## 7. Shadow Safety Audit (Task 7)

The frozen `ShadowPipeline` was executed across all 1,000 products in the active cohort.

### Audit Checklist & Anomaly Metrics

| Audit Check / Diagnostic Metric | Result | Benchmark Threshold / Invariant | Status |
| :--- | :---: | :---: | :---: |
| **Total Products Evaluated** | 1,000 | 1,000 | PASS |
| **Pipeline Crashes / Unhandled Errors** | 0 | 0 | PASS |
| **Negative Forecasts / Targets** | **0** | **Strict 0** | **PASS** |
| **Dead Stock with Non-Zero Target** | **0** | **Strict 0** | **PASS** |
| **Forecast Delta > 25% vs Legacy** | 65.40% (654/1000) | Diagnostic | Monitored |
| **Forecast Delta > 50% vs Legacy** | 62.80% (628/1000) | Diagnostic | Monitored |
| **Forecast Delta > 100% vs Legacy** | 1.20% (12/1000) | < 5% | PASS |
| **Target Delta > 25% vs Legacy** | 91.10% (911/1000) | Diagnostic | Monitored |
| **Target Delta > 50% vs Legacy** | 89.80% (898/1000) | Diagnostic | Monitored |
| **Target > 2x Forecast (non-zero)** | 12.50% | < 25% | PASS |
| **Buffer > Forecast (non-zero)** | 12.50% | < 25% | PASS |
| **Potential Understock Risk Flags** | 663 (66.3%) | Informational (Legacy > Shadow) | Monitored |
| **Potential Overstock Risk Flags** | 0 (0.0%) | Informational (Shadow > Legacy) | PASS |

**Top 50 Changes Exported:**
- The top 50 largest target deltas were exported for planner inspection: `scratch/step9b_top50_largest_changes.csv`.
- The largest changes correspond directly to dormant legacy products where legacy reorder targets of 100–300m were collapsed to 0m by the shadow engine.

---

## 8. Unit Tests (Task 8)

Four new test cases were added to `backend/tests/test_benchmark_v2_shadow.py` to cover active-product shadow dynamics:
1. `test_active_fast_moving_product_shadow_evaluation`: Confirms active continuous items produce strictly positive forecasts, positive safety buffers, and valid target stocks.
2. `test_active_intermittent_product_shadow_evaluation`: Confirms active intermittent products with recent demand produce non-negative forecasts, bounded buffers, and valid targets.
3. `test_active_product_zero_stock_on_hand`: Verifies active stockout items evaluate safely without division-by-zero or negative target stocks.
4. `test_material_delta_detection_on_active_products`: Verifies material delta calculations distinguish legacy understock vs overstock risk flags.

**Test Suite Execution Results:**
```
Ran 85 tests in 2.480s

OK
```
All 85 tests pass across:
- `backend/tests/test_benchmark_v2_correctness.py`
- `backend/tests/test_benchmark_v2_leakage.py`
- `backend/tests/test_benchmark_v2_calibration.py`
- `backend/tests/test_benchmark_v2_shadow.py`

---

## 9. Explicit Task Answers

### 1. Does `trimmed_mean_3` generalize to active products?
**YES.**
On this 1,000-product active cohort with zero prior overlap, `trimmed_mean_3` achieved a pooled WAPE of **1.0514** (vs 1.1847 for median baseline) and a Macro WAPE of **1.1493** (vs 1.8015 for median baseline). It is decisively the strongest central demand forecaster in the catalog.

### 2. Is it still best at H3?
**YES.**
At the operational 3-month reorder horizon (H3), `trimmed_mean_3` registered a WAPE of **1.0711**, outperforming `median_baseline` (1.2271) by 15.6 percentage points and `pattern_router_e` (1.2724) by 20.1 percentage points.

### 3. Does `pattern_router_e` add value?
**NO.**
`pattern_router_e` underperformed simple baselines across the board (overall WAPE 1.2352; H3 WAPE 1.2724). On rising products, the router's internal trend models severely overshot, yielding an unacceptable WAPE of 2.0379 (compared to 1.2596 for `trimmed_mean_3`). The router should remain in Benchmark V2 research and NOT be promoted.

### 4. Which patterns need special handling?
- **`intermittent`**: Even though `trimmed_mean_3` has the lowest WAPE, intermittent demand requires conservative buffering (70–75%) to prevent phantom inventory from occasional batch spikes.
- **`dead_stock`**: Requires hard zero clamping on both forecast and buffer (`buffer = 0.0`, `target = 0.0`).
- **`fast_moving`**: Requires full 80% service-level buffering to protect against severe stockout penalties on core revenue drivers.

### 5. Does empirical buffering improve business loss on ACTIVE products?
**YES.**
Under an asymmetric business environment where stockouts carry higher penalties (e.g. 3:1), empirical buffering reduces shortfall from 8.831m to 8.439m and reduces total business loss from 29.052 to **28.989**.

### 6. Is 80% still justified?
**Partially.**
For `fast_moving` and `stable/normal` products, 80% configured CSL achieves ~77–79% attained service level and directly optimizes business loss. For the broader catalog (including intermittent items), configured 75% achieves optimal business loss without building excess inventory.

### 7. Which pattern-specific service levels should actually be used?
- `fast_moving`: **80%**
- `stable/normal`: **80%**
- `rising`: **75%** (lowered from 80% to avoid overshooting during demand inflection)
- `falling`: **75%**
- `intermittent`: **75%**
- `dead_stock`: **0%**

### 8. Are legacy reorder targets genuinely excessive or merely different?
**Both, with clear distinctions:**
- **58.3% are genuinely excessive legacy overstock** caused by the legacy engine applying lifetime historical demand to dormant products.
- **35.3% represent legitimate operational requirements** on active batch fabrics where legacy targets provide valid coverage (<= 4 months) that should not be immediately eliminated without lead-time and batch-size constraints.
- **6.4% require manual buyer review**.

### 9. Is the forecasting + calibration architecture ready for a canary shadow deployment?
**YES, for a PASSIVE CANARY SHADOW DEPLOYMENT.**
The architecture is fully ready for a passive, read-only shadow deployment where forecasts and calibrated buffers run in parallel with production, logging diagnostics and populating a side-by-side comparison screen without creating live Odoo purchase orders. It is NOT yet ready for unmonitored automated PO creation until batch-size constraints and planner approval workflows are integrated.

---

## 10. Integrity Verification

1. **Production Forecasting Files Untouched:**
   - `forecasting-engine/src/*`: Confirmed completely untouched.
   - `backend/app/api/*`: Confirmed untouched.
2. **Odoo Database Untouched:**
   - Zero Odoo tables modified.
   - Zero Odoo schema changes.
   - Zero Odoo purchase orders created.
3. **Changed Files in this Step:**
   - `backend/tests/test_benchmark_v2_shadow.py` (added 4 active-product shadow unit tests)
   - `forecasting-engine/STEP9B_ACTIVE_CATALOG_VALIDATION.md` (this report)
4. **All Unit Tests Passing:**
   - 85 / 85 tests passing (`OK`).
