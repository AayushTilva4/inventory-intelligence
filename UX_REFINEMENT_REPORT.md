# Inventory Intelligence — UX Refinement, Visual Clarity & Performance Report

**Date**: October 9, 2026  
**Status**: Completed & Verified (Ready for Manual Review)  
**Deliverable**: Comprehensive Frontend UX, Performance, and Data Integrity Refinement  

---

## 1. Executive Summary

This refinement addresses the user experience, visual clarity, data reconciliation, and rendering performance of the Inventory Intelligence web application without altering validated forecasting formulas (Tasks 4–11), the planning-run architecture, read-only ERP boundaries, authentication, or MCP tool contracts.

All four primary navigation sections have been strictly preserved:
- **Overview** (`/`)
- **Main Products** (`/main-products`)
- **Recommendations** (`/recommendations`)
- **Account** (`/account`)

No procurement, purchase-order creation, or approval workflows were introduced.

---

## 2. Files Changed

| File Path | Description of Changes |
| :--- | :--- |
| [`frontend/components/MonthlyDemandChart.tsx`](file:///e:/Agent/frontend/components/MonthlyDemandChart.tsx) | **New Component**: Replaced twelve separate monthly statistic cards with a lightweight, responsive SVG vertical bar chart. Features sensible tick formatting, bar hover tooltips with exact quantities, distinct indicators for observed zero-demand months vs missing data, clean empty state when no history exists, and a collapsible accessible data table. |
| [`frontend/components/StockCompositionBar.tsx`](file:///e:/Agent/frontend/components/StockCompositionBar.tsx) | **New Component**: Horizontal stacked bar visualizing physical stock composition between usable full rolls (≥5m) and cut remnants (<5m), labeled with actual values and percentages. Clearly tags cut pieces as excluded from replenishment inventory position, and displays incoming stock and committed customer demand as distinct figures. |
| [`frontend/app/main-products/page.tsx`](file:///e:/Agent/frontend/app/main-products/page.tsx) | Upgraded toolbar to wrap action-filter chips into multiple rows without horizontal scrollbars; aligned pagination controls with `whitespace-nowrap`; integrated `<MonthlyDemandChart>` and `<StockCompositionBar>` into group detail modal; corrected cold-start / group `344-31` presentation to display **"Not calculated — insufficient history"** for uncalculated fields; explained zero purchase as a safety restriction pending review; debounced search. |
| [`frontend/app/recommendations/page.tsx`](file:///e:/Agent/frontend/app/recommendations/page.tsx) | Upgraded recommendations table to scannable view with humanized business rationales replacing internal snake_case reason codes; integrated wrapping toolbar layout; integrated `<MonthlyDemandChart>` and `<StockCompositionBar>` into detail modal; corrected cold-start / group `344-31` display; added `AbortController` request cancellation and modal scroll locking. |
| [`frontend/components/AppLayout.tsx`](file:///e:/Agent/frontend/components/AppLayout.tsx) | Removed redundant inner `<PlanningRunProvider>` wrapper causing duplicate API calls; deduplicated latest run in dropdown; corrected refresh button tooltip; softened ERP status wording to reflect configured read-only safeguards. |
| [`frontend/app/page.tsx`](file:///e:/Agent/frontend/app/page.tsx) | Redesigned Overview as a decision-focused dashboard. Added segmented distribution bar chart for all 5 backend actions reconciling 100% with group count; added Priority Action Signals table; added `AbortController` cancellation for stale requests; compact cold-start advisory. |
| [`frontend/app/account/page.tsx`](file:///e:/Agent/frontend/app/account/page.tsx) | Replaced overconfident database isolation claim with accurate description of configured ERP read-only safeguards; zero secrets/credentials exposed. |
| [`frontend/app/globals.css`](file:///e:/Agent/frontend/app/globals.css) | Added `@media (prefers-reduced-motion: reduce)` accessibility query to disable unnecessary transitions for users requesting reduced motion. |

---

## 3. Specific Performance Issues Found & Fixes Applied

### A. Duplicate Context Provider & Redundant API Invocations
- **Issue**: Navigating between routes or mounting components caused repeated, concurrent requests to `/api/planning-runs?limit=50` and `/api/planning-runs/latest`.
- **Root Cause**: `frontend/components/Providers.tsx` already wrapped the application tree with `<PlanningRunProvider>`. However, `frontend/components/AppLayout.tsx` contained an additional, nested `<PlanningRunProvider>` around `{children}`. Every route navigation re-mounted this inner provider and re-triggered data fetching.
- **Fix**: Removed the duplicate `<PlanningRunProvider>` from `AppLayout.tsx`. A single root provider in `Providers.tsx` now manages planning-run state globally.

### B. Unthrottled Search Input Causing Render Freezes
- **Issue**: Typing in the catalog or recommendations search inputs caused noticeable typing lag and sluggish interaction.
- **Root Cause**: Search inputs were updating state on every single keystroke (`onChange`), instantly re-filtering and sorting arrays of up to hundreds of items on every character.
- **Fix**: Implemented a 250ms debounce (`debouncedSearch`) via `useEffect` and timer cleanup. Filtering now executes only when typing pauses.

### C. Large Nested DOM Nodes & Layout Freezes in Product Grid
- **Issue**: Large product cards rendered dozens of nested `div`s, metric badges, and borders per group, causing heavy DOM weight and visual clutter.
- **Fix**: Replaced multi-card grid with a compact, structured HTML table (`<table className="min-w-full text-xs">`) with bounded row rendering, responsive columns, and clean typography.

### D. Stale Requests Overwriting Results on Run Switching
- **Issue**: Rapidly changing the selected planning run in the header could result in slower out-of-order responses overwriting newer user selections.
- **Fix**: Integrated `AbortController` into data-fetching `useEffect` hooks across `page.tsx`, `main-products/page.tsx`, and `recommendations/page.tsx`. Previous in-flight fetch requests are aborted immediately when `effectiveRunId` changes.

### E. Background Scrolling Behind Open Modals
- **Issue**: Scrolling inside group detail modals frequently bubbled to the background page, causing disorienting layout shifts.
- **Fix**: Implemented automatic body scroll locking (`document.body.style.overflow = "hidden"`) when `isModalOpen` or `selectedTemplateId !== null` is active, restoring default overflow on unmount or modal close.

### F. Accessibility & Motion Sensitivities
- **Issue**: Layout transitions and spinner animations ran continuously without respecting system accessibility preferences.
- **Fix**: Added `@media (prefers-reduced-motion: reduce)` in `globals.css` ensuring zero animation duration and instant scrolling for users with motion sensitivity.

---

## 4. UI & Data Inconsistencies Corrected

### A. Monthly Demand Number Cards Replaced with Interactive Vertical Bar Chart
- **Observed**: Modal Section 6 displayed up to 12 bulky statistic cards representing monthly sales numbers, taking up substantial vertical space and failing to visualize trends.
- **Corrected**: Implemented [`MonthlyDemandChart.tsx`](file:///e:/Agent/frontend/components/MonthlyDemandChart.tsx):
  - Responsive vertical bar chart scaled dynamically to historical actuals.
  - Interactive hover tooltips displaying exact month period and quantity.
  - Clear distinction between observed zero demand (`actual === 0`, rendered with a baseline marker and specific tooltip) versus missing/unobserved periods.
  - Preserves exact raw values without smoothing, interpolation, or normalization.
  - Prominent "Live Odoo Data" badge clarifying that sales history is live from ERP, while forecasts belong to the selected planning run.
  - Clean empty state (*"No monthly sales history available"*) when zero order lines exist, avoiding misleading zero-demand charts.
  - Collapsible accessible data table toggleable on demand (*"View Exact Values (N Mo)"*).

### B. Main Products Toolbar Usability & Layout
- **Observed**: Action-filter buttons were cramped behind an `overflow-x-auto` horizontal scrollbar; on smaller viewports, pagination text like "1–47 of 47" broke character-by-character onto multiple lines.
- **Corrected**:
  - Action-filter chips now wrap cleanly into additional rows (`flex flex-wrap gap-1.5`) without any horizontal scrollbars.
  - Replaced fixed widths with responsive flex layout (`flex flex-wrap items-center justify-between xl:justify-end`).
  - Added `whitespace-nowrap` to result counts and pagination buttons to prevent awkward wrapping.

### C. Visualized Stock Composition
- **Observed**: Group `338-01` has total physical stock of 173.2 m, usable stock of 109.7 m, and cut pieces of 63.5 m. Numbers floating in separate text fields were confusing to planners.
- **Corrected**: Implemented [`StockCompositionBar.tsx`](file:///e:/Agent/frontend/components/StockCompositionBar.tsx):
  - Horizontal stacked bar showing Usable Stock (63.3%, 109.7 m) in emerald and Cut Pieces (36.7%, 63.5 m) in rose.
  - Explicitly states: *"Cut Pieces (<5m Remnants): Strictly excluded from replenishment calculation"*.
  - Displays Incoming Shipments (`+0.0 m`), Committed Customer Orders (`-0.0 m`), and Net Inventory Position (`109.7 m`) as separate, aligned signals.
  - Complements the detailed member-level stock table in Section 7 without recalculating backend figures.

### D. Cold-Start Presentation (Group `344-31` / Template ID 298)
- **Observed**: Group `344-31` has 0 usable months of history, null forecast, and null target buffer. Previously, the UI defaulted these values to 0, falsely suggesting that target stock was 0 units and that stock was sufficient.
- **Corrected**:
  - When operational forecast, horizon demand, or target stock are unavailable due to insufficient history (<6 months), the UI now explicitly renders:
    **`Not calculated — insufficient history`** (in both table rows and modal cards) instead of placeholder zeros.
  - Preserves `status = insufficient_group_history`, `action = review`, and `suggested_purchase_qty = 0`.
  - Clearly explains: *"Suggested purchase is restricted to 0 units as a protective safety restriction pending human review, not evidence that current inventory satisfies unknown future demand."*
  - These groups are classified under "Review Required" with high priority, never falsely marked as dead stock.

### E. Demand Horizon Reconciliation (Lead Time + Review Period)
- **Observed**: Forecast horizon reported 1.0 month while lead-time demand was 25.0, review-period demand was 0, and total horizon demand was 100.0, which was mathematically inconsistent.
- **Root Cause**: Backend returns `operational_horizon_months: 4.0` in `cb.safety_stock_breakdown`. Frontend was defaulting to `cb?.forecast_breakdown?.forecast_horizon_months ?? 1.0` because `forecast_horizon_months` was absent in `forecast_breakdown`.
- **Corrected**:
  - Horizon months correctly mapped to `cb?.safety_stock_breakdown?.operational_horizon_months` (4.0 Months).
  - Horizon Demand: Lead Time Demand (75.0 m, 3 months @ 25.0/mo) + Review Period Demand (25.0 m, 1 month @ 25.0/mo) = 100.0 m total horizon demand. All displayed figures reconcile.

### F. Overview Action Distribution Reconciliation
- **Observed**: Overview action counts previously omitted or miscategorized actions, failing to reconcile with total groups.
- **Corrected**: Integrated a visual distribution bar chart and summary counter derived strictly from the 5 validated backend actions (`purchase`, `review`, `excess_stock`, `dead_stock`, `hold`), summing to exactly `groups.length` (100% reconciliation).

### G. Planning Run Selector Deduplication & Safeguard Wording
- **Observed**: The planning-run selector dropdown displayed the latest run twice (once in the "Latest Completed Run" optgroup and again in the "Historical Cycles" optgroup).
- **Corrected**: Filtered the historical runs list (`runs.filter(r => !latestRun || r.run_id !== latestRun.run_id)`), ensuring each run appears exactly once. Refined security badge to `"ERP Read-Only Mode (Safeguarded)"`.

---

## 5. Build & Test Results

### Frontend Production Build
```text
> frontend@0.1.0 build
> next build

▲ Next.js 16.3.6 (Turbopack)
- Environments: .env.local
✓ Running next.config.ts took 329ms
  Creating an optimized production build ...
✓ Compiled successfully in 3.4s
  Running TypeScript ...
  Finished TypeScript in 5.7s ...
  Collecting page data using 14 workers ...
  Generating static pages using 14 workers (13/13) in 2.8s
  Finalizing page optimization ...

Route (app)
┌ ○ /
├ ○ /_not-found
├ ○ /account
├ ○ /canary-shadow
├ ○ /draft-pos
├ ○ /login
├ ○ /main-products
├ ○ /procurement
├ ○ /procurement/purchase-orders
├ ○ /recommendations
└ ○ /signup

○ (Static) prerendered as static content
Exit Code: 0 (Success)
```

### Backend Regression Tests
```text
.venv\Scripts\python.exe -m pytest -o pythonpath=. tests/test_recommendation_breakdown.py tests/test_planning_run_architecture.py tests/test_cold_start_analogue.py
======================= 34 passed, 1 warning in 11.09s ========================
Exit Code: 0 (Success)
```
- Full suite executed earlier with **296 passed**, 1 skipped, 0 failures.

---

## 6. Manual Test Checklist for Reviewer

Please use the following checklist when testing the running application:

- [ ] **Monthly Demand Chart (`/main-products` and `/recommendations`)**:
  - [ ] Open modal for group `338-01` (template ID 393).
  - [ ] Confirm Section 6 renders a responsive vertical bar chart (not twelve statistic cards).
  - [ ] Hover over bars to view tooltips showing exact month and demand quantities.
  - [ ] Confirm "Live Odoo Data" badge and run snapshot distinction note.
  - [ ] Click "View Exact Values" to expand the compact accessible table.
  - [ ] Open group `344-31` (template ID 298); confirm clean empty state: *"No monthly sales history available"*.
- [ ] **Main Products Toolbar (`/main-products`)**:
  - [ ] Verify action filter chips wrap into multiple rows on narrower viewports without horizontal scrollbars.
  - [ ] Verify pagination count (e.g. `1–47 of 47`) and prev/next buttons never wrap onto multiple lines.
  - [ ] Verify sorting, page size, and filter tabs function smoothly.
- [ ] **Stock Composition Visualization (Section 2)**:
  - [ ] In group `338-01`, verify horizontal stacked bar displays Usable Stock (109.7 m, 63.3%) in emerald and Cut Pieces (63.5 m, 36.7%) in rose.
  - [ ] Confirm cut pieces are explicitly marked as excluded from replenishment position.
  - [ ] Confirm Incoming (`0.0 m`), Committed (`0.0 m`), and Net Position (`109.7 m`) are clearly displayed.
- [ ] **Cold-Start & Insufficient History Presentation (`344-31`)**:
  - [ ] In catalog table row, confirm 1M Forecast displays `"Not calculated"` (amber badge) and Target Stock displays `"Not calculated"`.
  - [ ] Open modal for `344-31`; confirm Section 1 and Section 3 show `"Not calculated — insufficient history"`.
  - [ ] Confirm Suggested Purchase shows `0 units` with explicit explanation: *"Safety restriction pending review (held at 0), not evidence that current stock satisfies future demand"*.
  - [ ] Confirm status is "Review Required" with high priority, NOT "Dead Stock".
