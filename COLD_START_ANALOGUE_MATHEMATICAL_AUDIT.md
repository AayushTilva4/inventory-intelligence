# Cold-Start Analogue Diagnostic — Mathematical Audit and Calibration

## 1. Executive Summary & Acceptance Decision

This report provides the final mathematical reconciliation, evidence calibration, and historical backtest audit for the **Cold-Start Similar-Product Analogue Diagnostic** implemented in `cold_start_analogue_service.py`.

### Final Acceptance Decision: **ACCEPTED AS AN ADVISORY-ONLY DIAGNOSTIC**

The diagnostic is accepted under the strict condition that it remains **strictly advisory and non-operational**:
- For all product groups with $N < 6$ usable months of history, the operational status remains `insufficient_group_history`, operational forecast remains `None`, replenishment action remains `review`, and suggested purchase quantity remains `0`.
- All operational forecasting, safety stock, target stock, and replenishment logic for products with $N \ge 6$ usable months remain **100% invariant** and unaffected.
- The analogue diagnostic provides demand planners with evidence-backed comparable peer identification and directional volume priors during new product introduction, but does **not** replace operational forecasting.

---

## 2. Mathematical Score Reconciliations & Definitions

### 2.1 Formal Definitions of Similarity Metrics

To eliminate any ambiguity between normalized similarity scores and raw evidence weights, the similarity engine defines four exact mathematical quantities:

Let $k \in \mathcal{A}$ index the set of potential product attributes:
$$\mathcal{A} = \{\text{category} (0.25), \text{brand} (0.15), \text{composition} (0.15), \text{quality} (0.10), \text{gsm} (0.05), \text{list\_price} (0.05)\}$$

Let $W_{\text{benchmark}}$ be the maximum potential weight capacity:
- $W_{\text{benchmark}} = 0.75$ for physical catalog attribute comparisons.
- $W_{\text{benchmark}} = 1.00$ when explicit lineage links (`main_product` or `product_template_similar_rel`) are present.

1. **Weighted Evidence Numerator ($W_{\text{matched}}$)**:
   $$W_{\text{matched}} = \sum_{k \in \mathcal{A}_{\text{matched}}} w_k \cdot s_k(T_k, C_k)$$
   where $s_k \in [0.0, 1.0]$ represents the verified attribute proximity or match score.

2. **Available Evidence Weight ($W_{\text{available}}$)**:
   $$W_{\text{available}} = \sum_{k \in \mathcal{A}_{\text{present}}} w_k$$
   where $\mathcal{A}_{\text{present}}$ is the subset of attributes present (non-null) in **both** target and candidate.

3. **Raw Similarity Score ($\text{Score}_{\text{raw}}$)**:
   $$\text{Score}_{\text{raw}} = \frac{W_{\text{matched}}}{W_{\text{available}}} \in [0.0, 1.0] \quad (\text{for } W_{\text{available}} > 0)$$
   This represents the degree of agreement strictly over the subset of observable attributes.

4. **Evidence Coverage ($\text{Coverage}$)**:
   $$\text{Coverage} = \min\left(1.0, \frac{W_{\text{available}}}{W_{\text{benchmark}}}\right) \in [0.0, 1.0]$$
   This quantifies the completeness of the attribute profile relative to the standard benchmark capacity ($0.75$ or $1.00$).

5. **Effective Similarity Score ($\text{Score}_{\text{effective}}$)**:
   $$\text{Score}_{\text{effective}} = \frac{W_{\text{matched}}}{\max(W_{\text{available}}, W_{\text{benchmark}})} \in [0.0, 1.0]$$

### 2.2 Universal Proof of the Coverage Identity

When $W_{\text{available}} \le W_{\text{benchmark}}$ (the standard case across the catalog):

$$\text{Score}_{\text{effective}} = \frac{W_{\text{matched}}}{W_{\text{benchmark}}} = \left(\frac{W_{\text{matched}}}{W_{\text{available}}}\right) \cdot \left(\frac{W_{\text{available}}}{W_{\text{benchmark}}}\right) \equiv \text{Score}_{\text{raw}} \cdot \text{Coverage}$$

This identity holds universally across both physical attribute comparisons ($W_{\text{benchmark}} = 0.75$) and explicit lineage comparisons ($W_{\text{benchmark}} = 1.00$).

#### Exact Numerical Examples

| Scenario | Present Attributes | Matched Attributes | $W_{\text{matched}}$ | $W_{\text{available}}$ | $W_{\text{benchmark}}$ | $\text{Score}_{\text{raw}}$ | $\text{Coverage}$ | $\text{Score}_{\text{effective}}$ |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **A. Category Only** | Category ($0.25$) | Category ($0.25$) | $0.25$ | $0.25$ | $0.75$ | $1.000$ | $0.3333$ | **$0.3333$** |
| **B. Category + Price** | Category ($0.25$), Price ($0.05$) | Category ($0.25$), Price ($0.05$) | $0.30$ | $0.30$ | $0.75$ | $1.000$ | $0.4000$ | **$0.4000$** |
| **C. Category + Mismatched Brand** | Category ($0.25$), Brand ($0.15$) | Category ($0.25$) | $0.25$ | $0.40$ | $0.75$ | $0.625$ | $0.5333$ | **$0.3333$** |
| **D. Complete Physical Match** | Categ, Brand, Comp, Qual, GSM, Price | All Match | $0.75$ | $0.75$ | $0.75$ | $1.000$ | $1.0000$ | **$1.0000$** |
| **E. Explicit Lineage + Category** | `similar_rel` ($0.35$), Category ($0.25$) | Both Match | $0.60$ | $0.60$ | $1.00$ | $1.000$ | $0.6000$ | **$0.6000$** |

This structure guarantees that sparse attributes (e.g. matching on category alone) can never masquerade as a 100% similarity match.

---

## 3. Candidate Eligibility & Boundary Verification

### 3.1 Eligibility Criteria
To prevent false-positive analogue matching in sparse catalog environments, a candidate product $C$ is accepted if and only if:
1. **Separation**: $C \neq T$ (candidate cannot be the target product itself).
2. **History Sufficiency**: Candidate has at least 6 distinct selling months in Odoo ($N_C \ge 6$).
3. **Evidence Requirement**:
   $$\text{Candidate Eligible} \iff \text{has\_explicit\_link} = \text{True} \quad \lor \quad (\text{matched\_attribute\_count} \ge 2 \land \text{Score}_{\text{effective}} \ge 0.30)$$

### 3.2 Boundary and Edge-Case Audit
- **Zero-Demand Candidates**: Candidates with total sales $= 0$ yield $\text{cand\_avg\_d} = 0.0$. Handled safely without division by zero.
- **Sparse / Missing Attributes**: Missing values in target or candidate are tracked in `missing_attributes` and excluded from $W_{\text{matched}}$ without default-value hallucination.
- **Score Bounds**: All scores are mathematically bounded in $[0.0, 1.0]$.
- **Target Not Found / No Analogues**: Returns a structured diagnostic payload with `status = "cold_start_target_not_found"` or `"cold_start_no_suitable_analogue"` and explicit limitation disclosures.

---

## 4. Reconciled Historical Backtest & Evidence Audit

An out-of-sample simulation across **16 historical cut-off origins** spanning the 41-month dataset (2023-06 to 2026-10) was executed to benchmark diagnostic behaviors.

### 4.1 Zero-History Cohort ($N = 0$, $N_{\text{samples}} = 1,394$)

| Method / Baseline | MAE | Bias | WAPE | Operational Meaning |
| :--- | :---: | :---: | :---: | :--- |
| **Category Median Baseline** | **38.45** | -33.29 | **98.4%** | Simple naive category median |
| **Category Mean Baseline** | 39.17 | -32.38 | 100.2% | Category arithmetic mean |
| **Analogue Early Launch Mean** | 40.19 | -30.15 | 102.8% | Borrowed early launch volume |
| **Analogue Mature Mean** | 40.57 | **-29.04** | 103.8% | Mature peer volume prior |

#### Honest Assessment for $N = 0$:
- Forecasting error on new product launches is extremely high ($\text{WAPE} \approx 98\%\text{--}104\%$) across all methods due to structural launch volatility (launch zeroes vs. initial bulk pipeline fills).
- The analogue diagnostic does **not** provide high-precision point accuracy; rather, its value is in providing demand planners with an evidence-backed **volume prior** and **comparable product reference** (reducing negative bias from $-33.29$ to $-29.04$).
- This empirical evidence confirms why automated operational replenishment must remain disabled.

---

### 4.2 Reconciled Short-History Cohort ($N = 1..5$, $N_{\text{samples}} = 6,053$)

The 6,053 short-history instances across all 16 historical cutoffs are reconciled across subcohorts:
- $N = 1$: 1,328 observations
- $N = 2$: 1,302 observations
- $N = 3$: 1,225 observations
- $N = 4$: 1,136 observations
- $N = 5$: 1,062 observations
- **Total Exact Sum**: $1,328 + 1,302 + 1,225 + 1,136 + 1,062 = 6,053$ observations.

#### Aggregate Performance Comparison

| Method | Overall MAE | Overall Bias | Overall WAPE | Key Characteristics |
| :--- | :---: | :---: | :---: | :--- |
| **Target Own Mean ($\bar{D}_T$)** | **35.21** | -7.92 | **96.2%** | Pure target-history baseline |
| **Mature Analogue ($\bar{D}_C$)** | 37.24 | **-3.28** | 101.7% | Mature peer volume (lowest bias) |
| **Bayesian Blend ($K = 3$)** | 35.52 | -5.27 | 97.0% | Balanced compromise |

#### Subcohort Progression by Month Count ($N = 1 \to 5$)

| History Month ($N$) | Cohort Size ($N_{\text{samples}}$) | Own Mean MAE (WAPE) | Mature Analogue MAE (WAPE) | Bayesian Blend MAE (WAPE) | Credibility Weight ($z$) |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **$N = 1$** | 1,328 | 37.34 (95.5%) | 39.24 (100.4%) | 38.17 (97.6%) | $0.250$ |
| **$N = 2$** | 1,302 | 40.57 (99.8%) | 43.35 (106.6%) | 41.56 (102.2%) | $0.400$ |
| **$N = 3$** | 1,225 | 38.95 (93.5%) | 41.06 (98.6%) | 39.02 (93.7%) | $0.500$ |
| **$N = 4$** | 1,136 | 28.01 (97.6%) | 29.79 (103.7%) | 27.94 (97.3%) | $0.571$ |
| **$N = 5$** | 1,062 | 29.37 (94.0%) | 30.80 (98.6%) | 28.86 (92.4%) | $0.625$ |

#### Rigorous Distinction Between Point Accuracy and Bias:
- **No Aggregate Accuracy Improvement**: The Bayesian credibility blend does **not** improve aggregate point-forecast error (MAE 35.52 vs 35.21; WAPE 97.0% vs 96.2%) over the naive target-history sample mean on the $N=1..5$ cohort. No claim of overall accuracy improvement is made.
- **Bias Reduction**: The blend reduces launch underforecasting bias by **33.5%** (from $-7.92$ to $-5.27$) by pulling early unrepresentative months towards mature analogue volume.
- **Noise Damping**: For $N=1$, the blend prevents a single unrepresentative launch month (e.g. initial stock fill or temporary lull) from dictating 100% of the diagnostic volume.

---

### 4.3 Sensitivity & Rationale for Credibility Constant $K = 3.0$

$$\hat{D}_{\text{diagnostic}} = (1 - z) \cdot \text{median}(\text{analogue\_priors}) + z \cdot \bar{D}_T, \quad z = \frac{N}{N + K}$$

To evaluate the parameter $K$, an empirical sensitivity sweep was conducted on the full 6,053 short-history historical instances:

| Parameter Setting | MAE | Bias | WAPE | Operational Characteristics |
| :--- | :---: | :---: | :---: | :--- |
| **Target Own Mean ($K \to 0$)** | 35.21 | -7.92 | 96.2% | Ignores analogues; maximum underforecast bias |
| **Blend $K = 1$** | 35.09 | -6.42 | 95.8% | Rapid transition to target observed data |
| **Blend $K = 2$** | 35.32 | -5.71 | 96.4% | Moderate analogue weighting |
| **Blend $K = 3$ (Adopted)** | **35.52** | **-5.27** | **97.0%** | **Equal weighting ($z = 0.50$) at midpoint $N = 3$** |
| **Blend $K = 4$** | 35.69 | -4.98 | 97.5% | Higher analogue weighting |
| **Blend $K = 5$** | 35.82 | -4.76 | 97.8% | Higher analogue weighting |
| **Blend $K = 6$** | 35.94 | -4.59 | 98.1% | Strongest analogue weighting; lowest bias |
| **Mature Analogue ($K \to \infty$)** | 37.24 | -3.28 | 101.7% | Ignores target observed data |

#### Rationale and Limitations of $K = 3.0$:
- **Interpretability**: $K = 3.0$ provides an intuitive, interpretable midpoint calibration: at $N = 3$ (the midpoint of the $1..5$ month range), the observed target demand and the analogue prior receive exactly equal weight ($50\% / 50\%$).
- **Smooth Asymptotic Bridge**: As $N \to 6$, the weight on target data smoothly rises to $66.7\%$, providing a continuous transition to the $N \ge 6$ operational forecasting threshold.
- **Explicit Limitation**: $K = 3.0$ is an empirical heuristic balancing bias reduction against variance. It is not an optimal parameter derived from a parametric likelihood, and planners should treat all short-history diagnostic outputs as advisory indicators.

---

## 5. Operational Safety Invariants & Verification

The operational safety rules established in Tasks 4–11 remain strictly enforced:

1. **Isolation of Operational Forecasting**:
   - For all products with $N < 6$, `get_group_forecast` returns `status = "insufficient_group_history"`, `next_month_forecast = None`, `best_model = None`, and attaches `cold_start_diagnostic` solely as metadata.
2. **Isolation of Procurement Recommendations**:
   - `get_group_recommendation` returns `status = "insufficient_group_history"`, `action = "review"`, and `group_suggested_purchase_qty = 0`.
3. **Invariance for $N \ge 6$**:
   - Products with $\ge 6$ months of usable history never evaluate the cold-start diagnostic; their model selection, forecasts, safety stocks, inventory positions, and suggested purchase quantities remain 100% identical.
4. **Odoo Database Safety**:
   - Database operations are strictly READ-ONLY. Zero purchase orders, RFQs, quants, moves, or schema modifications were executed.

---

## 6. Final Test Suite Execution & Acceptance Outcome

All test suites were executed following final consistency closure:

- **Dedicated Cold-Start Suite (`test_cold_start_analogue.py`)**: **13 passed in 8.83s** (100% pass rate).
  - Exact coverage identity $\text{Score}_{\text{effective}} = \text{Score}_{\text{raw}} \cdot \text{Coverage}$ verified for both physical and lineage matches.
  - Denominator shrinkage prevention verified.
  - Zero history ($N=0$) and Bayesian credibility ($N=1..5$) verified.
  - Boundary conditions, range bounds $[0.0, 1.0]$, and zero-demand safety verified.
  - Operational invariance for $N < 6$ and $N \ge 6$ verified.
- **Full Backend Pytest Suite (`backend/tests`)**: **260 passed, 1 skipped in 18.31s** (100% pass rate).
- **Forecasting Engine Pytest Suite (`forecasting-engine/tests`)**: **2 passed in 0.74s** (100% pass rate).
- **Odoo Database Safety**: Strictly READ-ONLY; zero mutations.
