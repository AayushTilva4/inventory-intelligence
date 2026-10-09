# Cold-Start Similar-Product Analogue Diagnostic Report

## 1. Executive Summary

This report documents the implementation and validation of the **Cold-Start Similar-Product Analogue Diagnostic** for product groups with fewer than 6 usable months of historical demand ($N < 6$). 

In accordance with the mentor-reference codebase audit (`forecasting-engine/src/similar_products.py`), this diagnostic provides demand planners and inventory specialists with evidence-based comparable product intelligence without violating the strict statistical threshold ($N \ge 6$) required for automated operational forecasting.

### Core Architectural Guarantees

1. **Operational Invariance**: For product groups with $N < 6$, the operational forecast status remains strictly `insufficient_group_history`, the forecast output remains `None`, the replenishment action remains `review`, and the suggested purchase quantity remains `0`.
2. **$N \ge 6$ Protection**: All products with $\ge 6$ months of history retain 100% identical forecasts, models, safety stock, target stock, inventory positions, and purchase recommendations (Tasks 4–11 mathematical invariants untouched).
3. **Verified Attributes Only**: Similarity is calculated exclusively using verified Odoo product attributes (`categ_id`, `brand_id`, `composition`, `quality`, `gsm`, `list_price`, and lineage relationships). Missing attributes are tracked explicitly in `missing_attributes` and are never silently treated as matches or assigned arbitrary default values.
4. **Explicit Diagnostic Boundary**: The analogue signal is encapsulated within a distinct `cold_start_diagnostic` payload containing candidate identifiers, verified similarity scores, matching/unmatched/missing attributes, historical demand metrics, velocity scaling, and explicit limitation disclosures.
5. **Zero Odoo Mutations**: All database interactions are strictly READ-ONLY. No purchase orders, RFQs, quants, moves, or schema modifications were executed.

---

## 2. Reference Audit & Architectural Design

### 2.1 Reference Audit Findings (`similar_products.py`)
The mentor reference provided an attribute similarity calculation based on weighted attributes and cosine similarity. However, adapting this to the current production PostgreSQL/Odoo environment required several key engineering enhancements:
- **Relational Integrity**: Direct integration with Odoo's `product_template` table, `main_product` relationships, and the `product_template_similar_rel` association table.
- **Missing Value Rigor**: Distinguishing true attribute matches (`matching_attributes`), genuine attribute mismatches (`unmatched_attributes`), and unpopulated data (`missing_attributes`). Missing attributes reduce total potential evidence rather than masquerading as similarity.
- **Velocity Adjustment**: When a target product has short observed history (1–5 months), candidate historical demand is scaled by the target's relative sales velocity before calculating diagnostic signals.
- **Clean Service Layer**: A standalone service module (`app/forecasting/cold_start_analogue_service.py`) that cleanly integrates into `group_forecast_service.py` and `group_recommendation_service.py` without mutating legacy data contracts.

---

## 3. Methodology & Mathematical Formulation

### 3.1 Verified Attribute Weights and Scoring
The similarity score $S(T, C) \in [0.0, 1.0]$ between target product $T$ and candidate analogue $C$ is computed dynamically across available verified attributes:

$$\text{Similarity Score} = \frac{\sum_{k} w_k \cdot s_k(T_k, C_k)}{\sum_{k} w_k \cdot \mathbb{I}(T_k \text{ and } C_k \text{ present})}$$

| Attribute | Max Weight ($w_k$) | Matching Logic |
| :--- | :---: | :--- |
| **Explicit Lineage / Similar Rel** | $0.40$ | $1.0$ if target and candidate share `main_product` or are linked via `product_template_similar_rel` |
| **Product Category (`categ_id`)** | $0.25$ | $1.0$ if identical integer category ID; $0.0$ otherwise |
| **Brand (`brand_id`)** | $0.15$ | $1.0$ if identical brand ID; $0.0$ otherwise |
| **Quality / Fabric Grade** | $0.10$ | $1.0$ if normalized string match; $0.0$ otherwise |
| **Composition / Material** | $0.10$ | $1.0$ if normalized text match, or $0.70$ if partial substring overlap |
| **GSM (Fabric Weight)** | $0.10$ | $1.0 - \frac{|GSM_T - GSM_C|}{\max(GSM_T, GSM_C)}$ if relative difference $\le 25\%$; $0.0$ otherwise |
| **List Price Tier** | $0.10$ | $1.0 - \frac{|P_T - P_C|}{\max(P_T, P_C)}$ if relative price difference $\le 30\%$; $0.0$ otherwise |

### 3.2 Candidate Eligibility Criteria
A candidate product $C$ is eligible as a cold-start analogue if and only if:
1. $C \neq T$ (cannot be the target itself).
2. Candidate has $\ge 6$ usable months of historical sales ($N_C \ge 6$).
3. Verified similarity score $S(T, C) \ge 0.30$.

### 3.3 Velocity Scaling & Signal Aggregation
When the target group has $1 \le N_T \le 5$ months of history, the candidate's historical monthly demand $\bar{D}_C$ is adjusted by the ratio of observed velocities:

$$\text{Scale Factor } \alpha = \text{clamp}\left( \frac{\bar{D}_T}{\bar{D}_C}, 0.20, 5.0 \right)$$

$$\text{Analogue Forecast Signal} = \bar{D}_C \cdot \alpha$$

The summary diagnostic estimate $\hat{D}_{\text{diagnostic}}$ is derived from the median signal of the top $K \le 5$ ranked analogues, blended cautiously with observed early velocity:
- For $N_T = 0$: $\hat{D}_{\text{diagnostic}} = \text{median}(\text{signals})$
- For $N_T = 1$: $\hat{D}_{\text{diagnostic}} = 0.85 \cdot \text{median}(\text{signals}) + 0.15 \cdot \bar{D}_T$
- For $2 \le N_T \le 5$: $\hat{D}_{\text{diagnostic}} = 0.75 \cdot \text{median}(\text{signals}) + 0.25 \cdot \bar{D}_{T, \text{recent}}$

---

## 4. Operational Invariance & Safety

The analogue diagnostic is strictly isolated from automated procurement decisions:

```
+-------------------------------------------------------------------------------+
|                             GROUP DEMAND SERVICE                              |
+-------------------------------------------------------------------------------+
                                       |
                     +-----------------+-----------------+
                     |                                   |
              [History >= 6]                      [History < 6]
                     |                                   |
         +-----------------------+           +-----------------------+
         | Operational Forecast  |           | Cold-Start Diagnostic |
         | Next Month: Float     |           | Status: 'insufficient'|
         | Horizon Demand: Float |           | Next Month: None      |
         | Model: Selected Model |           | Model: None           |
         +-----------------------+           +-----------------------+
                     |                                   |
         +-----------------------+           +-----------------------+
         | Tasks 4-11 Engine     |           | Tasks 4-11 Invariant  |
         | SS = z * sigma_L      |           | Action: 'review'      |
         | Suggested Qty = Math  |           | Suggested Qty = 0     |
         +-----------------------+           +-----------------------+
```

---

## 5. Files Changed and Implementation Details

1. **`backend/app/forecasting/cold_start_analogue_service.py`** *(New File)*:
   - Implements `compute_attribute_similarity` with verified attribute scoring, missing attribute tracking, and zero hallucination.
   - Implements `diagnose_cold_start_group` and `get_cold_start_analogues` performing read-only queries against Odoo's catalog and stock move history.
   - Computes candidate ranking, velocity scaling, and limitation metadata.

2. **`backend/app/forecasting/group_forecast_service.py`** *(Modified)*:
   - When `len(sales) < MINIMUM_HISTORY` (6 months), queries `get_cold_start_analogues` and attaches `cold_start_diagnostic` to the result dictionary.
   - Keeps `status = "insufficient_group_history"`, `next_month_forecast = None`, and `best_model = None`.

3. **`backend/app/inventory/group_recommendation_service.py`** *(Modified)*:
   - Forwards `cold_start_diagnostic` in the recommendation breakdown response when present.
   - Guarantees `action = "review"` and `group_suggested_purchase_qty = 0` for all `insufficient_group_history` groups.

4. **`backend/tests/test_cold_start_analogue.py`** *(New Test Suite)*:
   - 9 comprehensive unit and integration tests covering all requirements and edge cases.

---

## 6. Test Suite & Validation Evidence

### 6.1 Dedicated Cold-Start Test Suite (`test_cold_start_analogue.py`)
All 9 dedicated unit tests passed:

| Test Case | Scenario Tested | Outcome |
| :--- | :--- | :---: |
| `test_cold_start_zero_history` | Target with 0 history months receives valid diagnostic with candidate analogues and median summary | **PASSED** |
| `test_cold_start_short_history_1_to_5_months` | Target with 3 months history applies velocity scaling and blended estimate | **PASSED** |
| `test_cold_start_missing_attributes_handled_safely` | Target with null GSM, price, quality does not inflate score; tracks `missing_attributes` | **PASSED** |
| `test_cold_start_no_suitable_analogue` | Target with distinct/incompatible attributes returns `cold_start_no_suitable_analogue` | **PASSED** |
| `test_cold_start_multiple_candidates_ranking` | Highest verified similarity candidate is ranked first | **PASSED** |
| `test_cold_start_operational_invariance_under_6_months` | Group with $N=3$ has `status="insufficient_group_history"`, `action="review"`, `suggested_qty=0` | **PASSED** |
| `test_cold_start_invariance_for_sufficient_history_products` | Group with $N=12$ months does NOT attach cold start diagnostic; operational forecast active | **PASSED** |
| `test_explicit_lineage_weighting` | Explicit relationship (`main_product` or `similar_rel`) scores higher than pure attribute match | **PASSED** |
| `test_cold_start_discloses_limitations` | Diagnostic contains explicit limitation disclosures warning against operational procurement | **PASSED** |

### 6.2 Full Test Suite Results
- **Backend Test Suite (`backend/tests`)**: **256 passed, 1 skipped** (100% pass rate).
- **Forecasting Engine Test Suite (`forecasting-engine/tests`)**: **2 passed** (100% pass rate).

---

## 7. Limitations & Operational Guidelines

1. **Guidance Only**: Analogue estimates provide directional demand signals for manual review during new product launches; they must never trigger unapproved automated replenishment orders.
2. **Catalog Attribute Sparsity**: If historical peers have unpopulated attributes in Odoo, candidate matching is constrained to category, brand, and lineage. Planners are advised to maintain complete product attributes in Odoo.
3. **Cannibalization & Cross-Elasticity**: High demand in an analogue product may not translate directly if the new product cannibalizes or targets a different demographic segment.
