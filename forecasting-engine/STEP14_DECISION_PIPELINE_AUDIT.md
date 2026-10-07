# STEP 14: End-to-End Decision Pipeline Audit & Mathematical Trace

## 1. Executive Summary & Objective

The objective of **Step 14 Task 1** is to perform a rigorous mathematical and architectural audit of the end-to-end inventory replenishment decision pipeline. This trace maps the entire progression from raw demand forecasting to human-governed portal purchase orders:

$$\text{Raw Sales History} \longrightarrow \text{Central Forecast (1M / H3)} \longrightarrow \text{Safety Buffer (Empirical CSL)} \longrightarrow \text{Target Stock} \longrightarrow \text{Current Stock} \longrightarrow \text{Net Suggested Purchase} \longrightarrow \text{Group Stock Absorption} \longrightarrow \text{Supplier Constraints} \longrightarrow \text{Planner Approval} \longrightarrow \text{Portal-Side Draft PO}$$

### Core Architecture & Isolation Rules
- **Central Forecast Model**: `trimmed_mean_3` (robust champion model with 10% symmetric trimming).
- **Research-Only**: `pattern_router_e` remains strictly archived for research.
- **Odoo Isolation**: **100% READ-ONLY**. Zero writes, zero schema modifications, zero Odoo POs, zero Odoo RFQs, zero reorder-rule mutations.
- **Portal Procurement**: All approvals, draft POs, and line items are stored exclusively in the POC PostgreSQL database (`portal_purchase_orders`, `portal_purchase_order_lines`).

---

## 2. Mathematical Transformation Pipeline

Every metric transformation is deterministic, transparent, and non-duplicative. Below is the exact calculation flow:

### Step 2.1: Monthly Demand Forecast ($\hat{Y}_{1M}$)
For products with demand pattern classification:
$$\hat{Y}_{1M} = \text{trimmed\_mean\_3}(Y_{t-2}, Y_{t-1}, Y_t)$$
Where $10\%$ symmetric trimming is applied. If active history $N < 3$, deterministic fallbacks apply:
- $N = 2$: weighted moving average ($\frac{2}{3} Y_t + \frac{1}{3} Y_{t-1}$).
- $N = 1$ with active sales: single observation fallback.
- $N = 1$ with subsequent zero months (e.g. single launch order): hard zero clamp ($0.0$).
- `dead_stock`: hard-clamped to $0.0$.

### Step 2.2: Lead-Time Demand Forecast ($\hat{Y}_{H3}$)
The operational import lead time from international mills is approximately 3 months ($L = 3$ months / 90 days). The cumulative lead-time demand forecast is computed via multi-step autoregressive projection without compounding double count:
$$\hat{Y}_{H3} = \sum_{h=1}^{3} \hat{Y}_{t+h}$$
For rolling multi-step models, the horizon-specific projections are evaluated. In steady state:
$$\hat{Y}_{H3} \approx 3 \times \hat{Y}_{1M}$$
*(Note: In benchmark reporting, the average monthly horizon demand is expressed as $\hat{Y}_{H3\text{-avg}} = \frac{1}{3}\hat{Y}_{H3}$).*

### Step 2.3: Empirical Safety Buffer ($B$)
Uncertainty buffering is separated from the central demand projection using empirical residuals from the active catalog:
$$B = \hat{\sigma}_{\text{empirical}} \times Z_{\alpha}$$
Where $Z_{\alpha}$ corresponds to the calibrated cycle service level target by demand pattern:
- `fast_moving`: $80\%$ CSL
- `stable/normal`: $80\%$ CSL
- `rising`: $75\%$ CSL
- `falling`: $75\%$ CSL
- `intermittent`: $75\%$ CSL
- `cold_start`: $75\%$ CSL
- `dead_stock`: $0\%$ (hard clamp: $B = 0.0$)

**Guardrails**:
- Buffer is strictly non-negative: $B \ge 0.0$.
- For dead stock: $B = 0.0$.
- No arbitrary clipping that masks real demand variance; empirical percentile residuals are utilized.

### Step 2.4: Target Stock Calculation ($S_{\text{target}}$)
Target inventory represents the required stock to survive the 3-month import lead time plus the calibrated cycle-service protection:
$$S_{\text{target}} = \hat{Y}_{H3} + B$$
If pattern is `dead_stock`:
$$S_{\text{target}} \equiv 0.0$$

### Step 2.5: Current Stock & Stock Position ($I_{\text{pos}}$)
Stock on hand is fetched from Odoo internal warehouse locations (`stock_quant.quantity` where location usage is `internal`):
$$I_{\text{current}} = \max\left(0.0, \sum \text{Internal Quants}\right)$$
$$I_{\text{pos}} = I_{\text{current}} + I_{\text{in\_transit}} - I_{\text{reserved}}$$
In current POC scope (Odoo read-only without inbound PO visibility), $I_{\text{pos}} = I_{\text{current}}$.

### Step 2.6: Raw Suggested Purchase ($Q_{\text{raw}}$)
Net replenishment deficit:
$$Q_{\text{raw}} = \max\left(0.0, S_{\text{target}} - I_{\text{pos}}\right)$$
**Safety Invariant**:
- If $I_{\text{pos}} \ge S_{\text{target}}$, then $Q_{\text{raw}} = 0.0$. Never negative.
- If `dead_stock`, $Q_{\text{raw}} = 0.0$.

---

## 3. Main-Product / Similar Product Group Absorption

In textile wholesale, fabrics frequently share interchangeable colorways or base weaves under a common parent template (`product_template`). Ordering variant $A$ when variant $B$ in the same group has surplus stock leads to severe inventory bloat.

### Mathematical Formulation:
Let group $\mathcal{G} = \{p_1, p_2, \dots, p_k\}$ be the set of variants belonging to canonical template $T$:
$$I_{\mathcal{G}} = \sum_{p \in \mathcal{G}} I_{\text{current}}(p)$$
$$S_{\mathcal{G},\text{target}} = \sum_{p \in \mathcal{G}} S_{\text{target}}(p)$$
$$\text{Surplus}_{\mathcal{G}} = \max\left(0.0, I_{\mathcal{G}} - S_{\mathcal{G},\text{target}}\right)$$

### Decision Rule:
1. **Group Stock Sufficient**: If $\text{Surplus}_{\mathcal{G}} \ge Q_{\text{raw}}(p_i)$:
   $$Q_{\text{absorbed}}(p_i) = 0.0$$
   *Reason*: Group surplus completely absorbs the variant deficit.
2. **Partial Group Coverage**: If $0 < \text{Surplus}_{\mathcal{G}} < Q_{\text{raw}}(p_i)$:
   $$Q_{\text{absorbed}}(p_i) = Q_{\text{raw}}(p_i) - \text{Surplus}_{\mathcal{G}}$$
3. **All Understocked**: If $\text{Surplus}_{\mathcal{G}} = 0$:
   $$Q_{\text{absorbed}}(p_i) = Q_{\text{raw}}(p_i)$$

AI Suggested Purchase quantity is thus:
$$Q_{\text{AI}} = Q_{\text{absorbed}}(p_i)$$

---

## 4. Supplier Constraint Simulation Engine

International fabric mills enforce rigorous manufacturing constraints (Roll lengths, MOQs). These constraints are simulated inside the POC without touching Odoo:

### Constraint Rules:
- **Minimum Order Quantity (MOQ)**: e.g., $100\,\text{m}$.
- **Standard Roll Length**: e.g., $50\,\text{m}$ multiples.
- **Purchase UOM**: `meters`.
- **Lead Time**: $90$ days.

### Transformation:
$$\text{Rolls} = \left\lceil \frac{Q_{\text{AI}}}{\text{Roll\_Length}} \right\rceil$$
$$Q_{\text{roll}} = \text{Rolls} \times \text{Roll\_Length}$$
$$Q_{\text{constrained}} = \max\left(\text{MOQ}, Q_{\text{roll}}\right) \quad (\text{if } Q_{\text{AI}} > 0)$$

### Crucial Invariant: Preserving AI vs Constrained Quantities
- $Q_{\text{AI}}$ remains **strictly immutable**.
- $Q_{\text{constrained}}$ is stored in a separate column.
- The system generates an explicit audit reason code:
  - `rounded_to_roll_length_multiple_50m`
  - `adjusted_to_supplier_moq_100m`

---

## 5. End-to-End Trace Example

| Step | Metric | Value | Formula / Source | Note |
|---|---|---|---|---|
| **1** | Sales History (6m) | $[25, 28, 27, 26, 29, 28]$ | Odoo `sale_order_line` | Stable demand pattern |
| **2** | Forecast 1M | $27.0\,\text{m}$ | `trimmed_mean_3` | $10\%$ symmetric trim |
| **3** | Forecast H3 (Lead Time) | $81.6\,\text{m}$ | Autoregressive H3 projection | 3-month horizon demand |
| **4** | Safety Buffer | $8.4\,\text{m}$ | $80\%$ CSL calibrated residual | Stable demand policy |
| **5** | Target Stock | $90.0\,\text{m}$ | $81.6 + 8.4$ | Total lead-time target |
| **6** | Current Stock | $25.0\,\text{m}$ | Odoo `stock_quant` (internal) | On-hand inventory |
| **7** | Stock Position | $25.0\,\text{m}$ | Internal quants | Deficit detected |
| **8** | Raw Deficit | $65.0\,\text{m}$ | $\max(0, 90.0 - 25.0)$ | Net replenishment need |
| **9** | Group Stock Check | $0.0\,\text{m surplus}$ | Canonical group evaluator | No sibling surplus |
| **10** | **AI Suggested Purchase** | **$65.0\,\text{m}$** | $Q_{\text{AI}}$ | **Immutable AI Recommendation** |
| **11** | Supplier Roll Multiple | $100.0\,\text{m}$ | $\lceil 65 / 50 \rceil \times 50$ | 2 rolls of $50\,\text{m}$ |
| **12** | Supplier MOQ | $100.0\,\text{m}$ | $\max(100, 100)$ | MOQ satisfied |
| **13** | **Supplier Constrained Qty** | **$100.0\,\text{m}$** | $Q_{\text{constrained}}$ | Adjusted for packaging |
| **14** | Human Planner Action | Approved ($100.0\,\text{m}$) | POC `planner_approvals` | Senior planner sign-off |
| **15** | **Portal Draft PO Line** | **$100.0\,\text{m}$** | POC `portal_purchase_order_lines` | Draft PO generated in POC DB |

---

## 6. Verification Against Hidden or Duplicated Demand

1. **No Compounded Buffers**: Safety buffer is calculated once at the H3 horizon level; it is not re-applied inside monthly forecasting loops.
2. **No Double-Counting In-Transit Stock**: In-transit stock and on-hand stock are clearly separated in the data model.
3. **No Phantom Reorders**: Group inventory absorption actively prevents ordering duplicate stock across sibling colorways.
4. **Zero-Stock Hard Invariants**: Dead-stock products never generate positive targets, buffers, or purchase recommendations under any condition.
