# Phase 2 — Task 6: Safety Stock from Forecast Error Report

**Status:** Completed & Validated  
**Objective:** Replace the fixed 10% safety buffer placeholder with an empirical, evidence-based safety stock calculation derived from historical out-of-sample forecast errors across the operational horizon ($L + R = 4\text{ months}$).  
**Odoo Database Isolation:** 100% READ-ONLY (0 writes, 0 schema mutations, 0 POs/RFQs created).

---

## 1. Audit of Current Safety Stock Logic (Task 1)

Before Task 6, safety stock was implemented across the codebase as follows:

| Component | Historical / Pre-Task 6 Implementation | Issues Identified |
| :--- | :--- | :--- |
| `recommendation_engine.py` | `BUFFER_PCT = 0.10`, `safety_stock = round(D_horizon * 0.10, 4)` | Fixed 10% buffer ignored product volatility, noise, and forecast reliability. |
| `reorder.py` (legacy engine) | `reorder_point = avg_monthly_demand * (3 + 1.0)` | Hardcoded static 1-month safety stock based on trailing average. |
| Granularity | Target stock calculated at main-product group level | No individual residual variance or forecast uncertainty tracking existed. |
| Double Buffering Check | Audited: buffer was applied once to $D_{\text{horizon}}$ | No double-counting in Task 5, but embedded placeholder lacked statistical backing. |

---

## 2. Forecast Error Dataset Construction (Task 2)

Out-of-sample forecast errors were generated across rolling historical origins using the project's point-in-time backtesting infrastructure:
- **Historical Scope:** Monthly sales aggregated at main-product group level up to September 2026 ($M_{-1}$).
- **Rolling Origins:** Origins evaluated sequentially from month 6 to $N-1$ of available series history.
- **Strict Point-in-Time Safety:** At each origin $t$, models were trained **strictly** on data available at or before $t$ (no future leakage).
- **Multi-Step Forecasts:** 1-step to 4-step ahead forecasts generated using the champion model (`trimmed_mean_3`).
- **Ground Truth Comparison:** Compared against realized out-of-sample actual demand $y_{t+h}$ for horizons $h \in \{1, 2, 3, 4\}$ and cumulative 4-month operational horizon $H_{1..4} = \sum_{h=1}^4 y_{t+h}$.
- **Dataset Size:** **5,168 out-of-sample evaluation rows** collected across the catalog cohort (saved to `backend/data/task6_evaluations.csv`).

---

## 3. Error Measure Evaluation (Task 3)

The following error representations were evaluated for safety stock sizing:

1. **RMSE / Residual Standard Deviation ($\sigma_{\text{error}}$) [CHOSEN]:**
   - Directly represents the standard error of the forecast distribution.
   - Maps directly to classical and modern inventory theory ($\sigma_{\text{horizon}} = \sqrt{L + R} \cdot \sigma_{\text{error}}$).
   - Higher forecast uncertainty $\rightarrow$ higher $\sigma_{\text{error}} \rightarrow$ higher safety stock.
   - Low-noise / predictable series $\rightarrow$ lower $\sigma_{\text{error}} \rightarrow$ lower safety stock.
2. **MAE / WAPE:** Measures average magnitude but underestimates tail risk under volatile skewness.
3. **Signed Bias:** Tracks systematic over/under-forecasting; not suitable alone for buffer dispersion.

---

## 4. Benchmark of Current Fixed Buffer Baseline (Task 4)

The baseline snapshot using the temporary 10% multiplier was recorded across the top main-product group cohort:
- **Snapshot File:** `backend/data/task6_before_snapshot.csv`
- **Total Horizon Demand:** $2,669.98\,\text{m}$
- **Fixed Safety Stock (10%):** $266.99\,\text{m}$
- **Total Target Stock:** $2,936.96\,\text{m}$
- **Suggested Purchase Qty:** $156.0\,\text{m}$ across 2 purchasing groups

---

## 5. Candidate Safety Stock Methods & Chosen Architecture (Task 5 & 6)

### Evaluated Alternatives
- **Method A (Lead-Time Scaled Residual Error) [SELECTED]:**
  $$SS = Z_{\alpha} \times \sqrt{L + R} \times \sigma_{\text{error}}$$
- **Method B (Empirical Shortfall Quantile):** $q_{\alpha}(\max(0, y_{\text{4M}} - \hat{y}_{\text{4M}}))$. High variance on short histories ($< 12$ origin points).
- **Method C (Normalized CV Scaled):** $Z_{\alpha} \times \text{CV}_{\text{pattern}} \times D_{\text{horizon}}$. Used as robust fallback for sparse series.

### Chosen Formulation & Exact Mathematical Equations
For a group with projected demand $D_{\text{horizon}}$ over lead time $L = 3.0\,\text{months}$ and review period $R = 1.0\,\text{month}$:

$$\text{Operational Horizon } H = L + R = 4.0\,\text{months}$$
$$\text{Horizon Uncertainty Scaling Factor } K_{\text{horizon}} = \sqrt{L + R} = \sqrt{4.0} = 2.0$$

1. **Service Level Policy ($Z_{\alpha}$):**
   - `fast_moving`: $80\%\;\text{CSL} \implies Z_{0.80} = 0.8416$
   - `stable` / `normal`: $80\%\;\text{CSL} \implies Z_{0.80} = 0.8416$
   - `rising` / `falling` / `intermittent` / `cold_start`: $75\%\;\text{CSL} \implies Z_{0.75} = 0.6745$
   - `dead_stock`: $0\%\;\text{CSL} \implies Z = 0.0 \implies SS = 0.0$

2. **Error Scale ($\sigma_{\text{1M}}$):**
   $$\sigma_{\text{1M}} = \sqrt{\frac{1}{N} \sum_{i=1}^N (y_{i} - \hat{y}_{i})^2} \quad (\text{for } N \ge 5 \text{ out-of-sample origins})$$

3. **Safety Stock ($SS$):**
   $$SS_{\text{raw}} = Z_{\alpha} \times \sqrt{L + R} \times \sigma_{\text{1M}} = 2.0 \cdot Z_{\alpha} \cdot \sigma_{\text{1M}}$$
   $$SS = \operatorname{round}\Big(\min\big(SS_{\text{raw}},\; \max(1.5 \times D_{\text{horizon}},\; 10.0)\big),\; 4\Big)$$

4. **Target Stock ($S$):**
   $$\text{target\_stock} = \operatorname{round}(D_{\text{horizon}} + SS,\; 4)$$

---

## 6. Product / Group Granularity & Sparse-Data Fallback (Tasks 7 & 8)

1. **Primary Sizing:** Computed at the **canonical main-product group level** using group-specific historical forecast errors.
2. **Sparse-Data Fallback:** When a product group has fewer than 5 historical out-of-sample evaluation points (e.g. newly introduced items or short history), the error scale falls back to pattern-pooled empirical CV:
   $$\sigma_{\text{1M, fallback}} = \text{CV}_{\text{pattern}} \times \left(\frac{D_{\text{horizon}}}{L + R}\right)$$
   Where $\text{CV}_{\text{fast\_moving}} = 0.40$, $\text{CV}_{\text{stable}} = 0.20$, $\text{CV}_{\text{rising/falling}} = 0.35$, $\text{CV}_{\text{intermittent}} = 0.50$.
3. **Dead Stock Invariant:** If `dead_stock = True` or $D_{\text{horizon}} = 0$, safety stock is strictly **$0.0\,\text{m}$** (no phantom buffer).

---

## 7. Before vs. After Benchmark Comparison (Tasks 9 & 13)

Snapshots saved to:
- `backend/data/task6_before_snapshot.csv` (and `.json`)
- `backend/data/task6_after_snapshot.csv` (and `.json`)

### Cohort Summary Table

| Metric | Before Task 6 (Fixed 10%) | After Task 6 (Error-Based) | Delta | Operational Significance |
| :--- | :---: | :---: | :---: | :--- |
| **Total Horizon Demand** | $2,669.98\,\text{m}$ | $2,669.98\,\text{m}$ | $0.0\,\text{m}$ | Task 5 forecast demand 100% preserved |
| **Total Safety Stock** | $266.99\,\text{m}$ | $1,590.54\,\text{m}$ | $+1,323.55\,\text{m}$ | Dynamically expanded to cover true variance |
| **Total Target Stock** | $2,936.96\,\text{m}$ | $4,260.53\,\text{m}$ | $+1,323.57\,\text{m}$ | Provides genuine $75\%-80\%$ service levels |
| **Groups Needing Purchase** | 2 groups | 3 groups | $+1$ group | Volatile understocked item flagged |
| **Groups Under Review** | 0 groups | 2 groups | $+2$ groups | Low forecast confidence queues review |
| **Groups in Dead Stock** | 15 groups | 15 groups | 0 groups | All 15 dead stock groups receive $0.0\,\text{m}$ buffer |
| **Total Suggested Purchase** | $156.0\,\text{m}$ | $364.0\,\text{m}$ | $+208.0\,\text{m}$ | Accurately sized to prevent lead-time stockouts |

---

## 8. Mentor Evidence Examples & Archetypes (Task 10)

| Archetype | Group Name (ID) | Pattern | Horizon Demand | $\sigma_{\text{1M}}$ Error | Inv. Position | Old SS (10%) | New SS (Error) | Old Target | New Target | Old Buy | New Buy | Reason for Change |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **High-Forecast / Volatile** | **394-27** (14403) | intermittent | $400.7\,\text{m}$ | $82.8\,\text{m}$ | $286.4\,\text{m}$ | $40.1\,\text{m}$ | **$111.7\,\text{m}$** | $440.8\,\text{m}$ | **$512.5\,\text{m}$** | $155\,\text{m}$ | **$227\,\text{m}$** | Volatile error increases buffer to prevent stockout |
| **Falling / Surplus** | **379-06** (6623) | falling | $750.0\,\text{m}$ | $399.6\,\text{m}$ | $3,228.3\,\text{m}$ | $75.0\,\text{m}$ | **$539.1\,\text{m}$** | $825.0\,\text{m}$ | **$1,289.1\,\text{m}$** | $0\,\text{m}$ | **$0\,\text{m}$** | Existing stock surplus absorbs buffer; 0 purchase |
| **Fading / Review** | **1102-27** (11440) | intermittent | $28.5\,\text{m}$ | $16.2\,\text{m}$ | $32.5\,\text{m}$ | $2.9\,\text{m}$ | **$21.9\,\text{m}$** | $31.3\,\text{m}$ | **$50.3\,\text{m}$** | $0\,\text{m}$ | **$18\,\text{m}$** | Stock gap expands to cover intermittency error |
| **Fast-Moving / High-Noise** | **393-22** (10692) | fast_moving | $402.4\,\text{m}$ | $111.0\,\text{m}$ | $512.8\,\text{m}$ | $40.2\,\text{m}$ | **$186.8\,\text{m}$** | $442.7\,\text{m}$ | **$589.3\,\text{m}$** | $0\,\text{m}$ | **$77\,\text{m}$** | Fast mover needed buffer for $80\%$ CSL |
| **Dead Stock** | **18825** (6032) | dead_stock | $0.0\,\text{m}$ | $0.0\,\text{m}$ | $148.3\,\text{m}$ | $0.0\,\text{m}$ | **$0.0\,\text{m}$** | $0.0\,\text{m}$ | **$0.0\,\text{m}$** | $0\,\text{m}$ | **$0\,\text{m}$** | Zero forecast $\rightarrow$ zero buffer invariant |
| **Benchmark Deduplication** | **413-11** (16742) | intermittent | $24.7\,\text{m}$ | $8.0\,\text{m}$ | $1,054.0\,\text{m}$ | $2.5\,\text{m}$ | **$10.8\,\text{m}$** | $27.2\,\text{m}$ | **$35.5\,\text{m}$** | $0\,\text{m}$ | **$0\,\text{m}$** | Inbound $1,054\,\text{m}$ PO prevents duplicate purchase |
| **Benchmark Seasonal Surge** | **325-42** (859) | fast_moving | $958.6\,\text{m}$ | $120.0\,\text{m}$ | $461.3\,\text{m}$ | $95.9\,\text{m}$ | **$202.0\,\text{m}$** | $1,054.4\,\text{m}$ | **$1,160.6\,\text{m}$** | $594\,\text{m}$ | **$700\,\text{m}$** | Horizon demand intact; buffer covers peak surge |

---

## 9. Service Level Validation & Out-of-Sample Coverage (Task 12)

Out-of-sample backtest analysis demonstrated why the old 10% fixed buffer was fundamentally flawed:
- **Fixed 10% Attained CSL:** Achieved only **$16.3\%$ (falling) to $46.5\%$ (intermittent)** cycle service level during historical evaluation, leaving fabric products exposed to frequent stockouts.
- **Error-Based Method:** Calibrated to deliver the targeted **$75\% - 80\%$ cycle service level** by directly factoring $\sigma_{\text{error}}$ and the $4$-month operational horizon into the buffer sizing equation.

---

## 10. Regression Invariant Verification (Task 14)

Strict regression verification confirmed:
- `forecasted_horizon_demand` is **identical** before and after Task 6.
- Model forecasts ($H_1, H_2, H_3, H_4, H_5$) from `trimmed_mean_3` and model registry remain **unchanged**.
- `inventory_position` formula ($\text{Usable} + \text{Incoming} - \text{Committed}$) is **preserved**.
- Only `safety_stock`, `target_stock`, `stock_gap`, and resulting purchase quantity were updated to reflect forecast error.

---

## 11. Test Suite Results (Task 15)

Dedicated unit test suite added in `backend/tests/test_safety_stock_error.py`:
1. `test_1_stable_low_error_smaller_buffer` — **PASS**
2. `test_2_noisy_high_error_larger_buffer` — **PASS**
3. `test_3_zero_forecast_safe_zero_buffer` — **PASS**
4. `test_4_dead_stock_zero_buffer` — **PASS**
5. `test_5_sparse_error_history_deterministic_fallback` — **PASS**
6. `test_6_horizon_consistency_scaling` — **PASS**
7. `test_7_no_double_counted_safety_stock` — **PASS**
8. `test_8_non_negative_safety_stock` — **PASS**
9. `test_9_mentor_413_11_regression` — **PASS**
10. `test_10_mentor_325_42_regression` — **PASS**
11. `test_11_fixed_buffer_vs_error_based_comparison` — **PASS**
12. `test_12_deterministic_repeated_execution` — **PASS**

### Full Backend Test Run:
- **Total Tests:** **194 passed, 0 failures, 0 errors, 1 skipped**.

---

## 12. Odoo Read-Only Verification (Task 16)

- **Purchase Orders in DB:** 1,920 (0 created)
- **Stock Moves in DB:** 658,944 (0 created)
- **Warehouse Orderpoints:** 4 (0 modified)
- **Schema Mutations:** 0
- **Status:** **100% READ-ONLY COMPLIANT**.

---

## 13. Recommendation for Task 7 (Confidence from Real Error)

With Task 6 complete and validated:
- Safety stock now incorporates empirical forecast error standard deviation $\sigma_{\text{error}}$.
- In Task 7 (Confidence from Real Error), we can formalize confidence scoring ($e.g., \text{high, normal, low}$) directly from empirical error dispersion (such as $\text{CV}_{\text{error}} = \sigma_{\text{error}} / \bar{y}$ or historical WAPE), replacing heuristic confidence tags with statistical certainty metrics.
