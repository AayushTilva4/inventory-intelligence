# Inventory Intelligence — Mentor Codebase Reference Audit

> **Status:** `AUDIT COMPLETE — AWAITING REVIEW BEFORE IMPLEMENTATION`

---

## 1. Executive Summary

This audit performs a technical comparison between the mentor-provided reference codebase (`e:\Inventory-Intelligence-mentor-test` / `e:\AI-Demand-System`) and our current working codebase (`e:\Agent`).

The current working codebase incorporates all **Phase 2 Tasks 4–11** requirements:
- **Task 4**: Canonical Inventory Position ($\text{IP} = \text{Usable Stock} + \text{Incoming Stock} - \text{Committed Demand}$)
- **Task 5**: Operational Replenishment Horizon ($H = L + R = 4\text{ months}$) with $w_0$ partial-month weighting
- **Task 6**: Evidence-Based Error Safety Stock ($SS = \min(Z_{\alpha} \times \sqrt{H} \times \sigma_{1M}, \text{Cap})$)
- **Task 7**: Real Out-of-Sample Error Forecast Confidence (uncoupled from purchase action override)
- **Task 8**: Multi-Origin Operational Model Selection ($H=3, 4$ rolling backtesting across 6 origins)
- **Task 9**: Evidence-Based Stockout Censoring (`STOCKOUT_SUPPRESSED` missing demand treatment)
- **Task 10**: Short-History Forecasting ($6 \le N < 18\text{ months}$, `trimmed_mean_3` robust fallback, $N < 12$ annual seasonality prohibition)
- **Task 11**: Recommendation Calculation Breakdown (`forecast_breakdown`, `safety_stock_breakdown`, `inventory_position_breakdown`, `target_and_purchase_breakdown`, `zero_purchase_explanation`)

### Key Finding
Our current working codebase is **substantially more advanced, mathematically rigorous, and accurate** than the mentor reference ZIP. The mentor reference contains older baseline implementations (e.g. fixed 10% safety stock fallback, rigid 19-month minimum history gatekeeper, 1-step WAPE model selection, unhandled stockouts). 

However, the mentor reference provides **two high-value architectural components** worth adapting in future iterations:
1. **MCP Server Tooling Sidecar** (`forecasting-engine/mcp_server/server.py`) for LLM agent integration.
2. **Cold-Start Similar Product Analogue Utility** (`forecasting-engine/src/similar_products.py`) for brand-new products with 0–5 months of sales history.

---

## 2. Established Code States & Environment Audit

| Property | Current Working Codebase (`e:\Agent`) | Mentor Reference Codebase (`e:\Inventory-Intelligence-mentor-test`) |
| :--- | :--- | :--- |
| **Branch / Commit State** | `main` branch (up to date with `origin/main`), clean local modifications for Tasks 10–11 | Initial snapshot / reference release |
| **Total Source Files** | 258 files | 130 files |
| **Backend Test Suite** | 247 passed, 1 skipped (248 collected tests in `backend/tests/`) | 2 passed (baseline correctness) |
| **Forecasting Engine Tests** | 2 passed (`forecasting-engine/tests/`) | 2 passed |
| **Tasks 4–11 Math** | **Fully Implemented & Validated** | Legacy / Pre-Phase-2 Baseline |
| **Odoo Integration** | 100% Read-Only (0 PO, 0 RFQ, 0 move, 0 quant, 0 schema mutations) | Read-Only |

---

## 3. Major Component Comparison & Classification Matrix

Each meaningful architectural or algorithmic difference is evaluated and classified into one of four actions:
- `KEEP CURRENT`: Maintain our validated Task 4–11 implementation (mentor version is a regression).
- `ADAPT`: Modify and integrate mentor feature into our current structure without breaking existing invariants.
- `ADOPT`: Import modular mentor helper directly.
- `INVESTIGATE`: Conduct further benchmarking before deciding.

| Component & File Path | Mentor Implementation | Current Working Implementation (`e:\Agent`) | Specific Advantage & Supporting Evidence | Risk of Adopting Mentor Code | Domain | Audit Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **Model Selection**<br>`model_selection.py` | Single-origin test holdout ($H=1$) using basic 1-step WAPE in `evaluation.py` | Task 8 multi-origin operational horizon evaluation ($H=3, 4$) across 6 rolling origins with combined WAPE/MAE scoring | Current Task 8 selector reduces model switching from 18/40 groups down to <5/40 groups and lowers H4 WAPE across all tiers | Adopting mentor code would degrade model stability and increase asymmetric replenishment loss | Accuracy & Correctness | **`KEEP CURRENT`** |
| **Safety Stock**<br>`safety_stock_service.py` | Legacy fixed 10% buffer (`BUFFER_PCT = 0.10`) or fixed 1-month demand in `recommendation_engine.py` | Task 6 evidence-based safety stock ($SS = \min(Z_{\alpha} \times \sqrt{H} \times \sigma_{1M}, \text{Cap})$) with pattern-driven service levels ($Z \in \{0.6745, 0.8416\}$) | Current Task 6 formula scales buffer dynamically based on real OOS forecast error ($\text{RMSE}_{1M}$), protecting high-variance items | Adopting mentor code would return to arbitrary fixed buffers and under-buffer noisy SKUs | Accuracy & Replenishment | **`KEEP CURRENT`** |
| **Short-History Forecasting**<br>`group_forecast_service.py` | Rigid `MINIMUM_HISTORY = 19` gatekeeper; products with <19m receive no forecast | Task 10 safe short-history policy ($N \ge 6$) using `trimmed_mean_3` fallback and strict seasonality prohibition ($N < 12$) | Current Task 10 policy safely enables forecasts for 1,016 additional catalog groups with 6–18m history (including all 10 mentor recent launches) | Adopting mentor code would block 1,016 valid product groups from receiving purchase recommendations | Catalog Coverage | **`KEEP CURRENT`** |
| **Stockout Censoring**<br>`stockout_service.py` | Treats zero-sales months as zero customer demand without inventory verification | Task 9 evidence-based stockout censoring (`STOCKOUT_SUPPRESSED` missing demand treatment verified via Odoo stock moves) | Current Task 9 accurately distinguishes stockouts (e.g. 413-11 falling 342 $\rightarrow$ 0) from real zero-demand months | Adopting mentor code would re-introduce zero-demand bias during stockouts | Data Correctness | **`KEEP CURRENT`** |
| **Recommendation Breakdown**<br>`recommendation_engine.py` | Returns basic summary without calculation breakdown or zero-purchase explanations | Task 11 structured `calculation_breakdown` (`forecast_breakdown`, `safety_stock_breakdown`, `inventory_position_breakdown`, `target_and_purchase_breakdown`, `zero_purchase_explanation`) | Current Task 11 exposes complete mathematical breakdown ($D_{horizon}, \text{SS}, \text{Target}, \text{IP}, \text{Gap}, \text{Purchase}$) for buyer auditability | Adopting mentor code would remove breakdown transparency | Auditability | **`KEEP CURRENT`** |
| **LLM Agent Sidecar**<br>`mcp_server/server.py` | Implements FastMCP server to expose forecasting endpoints to LLM tools | No standalone MCP server running in backend | FastMCP provides clean RPC interface for AI agents to query forecasts, run backtests, and inspect recommendations | Low risk if exposed as read-only sidecar process | Tooling & Integration | **`ADAPT`** |
| **Cold-Start Analogue Helper**<br>`src/similar_products.py` | Computes attribute/sales similarity for products with 0–5 months history | Products with <6m history currently return `insufficient_group_history` | Allows borrowing demand velocity/seasonality shapes for brand-new launches ($0 \le N < 6$) | High risk if analogue forecasts override Task 10 $N \ge 6$ deterministic rules | Cold-Start Extension | **`ADAPT`** |

---

## 4. High-Value Improvements to Consider

### 4.1 MCP Server Tooling Sidecar (`forecasting-engine/mcp_server/server.py`)
- **Concept**: FastMCP server that exposes read-only functions (`get_product_forecast`, `run_backtest`, `get_similar_products`) over Model Context Protocol (MCP).
- **Advantage**: Enables Antigravity and external LLM tools to query forecasting signals directly via standard JSON-RPC without calling frontend REST endpoints.
- **Adaptation Strategy**: Wrap existing backend services (`get_group_forecast`, `get_group_recommendation`) in a dedicated read-only MCP sidecar.

### 4.2 Cold-Start Similar Product Analogue Utility (`forecasting-engine/src/similar_products.py`)
- **Concept**: Finds historical analogue products with $\ge 6$ months of history based on product attributes (category, fabric type, price tier) and historical sales correlation.
- **Advantage**: Provides initial demand estimations for new product launches with 0–5 months of usable history (which are currently returned with `insufficient_group_history`).
- **Adaptation Strategy**: Keep Task 10 $N \ge 6$ minimum history rule intact for automated procurement, but expose similar-product demand estimation as an informational diagnostic for $N < 6$ series.

---

## 5. Regressions & Older Approaches in Mentor Codebase

The audit confirmed that the mentor ZIP contains several older implementations that should **not** be brought into our production codebase:

1. **Fixed 10% Safety Stock Fallback** (`BUFFER_PCT = 0.10`): Arbitrary percentage buffer that fails to account for forecast noise ($\text{RMSE}_{1M}$) or Lead Time ($L=3$) + Review Period ($R=1$) horizon scaling.
2. **Rigid 19-Month History Gatekeeper** (`MINIMUM_HISTORY = 19`): Blocks 1,016 valid short-history product groups (6–18 months) from receiving forecasts.
3. **Single-Step Holdout Model Selection**: Selects models based on 1-month WAPE at a single origin ($H=1$), leading to severe model switching (18/40 groups) when rolling history by 1 month.
4. **Low-Confidence Purchase Action Overrides**: Changing purchase action from `purchase` $\rightarrow$ `review` solely because forecast confidence is `low` (violating Task 7 separation of concerns).
5. **Uncensored Zero Sales Handling**: Interpreting stockout months as true zero demand, which artificially lowers forecasts for fast-moving items following stockouts.

---

## 6. Missing Improvements Neither Version Adequately Addresses

1. **Dynamic Supplier Lead Time & MOQ API Integration**: Both codebases use a hardcoded lead time ($L=3.0$ months). Incorporating real-time supplier lead times and Minimum Order Quantities (MOQs) from supplier master data would improve order rounding.
2. **Real-Time Inventory Event Webhooks**: Currently, stock levels are polled on-demand from Odoo PostgreSQL. A push webhook event listener could trigger instant recalculations when major stock movements occur.
3. **Multi-Warehouse Stock Partitioning**: Current recommendations aggregate total inventory across all locations; partitioning usable stock per warehouse location would prevent regional stockouts.

---

## 7. Plan for Protecting Tasks 4–11 Baseline

To ensure no future refactoring or adaptation breaks existing validated mathematical behavior, the following test suites and files serve as strict regression barriers:

| Task / Feature | Protection File / Test Suite | Invariant Enforced |
| :--- | :--- | :--- |
| **Task 4 (Inventory Position)** | `test_inventory_position.py` | $\text{IP} = \text{Usable} + \text{Incoming} - \text{Committed}$; no clamping of negative IP |
| **Task 5 (Operational Horizon)** | `test_forecast_order_quantity.py` | $H = L + R = 4.0\text{ months}$; $w_0$ partial-month weighting |
| **Task 6 (Error Safety Stock)** | `test_safety_stock_error.py` | $SS = \min(Z_{\alpha} \times \sqrt{H} \times \sigma_{1M}, \text{Cap})$; dead stock = 0 SS |
| **Task 7 (Confidence Diagnostic)** | `test_confidence_error.py` | Real OOS error confidence diagnostic; does not alter recommendation action |
| **Task 8 (Model Selection)** | `test_model_selection.py` | Multi-origin operational evaluation ($H=3, 4$); deterministic tie-breaking |
| **Task 9 (Stockout Censoring)** | `test_stockout_demand.py` | `STOCKOUT_SUPPRESSED` missing demand treatment; 413-11 handling |
| **Task 10 (Short-History 6–18m)** | `test_short_history_forecasting.py` | $N \ge 6$ threshold; `trimmed_mean_3` fallback; $N < 12$ annual seasonality prohibition |
| **Task 11 (Breakdown Contract)** | `test_recommendation_breakdown.py` | Structured `calculation_breakdown` & explicit `zero_purchase_explanation` |

---

## 8. Safe, Incremental Roadmap for Future Iterations

1. **Step 1**: Retain current codebase (`e:\Agent`) baseline core math and test suite (247 backend tests passing).
2. **Step 2**: Adapt Cold-Start Similar Product Analogue Utility for diagnostic display on $0 \le N < 6$ products without overriding Task 10 $N \ge 6$ deterministic rules.
3. **Step 3**: Integrate Read-Only FastMCP Server Sidecar for LLM tools & AI agent RPC.
4. **Step 4**: Execute full regression test suite across all 248 tests to guarantee 100% invariance.

---

## 9. Odoo Read-Only & Isolation Confirmation

- **Purchase Orders Written**: 0
- **RFQs Written**: 0
- **Stock Moves Created**: 0
- **Stock Quants Mutated**: 0
- **Database Schema Changes**: 0
- **Status**: 100% Read-Only & Isolated.

*Audit complete. No source code modifications executed.*
