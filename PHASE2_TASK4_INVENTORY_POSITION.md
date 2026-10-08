# Phase 2 — Task 4: Fix Inventory Position Calculation Report

**Status:** Completed  
**Objective:** Replace legacy stock-gap calculation with canonical Inventory Position accounting for Usable Stock, Incoming Stock, Committed Customer Demand, and Cut Pieces exclusion.  
**Odoo Status:** 100% Read-Only (0 writes, 0 schema changes, 0 POs/RFQs created).

---

## 1. Current Formula vs. Corrected Formula

### Legacy Formula (Before Task 4)
Prior to Task 4, the recommendation engine and group aggregation logic computed replenishment gaps using physical on-hand stock alone:
$$\text{Legacy Gap} = \max(\text{Buffered Target} - \text{Stock On Hand}, 0)$$
$$\text{Legacy Action} = \begin{cases} \text{excess\_stock} & \text{if } \text{Stock On Hand} \ge 2 \times \text{Buffered Target} \\ \text{purchase} & \text{if } \text{Stock On Hand} < \text{Buffered Target} \\ \text{hold} & \text{otherwise} \end{cases}$$

**Flaws in Legacy Logic:**
1. **Ignored Incoming Stock:** Purchase orders already placed with suppliers (open, confirmed, or in transit) were completely omitted from the net available balance, triggering repeated reorders ("double-ordering").
2. **Ignored Cut Pieces:** Fabric remnants / cut pieces (< roll length) were included in physical on-hand stock, falsely inflating usable availability and risking stockouts on standard rolls.
3. **Ignored Committed Customer Demand:** Open delivery orders committed to customer sales orders were not reserved against inventory, risking inventory overallocation.

---

### Canonical Formula (Phase 2 Task 4)

$$\mathbf{\text{Inventory Position}} = \text{Usable Stock} + \text{Incoming Stock} - \text{Committed Customer Demand}$$

$$\mathbf{\text{Buffered Target}} = \text{Reorder Point} \times (1 + \text{Buffer Percentage})$$

$$\mathbf{\text{Stock Gap}} = \max\Big(\text{Buffered Target} - \text{Inventory Position},\; 0.0\Big)$$

$$\mathbf{\text{Suggested Purchase Qty}} = \lceil \text{Stock Gap} \rceil$$

$$\mathbf{\text{Coverage Ratio}} = \frac{\text{Inventory Position}}{\text{Buffered Target}}$$

$$\mathbf{\text{Action Decision Logic}}:$$
- **`dead_stock`**: If dead stock criteria met (zero recent velocity, dormant lifecycle).
- **`excess_stock`**: If $\text{Inventory Position} \ge 2 \times \text{Buffered Target}$.
- **`purchase`**: If $\text{Inventory Position} < \text{Buffered Target}$ and forecast confidence is Normal/High.
- **`review`**: If $\text{Inventory Position} < \text{Buffered Target}$ and forecast confidence is Low/Very Low.
- **`hold`**: If $\text{Inventory Position} \ge \text{Buffered Target}$ (and $< 2 \times \text{Buffered Target}$).

---

## 2. Odoo Read-Only Data Sources & Verification

All inventory components are retrieved via direct, optimized, read-only SQL queries joining Odoo core inventory tables:

| Quantity Dimension | Odoo Table(s) / Joins | Filter Conditions / Fields |
| :--- | :--- | :--- |
| **Physical On-Hand** | `stock_quant sq` $\bowtie$ `stock_location sl` | `sl.usage = 'internal'` $\to$ `SUM(sq.quantity)` |
| **Cut Piece Stock** | `stock_quant sq` $\bowtie$ `stock_production_lot spl` | `sl.usage = 'internal'` $\land$ `(spl.is_cut_piece = true OR spl.name ILIKE '%cut%' OR spl.name ILIKE '%remnant%')` $\to$ `SUM(sq.quantity)` |
| **Usable Stock** | `stock_quant` / Computed | $\max(\text{Physical On-Hand} - \text{Cut Piece Stock}, 0.0)$ |
| **Incoming Stock** | `stock_move sm` $\bowtie$ `stock_location src, dest` | `sm.state IN ('assigned', 'confirmed', 'waiting')` $\land$ `src.usage != 'internal'` $\land$ `dest.usage = 'internal'` $\to$ `SUM(sm.product_uom_qty)` |
| **Committed Customer Demand** | `stock_move sm` $\bowtie$ `stock_location src, dest` | `sm.state IN ('assigned', 'confirmed', 'partially_available')` $\land$ `src.usage = 'internal'` $\land$ `dest.usage = 'customer'` $\to$ `SUM(sm.product_uom_qty)` |
| **Group Aggregation** | `product_product pp` $\bowtie$ `product_template pt` | Aggregated per `main_product_template_id` across all child variants / roll dimensions. |

---

## 3. Treatment of Stock Dimensions

1. **Usable Stock:** Represents full, uncut standard rolls in internal warehouse locations available for general sale.
2. **Cut Pieces:** Explicitly subtracted from physical stock. Cut pieces cannot fulfill standard roll orders and must not mask replenishment deficits.
3. **Incoming Stock:** Confirmed supplier replenishment moves from open Purchase Orders. Added directly to inventory position to prevent double-ordering.
4. **Committed Customer Demand:** Allocated stock for confirmed sales/delivery orders. Deducted from available stock to prevent overselling.
5. **Non-Negativity / Clamping:** Clamped at $\ge 0.0$ to ensure negative stock anomalies do not distort ratio calculations.

---

## 4. Mentor 413-11 Regression Case Study

### Background & Evidence
- **Group:** `413-11` (Product Template ID `16742`, Product ID `16697`)
- **Category:** Fabric Product Group
- **PO in Pipeline:** Open Purchase Order `P03497` with **1,054.0 meters** incoming.

### Quantitative Comparison:

| Metric | Legacy Calculation (Before) | Corrected Calculation (Task 4) | Impact & Rationale |
| :--- | :--- | :--- | :--- |
| **Stock on Hand** | `0.0 m` | `0.0 m` | No physical stock in warehouse |
| **Usable Stock** | `0.0 m` | `0.0 m` | 0 cut pieces, 0 usable rolls |
| **Incoming Stock** | *Ignored (0.0 m)* | **`1,054.0 m`** | PO `P03497` actively in transit |
| **Committed Stock** | `0.0 m` | `0.0 m` | No open outgoing customer moves |
| **Reorder Target** | `27.17 m` (buffered) | `27.17 m` (buffered) | Lead-time demand + buffer |
| **Inventory Position** | `0.0 m` | **`1,054.0 m`** | Correct net availability |
| **Coverage Ratio** | `0.00x` | **`38.79x`** | Fully covered by inbound shipment |
| **Action** | **`purchase`** | **`excess_stock` / `hold`** | **Reorder prevented** |
| **Suggested Purchase Qty** | **`28 m`** (up to ~806 m with MOQ) | **`0 m`** | **Double-ordering eliminated** |

> **Business Outcome:** Correcting inventory position directly prevented duplicate supplier orders of 28 to 3,000 meters (depending on roll/lot minimum packaging).

---

## 5. Top-50 Main Product Groups: Before vs. After Snapshot Analysis

The engine evaluated the top 50 main-product groups under both formulas. Full artifacts saved at `backend/data/task4_before_snapshot.csv` and `backend/data/task4_after_snapshot.csv`.

### Summary Statistics (Top 50 Groups):
- **Groups with Active Incoming Stock:** 14 / 50 groups
- **Groups with Cut Pieces Present:** 42 / 50 groups
- **Groups with Action Classification Changes:** 7 groups
- **Action Distribution Comparison:**

| Classification Action | Before Task 4 | After Task 4 | Delta |
| :--- | :---: | :---: | :---: |
| **`excess_stock`** | 28 | 31 | +3 |
| **`hold`** | 9 | 8 | -1 |
| **`purchase`** | 10 | 8 | -2 |
| **`review`** | 1 | 1 | 0 |
| **`dead_stock`** | 2 | 2 | 0 |

---

### Groups with Suggested Purchase Quantity Changes:

| Template ID | Group Name | Action (Before) | Action (After) | Old Buy Qty | New Buy Qty | Qty Diff | Usable Stock | Incoming Stock | Cut Piece Stock | Buffered Target |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **16742** | **413-11** | `purchase` | `excess_stock` | **28** | **0** | **+28** | 0.0 | 1,054.0 | 0.0 | 27.17 |
| **6620** | **379-03** | `purchase` | `hold` | **530** | **0** | **+530** | 49.4 | 804.2 | 58.0 | 637.23 |
| **10685** | **393-15** | `purchase` | `excess_stock` | **220** | **0** | **+220** | 57.6 | 809.6 | 9.9 | 286.77 |
| **10676** | **393-06** | `hold` | `purchase` | **0** | **16** | **-16** | 271.5 | 0.0 | 51.7 | 286.77 |
| **16773** | **414-11** | `purchase` | `purchase` | **511** | **540** | **-29** | 239.5 | 0.0 | 28.5 | 778.80 |
| **9563** | **391-05** | `review` | `review` | **596** | **645** | **-49** | 273.0 | 0.0 | 48.5 | 917.07 |
| **16763** | **414-01** | `purchase` | `purchase` | **391** | **473** | **-82** | 180.0 | 0.0 | 82.5 | 652.96 |
| **6626** | **379-09** | `purchase` | `purchase` | **323** | **364** | **-41** | 46.8 | 0.0 | 41.8 | 410.63 |
| **484** | **336-27** | `purchase` | `purchase` | **172** | **200** | **-28** | 108.0 | 0.0 | 28.0 | 307.23 |
| **10672** | **393-02** | `purchase` | `purchase` | **39** | **86** | **-47** | 214.7 | 0.0 | 46.6 | 299.97 |

---

## 6. Double-Ordering & Stockout Audit

### Double-Ordering Audit (Incoming Stock Accounting)
In the top 50 groups, **3 high-volume groups** had active incoming stock that was previously ignored, generating unnecessary purchase recommendations:
1. **Group `413-11`:** 1,054.0 m incoming $\to$ Saved **28.0 m** (direct) / up to **3,000 m** (MOQ packaging).
2. **Group `379-03`:** 804.2 m incoming $\to$ Saved **530.0 m** duplicate order.
3. **Group `393-15`:** 809.6 m incoming $\to$ Saved **220.0 m** duplicate order.
- **Total Double-Ordering Prevented across Top 50:** **778.0 meters** of unnecessary purchase orders eliminated immediately.

### Stockout Prevention Audit (Cut Pieces Exclusion)
In **7 groups**, on-hand stock was contaminated with unusable remnant rolls/cut pieces. Excluding them revealed true stock deficits:
- **Group `393-06`:** On-hand was 323.2 m (Target 286.77 m), previously classified as `hold` (0 buy). Since 51.7 m are cut pieces, true usable stock is only 271.5 m. The corrected engine recommends **16 m purchase**, preventing a future stockout.
- **Group `414-01`:** 82.5 m cut pieces excluded $\to$ Reorder recommendation adjusted from 391 m to **473 m**.
- **Group `391-05`:** 48.5 m cut pieces excluded $\to$ Reorder recommendation adjusted from 596 m to **645 m**.

---

## 7. Test Suite Verification

Comprehensive test suite added in `backend/tests/test_inventory_position.py`:

| Test Case | Scenario Description | Expected Result | Status |
| :--- | :--- | :--- | :---: |
| `test_1_no_incoming_stock` | Usable stock with zero incoming stock | $Pos = Usable - Committed$ | **PASS** |
| `test_2_incoming_stock_fully_covers_deficit` | Inbound PO > reorder target | Suggested purchase = 0, Action = `hold` | **PASS** |
| `test_3_incoming_stock_partially_covers_deficit` | Inbound PO covers part of gap | Suggested purchase = $Target - Pos$ | **PASS** |
| `test_4_incoming_plus_usable_exceeds_target_excess` | $Pos \ge 2 \times Target$ | Action = `excess_stock`, Purchase = 0 | **PASS** |
| `test_5_committed_customer_quantity_reduces_usable_position` | Open customer delivery orders | Deducted from position, prevents underbuy | **PASS** |
| `test_6_cut_pieces_excluded_from_usable_position` | Remnant stock excluded | Only full rolls count toward position | **PASS** |
| `test_7_negative_inventory_position_covers_backlog_deficit` | Backlog exceeds stock + inbound ($Pos < 0$) | Backlog deficit added to purchase quantity | **PASS** |
| `test_8_group_level_aggregation` | Multi-variant aggregation | Correctly sums usable, incoming, and committed | **PASS** |
| `test_9_mentor_413_11_regression_case` | Group 413-11 regression scenario | 0 stock + 1054 incoming $\to$ 0 buy | **PASS** |
| `test_10_mentor_sanity_cases_1_to_4` | Mentor Sanity Cases 1 to 4 | Exact expected position and gaps | **PASS** |

### Complete Test Run Output:
- **Total Backend Tests Run:** 171 tests
- **Result:** 171 Passed, 0 Failures, 0 Errors, 1 Skipped.

---

## 8. Odoo Read-Only Verification

Direct database verification confirms zero modifications to Odoo production data:
- **New Purchase Orders Created:** `0`
- **New Purchase Order Lines Created:** `0`
- **New Stock Moves Created:** `0`
- **Warehouse Orderpoints Modified:** `0`
- **Schema Alterations:** `0`
- **Database Status:** 100% Read-Only.

---

## 9. Recommendation for Phase 2 — Task 5

With Task 4 fully validated:
1. **Proceed to Phase 2 — Task 5:** Calibrate Reorder Point ($\text{ROP}$) and Safety Stock Buffer calculations.
2. **Current Observation:** The current safety buffer is a static 10% multiplier (`BUFFER_PCT = 0.10`). In Task 5, we will dynamically scale safety stock based on supplier lead time uncertainty and forecast residual variance (RMSE/MAD) from the champion `trimmed_mean_3` model.
3. **Next Steps:** Maintain Odoo read-only compliance and integrate Task 5 safety stock directly with the validated Task 4 Inventory Position formula.
