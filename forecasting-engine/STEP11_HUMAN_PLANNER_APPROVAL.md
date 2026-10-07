# STEP 11: HUMAN PLANNER APPROVAL WORKFLOW REPORT

## Executive Summary

Following Step 10's successful passive canary shadow deployment, **Step 11 establishes and validates the HUMAN-IN-THE-LOOP APPROVAL WORKFLOW** for the Inventory Intelligence platform.

This milestone operationalizes human governance over AI-generated demand forecasts and safety buffer targets with **strict safety boundaries**:
- **Strictly Isolated from Procurement**: Approving, rejecting, or editing an AI recommendation **does NOT create purchase orders or RFQs in Odoo**, does NOT modify Odoo reorder rules, and writes zero data back to Odoo ERP.
- **Dedicated Governance Storage**: All planner approvals, overrides, and audit trails are persisted exclusively in the separate POC PostgreSQL database (`planner_approvals`, `planner_approval_audit_trail`).
- **Immutable AI Recommendations**: The original AI recommendation (`trimmed_mean_3` forecast, empirical safety buffer, target stock, suggested purchase) is **permanently preserved and never silently overwritten**, even when a human planner overrides quantities.
- **Enforced Safety Controls**: Strict non-negative quantity protection, dead-stock zero target/buy invariants, mandatory rejection/edit reasons, and high-risk category warning governance.
- **Planner Governance UI**: An interactive approval and comparison dashboard prominently labeled: **`AI RECOMMENDATION — REQUIRES PLANNER APPROVAL`**.

---

## 1. Approval Governance Architecture

The platform architecture strictly separates AI shadow recommendation generation, human planner governance, and external ERP procurement:

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                                ODOO ERP DATABASE                                  │
│                 (sale_order_line, stock_quant, product_template)                 │
└─────────────────────────────────────────┬─────────────────────────────────────────┘
                                          │ Read-Only Ingestion (Zero Writes)
                                          ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                    INVENTORY INTELLIGENCE CANARY SHADOW ENGINE                    │
│                        (Frozen trimmed_mean_3 Pipeline)                           │
│                                                                                   │
│  - H1 & H3 Forecasts                                                              │
│  - Pattern-Specific Empirical Safety Buffer (80% / 75% / 0%)                      │
│  - Calibrated Target Stock & Suggested Advisory Purchase                          │
│  - Exception Queue Classification (7 Categories)                                  │
└─────────────────────────────────────────┬─────────────────────────────────────────┘
                                          │ Persist Snapshot Recommendations
                                          ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                            POC POSTGRESQL DATABASE                                │
│                                                                                   │
│  ┌───────────────────────────────┐     ┌────────────────────────────────────────┐ │
│  │       planner_approvals       │     │     planner_approval_audit_trail       │ │
│  │                               │     │                                        │ │
│  │ - approval_id, snapshot_id    │     │ - approval_id, action, timestamp       │ │
│  │ - Original AI Values (Frozen) │────▶│ - Previous Status -> New Status        │ │
│  │ - status: PENDING / APPROVED /│     │ - Original Values (Frozen Snapshot)    │ │
│  │           REJECTED / EDITED   │     │ - Edited Values (Overrides)            │ │
│  │ - edited_target / edited_buy  │     │ - planner_id, mandatory reason         │ │
│  │ - planner_id, comment         │     └────────────────────────────────────────┘ │
│  └───────────────────────────────┘                                                │
└───────────────────────▲───────────────────────────────────▲───────────────────────┘
                        │ Read / Update Status              │ Audit Logging
                        │                                   │
┌───────────────────────┴───────────────────────────────────┴───────────────────────┐
│                            PLANNER GOVERNANCE API                                 │
│                               (/api/approvals)                                    │
│                                                                                   │
│  GET  /api/approvals             POST /api/approvals/{id}/approve                 │
│  GET  /api/approvals/{id}        POST /api/approvals/{id}/reject                  │
│  GET  /api/approvals/summary     POST /api/approvals/{id}/edit                    │
└─────────────────────────────────────────▲─────────────────────────────────────────┘
                                          │ User Actions
                                          ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                         PLANNER COMPARISON & REVIEW UI                            │
│                         (frontend/app/canary-shadow)                              │
│                                                                                   │
│       ★ BANNER: "AI RECOMMENDATION — REQUIRES PLANNER APPROVAL" ★                │
│                                                                                   │
│  - Side-by-Side: Legacy Reorder vs AI Recommendation vs Planner Decision          │
│  - Modal Actions: [Approve], [Reject with Reason], [Edit / Override with Reason] │
│  - Filter Queues: Pending (997), Approved (1), Edited (1), Rejected (1)           │
│                                                                                   │
│  STRICT INVARIANT: APPROVAL DOES NOT CREATE PURCHASE ORDERS IN ODOO               │
└───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Database Schema (POC PostgreSQL)

Two dedicated relational tables manage planner governance in the POC database:

### Table 1: `planner_approvals`
Stores the active governance state for each product recommendation:

| Column Name | Data Type | Constraints / Description |
| :--- | :--- | :--- |
| `approval_id` | VARCHAR(128) | PRIMARY KEY (`appr_<snapshot_id>_<product_id>`) |
| `snapshot_id` | VARCHAR(64) | NOT NULL (Foreign reference to shadow snapshot) |
| `product_id` | INT | NOT NULL (Odoo Product ID) |
| `product_name` | VARCHAR(255) | Product display name |
| `pattern` | VARCHAR(50) | Point-in-time classified demand pattern |
| `forecast_1m` | NUMERIC(12, 2) | Frozen next-month trimmed_mean_3 forecast |
| `forecast_h3` | NUMERIC(12, 2) | Frozen horizon-3 demand forecast |
| `safety_buffer` | NUMERIC(12, 2) | Calibrated safety stock buffer (meters) |
| `service_level` | NUMERIC(5, 2) | Target service level (e.g. 0.80, 0.75, 0.00) |
| `target_stock` | NUMERIC(12, 2) | **Original AI Target Stock (Permanently Preserved)** |
| `current_stock` | NUMERIC(12, 2) | Stock on hand at evaluation time |
| `suggested_purchase`| NUMERIC(12, 2) | **Original AI Suggested Purchase (Permanently Preserved)** |
| `legacy_target` | NUMERIC(12, 2) | Current legacy production reorder point |
| `target_delta` | NUMERIC(12, 2) | AI Target - Legacy Target |
| `exception_category`| VARCHAR(64) | Primary planner exception queue tag |
| `status` | VARCHAR(32) | `CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'EDITED', 'CANCELLED'))` |
| `planner_comment` | TEXT | Planner rationale, approval notes, or rejection reason |
| `edited_target_stock`| NUMERIC(12, 2) | Overridden target stock (NULL unless EDITED) |
| `edited_purchase_qty`| NUMERIC(12, 2) | Overridden purchase quantity (NULL unless EDITED) |
| `planner_id` | VARCHAR(64) | Identifier of reviewing human planner |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `reviewed_at` | TIMESTAMPTZ | Timestamp of human review decision |
| `audit_metadata` | JSONB | Risk classification, lead time, and velocity metadata |

### Table 2: `planner_approval_audit_trail`
Provides an immutable ledger of every governance event:

| Column Name | Data Type | Description |
| :--- | :--- | :--- |
| `id` | SERIAL | PRIMARY KEY |
| `approval_id` | VARCHAR(128) | Foreign Key referencing `planner_approvals` |
| `action` | VARCHAR(32) | `CREATED`, `APPROVED`, `REJECTED`, `EDITED`, `CANCELLED` |
| `previous_status` | VARCHAR(32) | State before action (e.g. `PENDING`) |
| `new_status` | VARCHAR(32) | State after action (e.g. `APPROVED`) |
| `original_values` | JSONB | Frozen snapshot of AI values at decision time |
| `edited_values` | JSONB | Overridden figures (target, purchase qty) |
| `planner_id` | VARCHAR(64) | Reviewing planner identifier |
| `reason_or_comment` | TEXT | Mandatory rationale for edits/rejections; optional for approves |
| `timestamp` | TIMESTAMPTZ | Exact UTC execution timestamp |

---

## 3. Decision States & Transition Rules

```
                          ┌────────────────────────┐
                          │   CANARY SNAPSHOT      │
                          └───────────┬────────────┘
                                      │ Ingest Recommendation
                                      ▼
                          ┌────────────────────────┐
                          │        PENDING         │
                          └───────┬───┬────┬───────┘
            Approve Action        │   │    │      Reject Action
       ┌──────────────────────────┘   │    └──────────────────────────┐
       ▼                              │                               ▼
┌──────────────┐                      ▼ Edit Action            ┌──────────────┐
│   APPROVED   │             ┌─────────────────┐               │   REJECTED   │
│              │             │     EDITED      │               │              │
│ - Preserves  │             │                 │               │ - Preserves  │
│   AI Target  │             │ - Preserves AI  │               │   AI Target  │
│ - Preserves  │   Approve   │   Target & Buy  │               │ - Requires   │
│   AI Buy     │◀────────────│ - Stores Edited │               │   Mandatory  │
│ - Records    │  Overridden │   Target & Buy  │               │   Reason     │
│   Planner ID │             │ - Requires      │               │ - Purchase   │
│ - Records    │             │   Reason        │               │   Cancelled  │
│   Comment    │             └─────────────────┘               └──────────────┘
└──────────────┘
```

### State Transition Rules:
1. **`PENDING`**: Initial state upon ingestion from shadow snapshot. Requires planner review.
2. **`APPROVED`**:
   - Planner accepts the recommendation.
   - Original AI `target_stock` and `suggested_purchase` are confirmed.
   - Records `planner_id` and timestamp.
   - If previously `EDITED`, approving confirms the edited quantities.
   - Idempotency guard: Attempting to approve an already `APPROVED` item raises an error.
3. **`REJECTED`**:
   - Planner declines replenishment.
   - **Requires an explicit rejection reason** (minimum 3 characters).
   - Original AI recommendations remain permanently preserved for reporting.
4. **`EDITED`**:
   - Planner overrides recommended target stock and/or purchase quantity (e.g. for MOQ or batch roll constraints).
   - Original AI `target_stock` and `suggested_purchase` remain **untouched**.
   - `edited_target_stock` and `edited_purchase_qty` store overridden numbers.
   - **Requires an explanatory note** (minimum 3 characters).
5. **`CANCELLED`**: Administrative cancellation if batch or product parameters change.

---

## 4. Safety Validation & Controls (Task 4)

Every decision processed by the API and service layer enforces strict safety checks:

| Safety Control | Rule Specification | Failure Behavior | Verification Status |
| :--- | :--- | :--- | :---: |
| **Non-Negative Target** | `target_stock >= 0.0` and `edited_target >= 0.0` | Throws `ValueError`, transaction aborted | **PASS** |
| **Non-Negative Purchase** | `suggested_purchase >= 0.0` and `edited_purchase >= 0.0` | Throws `ValueError`, transaction aborted | **PASS** |
| **Dead-Stock Protection** | Dead stock cannot have `target > 0` or `purchase > 0` | Throws `ValueError`, transaction aborted | **PASS** |
| **Mandatory Rejection Reason** | Rejection requires non-empty string (`len >= 3`) | Throws `ValueError`, transaction aborted | **PASS** |
| **Mandatory Override Reason** | Quantity edit requires non-empty string (`len >= 3`) | Throws `ValueError`, transaction aborted | **PASS** |
| **Risky Category Governance** | High-risk categories (`rising_product_risk`, `major_target_reduction`, etc.) require warning ack or explanatory comment | Throws `ValueError`, transaction aborted | **PASS** |
| **Snapshot Traceability** | Every approval record must reference a valid snapshot | Enforced via data model foreign key | **PASS** |
| **Duplicate Approval Guard** | Already approved item cannot be re-approved | Throws `ValueError`, transaction aborted | **PASS** |

---

## 5. API Endpoints (`/api/approvals`)

Integrated into FastAPI at [`backend/app/api/approvals.py`](file:///e:/Agent/backend/app/api/approvals.py) and mounted in [`backend/app/main.py`](file:///e:/Agent/backend/app/main.py):

| Method | Endpoint | Description | Request Payload / Params |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/approvals` | List recommendations with filters | `status`, `exception_category`, `pattern`, `search`, `limit`, `offset` |
| `GET` | `/api/approvals/summary` | Aggregated counts by status & queue | `snapshot_id` (optional) |
| `GET` | `/api/approvals/{id}` | Detail view with complete audit trail | Path parameter `approval_id` |
| `POST`| `/api/approvals/{id}/approve` | Transactional planner approval | `{"planner_id": str, "comment": str, "warning_acknowledged": bool}` |
| `POST`| `/api/approvals/{id}/reject` | Transactional planner rejection | `{"planner_id": str, "reason": str}` (min length 3) |
| `POST`| `/api/approvals/{id}/edit` | Transactional quantity override | `{"planner_id": str, "edited_target_stock": float, "edited_purchase_qty": float, "reason": str}` |
| `POST`| `/api/approvals/sync` | Ingest pending recommendations | `snapshot_id` (optional, defaults to latest) |

---

## 6. Planner User Interface Workflow (Task 5 & 6)

The planner governance screen was implemented at [`frontend/app/canary-shadow/page.tsx`](file:///e:/Agent/frontend/app/canary-shadow/page.tsx):

### UI Highlights:
1. **Prominent Safety Header**:
   - Banner: **`AI RECOMMENDATION — REQUIRES PLANNER APPROVAL`**.
   - Subtext: *"Approval records human planner governance decisions. Strict Safety Rule: Approval does NOT create Odoo purchase orders or RFQs."*
2. **KPI Summary Cards**:
   - Displays real-time counts for `Pending Review (997)`, `Approved (1)`, `Edited (1)`, `Rejected (1)`, and `Procurement Isolation (0 POs Created)`.
3. **Queue Navigation Tabs**:
   - Instant filtering by state: `Pending Review`, `Approved`, `Edited`, `Rejected`.
   - Instant filtering by exception queue: `Major Reductions (310)`, `Major Increases (1)`, `Rising Risk (8)`, `Intermittent (7)`, `Dormant / Dead (12)`, `Large FC Delta (579)`.
   - Real-time search across product name and product ID.
4. **Side-by-Side Table Layout**:
   - Left: Product ID, Product Name, Demand Pattern badge.
   - Center-Left: **Legacy Production** (Reorder Point, Current Stock).
   - Center-Right: **AI Recommendation** (AI Target, AI Suggested Buy, Delta).
   - Right: **Planner Decision** (Status badge, Approved/Edited Qty, Action Buttons `Approve`, `Edit`, `Reject`).
5. **Interactive Action Modals**:
   - **Approve Modal**: Summary of original quantities, high-risk exception acknowledgement checkbox, optional comment input.
   - **Reject Modal**: Mandatory operational reason textarea.
   - **Edit Modal**: Inputs for `Edited Target Stock` and `Edited Purchase Qty`, mandatory override rationale textarea.
   - **Detail Modal**: Complete audit trail showing chronological actions, timestamps, and planner IDs.

---

## 7. Audit Trail & Rationale Traceability (Task 7)

Every decision creates an immutable event in `planner_approval_audit_trail`. 

### Complete Audit Trail Reconstruction Example (Product 19055, `436-18`):

```json
[
  {
    "id": 1,
    "approval_id": "appr_canary_snap_002_19055",
    "action": "CREATED",
    "previous_status": null,
    "new_status": "PENDING",
    "original_values": {
      "forecast_1m": 0.0,
      "forecast_h3": 0.0,
      "target_stock": 0.0,
      "suggested_purchase": 0.0,
      "pattern": "intermittent"
    },
    "edited_values": null,
    "planner_id": "system_canary_shadow",
    "reason_or_comment": "Created pending recommendation from canary snapshot",
    "timestamp": "2026-10-07T10:11:12.123879Z"
  },
  {
    "id": 2,
    "approval_id": "appr_canary_snap_002_19055",
    "action": "EDITED",
    "previous_status": "PENDING",
    "new_status": "EDITED",
    "original_values": {
      "target_stock": 0.0,
      "suggested_purchase": 0.0,
      "pattern": "intermittent"
    },
    "edited_values": {
      "edited_target_stock": 25.0,
      "edited_purchase_qty": 25.0
    },
    "planner_id": "planner_lead_01",
    "reason_or_comment": "Rounded up purchase quantity to meet supplier standard roll length of 50m.",
    "timestamp": "2026-10-07T10:11:12.641774Z"
  }
]
```

### Traceability Guarantees:
- **Zero Information Loss**: The original AI figures (target = 0.0m, purchase = 0.0m) remain permanently stored and inspectable.
- **Accountability**: Overridden figures (target = 25.0m, purchase = 25.0m) are explicitly tied to `planner_lead_01` and the operational rationale.
- **Bi-temporal Visibility**: System can report both *"What did AI recommend?"* and *"What did the human planner decide?"* across the entire catalog.

---

## 8. Proof of No Procurement Side Effects (Task 8)

The workflow was rigorously audited to confirm zero procurement side effects:

```
┌────────────────────────────────────────────────────────────────────────┐
│               PROCUREMENT ISOLATION VERIFICATION MATRIX                │
├──────────────────────────────────────┬────────────────┬────────────────┤
│ Operation / Action                   │ Expected Rule  │ Observed Count │
├──────────────────────────────────────┼────────────────┼────────────────┤
│ APPROVE recommendation               │ Create Odoo PO │ STRICTLY 0     │
│ APPROVE recommendation               │ Create RFQ     │ STRICTLY 0     │
│ EDIT recommendation                  │ Create Odoo PO │ STRICTLY 0     │
│ EDIT recommendation                  │ Modify Reorder │ STRICTLY 0     │
│ REJECT recommendation                │ Odoo DB Writes │ STRICTLY 0     │
│ Total Odoo Tables Modified           │ Zero writes    │ 0 tables       │
│ Total Odoo Purchase Orders Created   │ Zero POs       │ 0 orders       │
│ Total Odoo RFQs Created              │ Zero RFQs      │ 0 RFQs         │
└──────────────────────────────────────┴────────────────┴────────────────┘
```

**Verification Statement**:
`APPROVE != CREATE ODOO PO`  
`EDIT != CREATE ODOO PO`  
`REJECT != MODIFY ODOO`  
The approval workflow is completely isolated in the separate POC PostgreSQL database and serves strictly as a governance ledger.

---

## 9. Test Suite Verification (Task 9)

A dedicated unit test suite was implemented in [`backend/tests/test_planner_approval.py`](file:///e:/Agent/backend/tests/test_planner_approval.py):
1. `test_approval_creation_and_fields`: Validates sync from snapshot, field types, and initial `CREATED` audit event.
2. `test_approve_preserves_original_recommendation`: Confirms approve preserves original AI values and records planner identity and comments.
3. `test_duplicate_approval_protection`: Confirms attempting to re-approve an already approved item raises `ValueError`.
4. `test_reject_requires_mandatory_reason`: Confirms rejection requires non-empty reason and preserves AI figures.
5. `test_edit_preserves_original_ai_and_stores_overrides`: Confirms editing stores overrides while keeping original AI recommendations bitwise intact.
6. `test_negative_value_protection`: Confirms negative target or purchase overrides are strictly rejected.
7. `test_dead_stock_zero_protection`: Confirms dead stock products cannot be edited with positive purchase quantities.
8. `test_risky_category_warning_requirement`: Confirms risky exception categories require warning acknowledgement or descriptive comments.
9. `test_zero_odoo_writes_and_no_po_creation`: Confirms absolute isolation from Odoo procurement tables.

### Complete Test Suite Execution
```
python -m unittest discover backend/tests

Ran 102 tests in 2.049s

OK
```
All **102 unit tests pass** across:
- `backend/tests/test_benchmark_v2_correctness.py` (22 tests)
- `backend/tests/test_benchmark_v2_leakage.py` (25 tests)
- `backend/tests/test_benchmark_v2_calibration.py` (26 tests)
- `backend/tests/test_benchmark_v2_shadow.py` (12 tests)
- `backend/tests/test_canary_shadow.py` (8 tests)
- `backend/tests/test_planner_approval.py` (9 tests)

---

## 10. Milestone Recommendation & Next Steps

### Can we proceed to a Controlled Procurement Workflow?
**YES, as the next milestone.**
The human planner approval workflow is now completely established, auditable, and validated. With human governance active, the platform is prepared to design **Step 12: Controlled Draft PO Generation (Human-Approved Only)**, where approved recommendations can be staged as draft review purchase orders under explicit planner control.

### Should automated procurement be enabled?
**STRICTLY NO.**
Automated procurement must remain permanently disabled. All procurement actions must originate from explicitly approved or edited planner decisions.

---

## 11. Integrity Verification Summary

1. **Production Forecasting Files Untouched**:
   - `forecasting-engine/src/*`: Confirmed completely untouched.
   - `backend/app/api/forecast.py`: Confirmed untouched.
2. **Odoo Database & Schemas Untouched**:
   - Zero Odoo tables modified.
   - Zero Odoo schema changes.
   - Zero Odoo purchase orders created.
3. **Changed / Added Files**:
   - `backend/app/forecasting/benchmark_v2/approvals.py` (new approval governance service)
   - `backend/app/api/approvals.py` (new planner approval API router)
   - `backend/app/main.py` (mounted approvals API router)
   - `frontend/app/canary-shadow/page.tsx` (extended planner comparison and approval UI)
   - `backend/tests/test_planner_approval.py` (new unit test suite)
   - `forecasting-engine/STEP11_HUMAN_PLANNER_APPROVAL.md` (this report)
4. **All Unit Tests Passing**:
   - 102 / 102 tests passing (`OK`).
