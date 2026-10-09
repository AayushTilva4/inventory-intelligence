# Phase 2 — Task 11: Breakdown Behind Each Recommendation

> **Final Verdict:** `CURRENT RECOMMENDATION BREAKDOWN VALIDATED — READY FOR LATER UI INTEGRATION`

---

## 1. Executive Summary & Pipeline Audit

Task 11 exposes the exact mathematical and empirical breakdown behind every main-product group recommendation without modifying any underlying calculation logic, safety-stock formula, model-selection policy, stockout treatment, or procurement action.

A buyer can now trace the final purchase recommendation back to its underlying forecast components, error metrics, safety stock parameters, inventory position elements, target stock, and stock gap equations.

### 1.1 Audit of Existing Calculation Pipeline & Exposed Fields

| Calculation Component | Underlying Function / Service | Input Parameters / Formula | Intermediate Values Exposed in Breakdown |
| :--- | :--- | :--- | :--- |
| **Monthly & Horizon Forecast** | `get_group_forecast` | Multistep forecast $h=1..4$, $w_0$ partial-month weighting | `monthly_forecasts` $[f_1, f_2, f_3, f_4]$, `forecasted_horizon_demand` ($D_{horizon}$) |
| **Model Selection** | `select_best_model_operational` | Multi-origin rolling evaluation on $H=3,4$ replenishment horizons | `selected_model`, `selection_reason`, `is_short_history`, `short_history_fallback_used` |
| **Stockout Classification** | `classify_group_monthly_stockouts` | Odoo stock move inventory availability evidence | `history_months`, `usable_observations`, `stockout_suppressed_months` |
| **Confidence Diagnostic** | `classify_forecast_confidence` | OOS walk-forward WAPE, MASE, observation count | `confidence`, `wape`, `mase`, `rmse`, `observation_count`, `warnings` |
| **Safety Stock (Task 6)** | `calculate_error_based_safety_stock` | $SS = \min(Z \times \sqrt{L+R} \times \sigma_{1M}, \text{Cap})$ | `lead_time_months`, `review_period_months`, `operational_horizon_months`, `service_level`, `z_score`, `sigma_error_1m`, `horizon_scale_factor`, `sigma_horizon`, `raw_safety_stock`, `cap_applied`, `cap_value`, `final_safety_stock`, `safety_stock_method`, `dead_stock_safeguard` |
| **Inventory Position (Task 4)** | `build_recommendation` | $\text{IP} = \text{Usable} + \text{Incoming} - \text{Committed}$ | `usable_stock`, `incoming_stock`, `committed_stock`, `cut_piece_stock_excluded`, `inventory_position`, `formula` |
| **Target & Purchase (Task 5)** | `build_recommendation` | $\text{Target} = D_{horizon} + \text{SS}$, $\text{Gap} = \max(\text{Target}-\text{IP}, 0)$, $\text{Purchase} = \lceil \text{Gap} \rceil$ | `target_stock`, `stock_gap`, `suggested_purchase_qty`, `action`, `reason_codes`, `zero_purchase_explanation`, `formulas` |

---

## 2. Recommendation Breakdown Response Contract

The backend response for `get_group_recommendation` and `build_recommendation` is extended with a single structured dictionary key: `calculation_breakdown`.

```json
{
  "status": "ok",
  "action": "purchase",
  "priority": "high",
  "group_next_month_forecast": 25.0,
  "group_forecasted_horizon_demand": 100.0,
  "group_safety_stock": 10.1,
  "group_target_stock": 110.1,
  "group_inventory_position": 45.0,
  "group_stock_gap": 65.1,
  "group_suggested_purchase_qty": 66,
  "zero_purchase_explanation": null,
  "calculation_breakdown": {
    "forecast_breakdown": {
      "monthly_forecasts": [25.0, 25.0, 25.0, 25.0],
      "forecasted_horizon_demand": 100.0,
      "selected_model": "trimmed_mean_3",
      "selection_reason": "min_combined_h3_h4_wape_0.1500",
      "history_months": 24,
      "usable_observations": 22,
      "stockout_suppressed_months": 2,
      "demand_pattern": "normal",
      "is_short_history": false,
      "short_history_fallback_used": false,
      "confidence": "normal",
      "wape": 0.15,
      "mase": 0.45,
      "rmse": 6.0,
      "observation_count": 6,
      "warnings": []
    },
    "safety_stock_breakdown": {
      "lead_time_months": 3.0,
      "review_period_months": 1.0,
      "operational_horizon_months": 4.0,
      "service_level": 0.80,
      "z_score": 0.8416,
      "sigma_error_1m": 6.0,
      "horizon_scale_factor": 2.0,
      "sigma_horizon": 12.0,
      "raw_safety_stock": 10.0992,
      "cap_applied": false,
      "cap_value": 150.0,
      "final_safety_stock": 10.1,
      "safety_stock_method": "error_based",
      "dead_stock_safeguard": false
    },
    "inventory_position_breakdown": {
      "usable_stock": 40.0,
      "incoming_stock": 10.0,
      "committed_stock": 5.0,
      "cut_piece_stock_excluded": 0.0,
      "inventory_position": 45.0,
      "formula": "Inventory Position = Usable Stock + Incoming Stock - Committed Customer Demand"
    },
    "target_and_purchase_breakdown": {
      "forecasted_horizon_demand": 100.0,
      "safety_stock": 10.1,
      "target_stock": 110.1,
      "inventory_position": 45.0,
      "stock_gap": 65.1,
      "suggested_purchase_qty": 66,
      "action": "purchase",
      "reason_codes": ["stock_below_target", "positive_forecast"],
      "zero_purchase_explanation": null,
      "formulas": {
        "target_stock": "Target Stock = Forecasted Horizon Demand + Safety Stock",
        "stock_gap": "Stock Gap = max(Target Stock - Inventory Position, 0)",
        "suggested_purchase_qty": "Suggested Purchase Quantity = ceil(Stock Gap)"
      }
    },
    "zero_purchase_explanation": null
  }
}
```

---

## 3. Explanations for Zero-Purchase Cases

When `suggested_purchase_qty == 0`, an explicit human-readable `zero_purchase_explanation` is populated based on actual evidence:

1. **Dead Stock Safeguard**:
   > *"Target stock is 0.00 because product group is classified as dead stock (no recent customer demand)."*
2. **Excess Inventory**:
   > *"Inventory position (126.60) far exceeds target stock (0.00) by excess multiplier (>= 2.0x)."*
3. **Incoming Stock Coverage**:
   > *"Inventory position (450.00) meets target stock (400.00); incoming stock (350.00) covers replenishment requirement."*
4. **Target Met by On-Hand Stock**:
   > *"Inventory position (126.60) already covers target stock (110.00). No purchase gap remaining."*
5. **Zero Demand & Zero Buffer**:
   > *"Forecasted horizon demand (0.00) and safety stock (0.00) are both zero. Target stock is 0.00."*

---

## 4. Mentor Cases & Verification Results

| Case | Product Group | Key Inputs & Setup | Returned Action & Purchase Qty | Verified Breakdown Explanation |
| :--- | :---: | :--- | :---: | :--- |
| **Incoming Stock Coverage** | **413-11** | Usable: 100, Incoming: 350, Target: 400 | `hold` (Purch: 0) | `zero_purchase_explanation`: *"Inventory position (450.00) meets target stock (400.00); incoming stock (350.00) covers replenishment requirement."* Reason codes include `covered_by_incoming_stock`. |
| **Seasonal Forecast Replenishment** | **325-42** | Seasonal Naive model, $D_{horizon} > 0$ | `purchase` / `hold` | Forecast breakdown reflects multi-step seasonal horizon. Target Stock = $D_{horizon} + \text{SS}$. |
| **Dead-Stock Safeguard** | **Dead Stock Group** | 0 sales in $\ge 6$ months, Stock: 50 | `dead_stock` (Purch: 0) | `zero_purchase_explanation`: *"Target stock is 0.00 because product group is classified as dead stock (no recent customer demand)."* SS Method: `dead_stock`. |
| **Task 10 Short-History Group** | **Recent Launch** | $N_{usable} = 8$ observations ($6 \le N < 14$) | `ok` (Purch: 0 or >0) | `is_short_history = true`, `short_history_fallback_used = true`, model: `trimmed_mean_3`, reason: `short_history_robust_default`. |

---

## 5. Regression & Formula Invariance Verification

Comparing pre-Task 11 and post-Task 11 outputs across all test cohorts and Odoo snapshots:

- **Selected Model**: **100% Identical**
- **Forecast Values ($h=1..4$)**: **100% Identical**
- **Horizon Demand ($D_{horizon}$)**: **100% Identical**
- **Safety Stock ($\text{SS}$)**: **100% Identical**
- **Target Stock**: **100% Identical**
- **Inventory Position ($\text{IP}$)**: **100% Identical**
- **Stock Gap**: **100% Identical**
- **Suggested Purchase Qty**: **100% Identical**
- **Action & Reason Codes**: **100% Identical**

---

## 6. Test Suite Summary

- **Task 11 Dedicated Unit Tests**: **10 passed** (`test_recommendation_breakdown.py`)
  - `test_forecast_breakdown_identities`: PASS
  - `test_safety_stock_breakdown_identities`: PASS
  - `test_inventory_position_arithmetic`: PASS
  - `test_negative_inventory_position_no_clamping`: PASS
  - `test_stock_gap_and_purchase_qty_arithmetic`: PASS
  - `test_zero_purchase_explanations`: PASS
  - `test_mentor_case_413_11_incoming_coverage`: PASS
  - `test_short_history_breakdown_diagnostics`: PASS
  - `test_missing_nan_inf_handling`: PASS
  - `test_invariance_before_and_after_task11`: PASS
- **Backend Test Suite**: **237 passed, 1 skipped, 0 failures**
- **Forecasting Engine Test Suite**: **2 passed, 0 failures**

---

## 7. Odoo Read-Only Isolation Confirmation

- **Purchase Orders Written**: 0
- **RFQs Written**: 0
- **Stock Moves Created**: 0
- **Stock Quants Mutated**: 0
- **Database Schema Changes**: 0
- **Status**: 100% Read-Only & Isolated.

---

## 8. Artifact Deliverables

1. Markdown Report: `PHASE2_TASK11_RECOMMENDATION_BREAKDOWN.md`
2. Machine-Readable CSV: `task11_recommendation_breakdown.csv`
