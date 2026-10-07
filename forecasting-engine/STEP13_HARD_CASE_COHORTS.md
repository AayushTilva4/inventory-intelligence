# Step 13: Fresh Out-of-Sample Hard-Case Cohorts

**Project:** Inventory Intelligence — Dazzle Fabrics Odoo Catalog  
**Step:** Step 13 — Task 1  
**Scope:** Specification of 6 Specialized Difficult-Case Cohorts (Total N=557)  
**Date:** October 2026  
**Status:** COMPLETE (Zero Overlap Verified)

---

## 1. Executive Summary

To evaluate whether fallback and reactivation logic produce **accurate and useful forecasts** (rather than merely safe defaults), we constructed six specialized hard-case cohorts totaling **557 products**.

Strict cohort isolation rules were enforced:
- **Zero overlap** with Top 100 Benchmark products.
- **Zero overlap** with the Step 7 1,000-product cohort.
- **Zero overlap** with the Step 9 1,000-product cohort.
- **Zero overlap** with the Step 9B 1,000-product active cohort.
- Deterministic selection using fixed pseudo-random seed `SEED = 42`.
- Persisted to [`scratch/step13_hard_case_cohorts.json`](file:///C:/Users/AAYUSH/.gemini/antigravity-ide/brain/18f466d7-5c15-4dc4-acc3-60590e1f7a47/scratch/step13_hard_case_cohorts.json).

---

## 2. Cohort Definitions & Summary

| Cohort Code | Cohort Name | Description / Selection Criteria | Candidate Pool | Selected Count |
| :--- | :--- | :--- | :---: | :---: |
| **Cohort A** | **Reactivated Products** | History span $\ge 6$m, $\ge 2$ positive sales months, prior zero-gap $\ge 4$ months, renewed demand in recent 3m | 335 | **100** |
| **Cohort B** | **Short-History Active** | Calendar history span $< 3$ months from first sale, positive recent demand ($N < 3$) | 60 | **60** *(100% available)* |
| **Cohort C** | **Single-Observation Active** | Exactly 1 positive sales month in lifetime, active within recent 12 months | 335 | **100** |
| **Cohort D** | **Active Intermittent** | Sporadic demand ($\text{ADI} \ge 1.5$ or active ratio $\le 35\%$), active in recent 6 months | 765 | **100** |
| **Cohort E** | **Stockout-Suppressed** | Physical stock on hand $= 0$, active sales in past 12 months, zero sales in recent 3 months | 97 | **97** *(100% available)* |
| **Cohort F** | **Volatile / Spike-Heavy** | $\text{Peak} / \text{Median} \ge 3.0$ or $CV \ge 0.8$ with peak demand $\ge 20$ units | 1,077 | **100** |
| **Total** | **All Hard-Case Cohorts** | **Zero overlap across previous benchmarks** | **2,669** | **557** |

---

## 3. Cohort Details & Sample Product IDs

### Cohort A: Reactivated Products ($N = 100$)
- **Criteria:** Meaningful past sales ($\ge 2$ positive months), dormant gap of $\ge 4$ consecutive zero months, followed by renewed activity in the last 1–3 months.
- **Top Sample PIDs:** `[2276, 5204, 5323, 5389, 5849, 7064, 7156, 7183, 7258, 7356]`
- **Validation Goal:** Test whether the engine detects reactivation in month 1, 2, and 3 without being prematurely clamped to dead stock or overreacting to one blip.

### Cohort B: Short-History Active Products ($N = 60$)
- **Criteria:** History span $< 3$ calendar months from introduction with positive recent demand.
- **Top Sample PIDs:** `[1930, 4248, 7635, 8108, 13344, 18776, 18777, 18778, 18779, 18780]`
- **Validation Goal:** Compare `recent_mean_fallback` against 1-point carryover and category analogue baselines.

### Cohort C: Single-Observation Active Products ($N = 100$)
- **Criteria:** Exactly 1 positive sales transaction across lifetime, occurring in the past 12 months.
- **Top Sample PIDs:** `[77, 107, 109, 110, 114, 117, 126, 169, 182, 187]`
- **Validation Goal:** Prevent a single transaction from generating perpetual phantom reorder targets.

### Cohort D: Active Intermittent Products ($N = 100$)
- **Criteria:** Sporadic purchasing patterns ($\text{ADI} \ge 1.5$), positive sales in the last 6 months.
- **Top Sample PIDs:** `[104, 105, 128, 133, 140, 143, 145, 148, 151, 153]`
- **Validation Goal:** Test `trimmed_mean_3` vs `median_baseline` across intermittent sub-segments (lumpy vs regular).

### Cohort E: Stockout-Suppressed Demand ($N = 97$)
- **Criteria:** On-hand physical stock $= 0$, positive sales in preceding 12 months, zero sales in trailing 3 months.
- **Top Sample PIDs:** `[87, 305, 386, 491, 494, 517, 545, 597, 610, 613]`
- **Validation Goal:** Distinguish genuine demand collapse from stockout suppression.

### Cohort F: Volatile / Spike-Heavy Products ($N = 100$)
- **Criteria:** Peak monthly demand $\ge 3\times$ median non-zero demand or $CV \ge 0.8$ with peak $\ge 20$ units.
- **Top Sample PIDs:** `[7086, 7096, 7150, 7190, 7255, 7350, 7421, 7449, 7461, 7476]`
- **Validation Goal:** Verify whether `trimmed_mean_3` outlier trimming is appropriately robust or overly conservative.
