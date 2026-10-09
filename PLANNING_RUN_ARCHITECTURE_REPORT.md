# Planning Run Architecture & Snapshot Persistence Report

## Executive Summary

This report documents the architectural design, database schema migration, lifecycle management, snapshot persistence, CLI execution interface, API endpoints, and retention policy implemented for Inventory Intelligence planning runs.

The planning run subsystem establishes a reproducible lifecycle where every execution receives a unique `run_id`, persists its own forecast and inventory recommendation outputs without overwriting past history, and provides deterministic retrieval by `run_id`.

---

## 1. Planning-Run Lifecycle & State Machine

Each planning run tracks its state machine transition explicitly:

```
[Start] ──> (status='running') ──┬──> [Success] ──> (status='completed')
                                 │
                                 └──> [Failure] ──> (status='failed')
```

### Metadata Fields Recorded Per Run

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `run_id` | `VARCHAR(64)` PRIMARY KEY | Unique identifier formatted as `run_YYYYMMDD_HHMMSS_<hash>`. |
| `started_at` | `TIMESTAMP WITH TIME ZONE` | Timestamp when the planning run was initialized. |
| `completed_at` | `TIMESTAMP WITH TIME ZONE` | Timestamp when the planning run completed or failed. |
| `status` | `VARCHAR(20)` | `running`, `completed`, or `failed`. |
| `error_message` | `TEXT` | Safe error message summary (truncated to 1,000 characters if failed). |
| `num_groups` | `INT` | Number of product groups processed in the run. |
| `num_products` | `INT` | Number of individual product recommendations generated. |
| `config_metadata` | `JSONB` | Runtime configuration (Python version, flags, parameters). |
| `execution_summary` | `JSONB` | Summary statistics (duration in seconds, group counts). |
| `is_pruned` | `BOOLEAN` | `TRUE` if detail snapshot rows were pruned by retention policy. |

### Concurrency Protection
Concurrent execution of multiple planning runs is prevented at the database level. When `create_planning_run` is called, it checks for any existing run with `status = 'running'`. If a run is in progress, the new invocation raises a `RuntimeError` and terminates safely without corrupting ongoing calculations.

---

## 2. Database Schema & Snapshot Persistence

The application database schema was migrated safely using Alembic to support run snapshot persistence.

### Relational Schema

1. **`planning_runs`**: Stores high-level lifecycle metadata.
2. **`group_forecast_results`**: Composite unique key `(run_id, main_product_template_id)`. Stores snapshot forecast outputs per run.
3. **`group_inventory_recommendations`**: Composite unique key `(run_id, main_product_template_id)`. Stores snapshot recommendation outputs per run.

### Data Migration & Historical Backward Compatibility

Pre-existing forecast and recommendation rows were preserved by assigning a synthetic baseline run:
- `run_id`: `'legacy_initial_run'`
- `status`: `'completed'`
- `started_at` & `completed_at`: Migration execution timestamp

This guarantees that pre-existing rows remain queryable without schema breaking changes.

---

## 3. Database Migrations (Alembic)

Alembic has been initialized for the POC application database (`inventory_intelligence_poc`).

- **Version File**: `backend/alembic/versions/0001_create_planning_runs.py`
- **Environment**: `backend/alembic/env.py` configured with `get_poc_engine()` from `app.db.connection`.
- **Command**: `python -m alembic upgrade head`

### Backup & Rollback Considerations

- Schema upgrade operates exclusively against the application database (`inventory_intelligence_poc`).
- Odoo database connection is configured with `-c default_transaction_read_only=on` and is **never** target of schema migrations.
- Downgrade function `alembic downgrade -1` drops composite unique constraints, restores single-column UNIQUE constraint on `main_product_template_id`, and drops `run_id` columns cleanly.

---

## 4. CLI Execution Interface & Cron Scheduler Integration

Planning cycles are executed via the CLI module:

```bash
python -m app.scripts.run_planning_cycle [--main-product-template-ids 405,1544] [--all-valid-groups] [--retention-limit 30]
```

Or via root script:

```bash
python backend/scripts/run_planning_cycle.py
```

### CLI Workflow

1. Initialize planning run record in database (`status='running'`).
2. Query canonical product groups from Odoo (read-only).
3. Compute group forecasts (`app.forecasting.group_forecast_service`) and inventory recommendations (`app.inventory.group_recommendation_service`).
4. Persist results under the active `run_id`.
5. Mark planning run `completed` with duration and counts.
6. Trigger transactional retention policy.
7. On exception: catch error, update run `status='failed'`, store safe error message, and exit with status code 1.

---

## 5. Retention Policy

By default, the application retains the **latest 30 completed planning runs** (`DEFAULT_RETENTION_LIMIT = 30`).

### Retention Invariants

1. **Active Runs Protection**: Runs with `status = 'running'` are **never** pruned.
2. **Latest Completed Protection**: The single most recent completed run is **never** deleted, even if retention limit is set below 1.
3. **Metadata Preservation**: When a run exceeds the retention threshold, its detailed snapshot rows in `group_forecast_results` and `group_inventory_recommendations` are transactionally deleted, while its `planning_runs` metadata record remains with `is_pruned = TRUE`.
4. **Transactional Safety**: Pruning operates inside a database transaction block (`connection.begin()`).

---

## 6. Read-Only API Endpoints

New authenticated endpoints allow inspecting planning run metadata:

| Method | Endpoint | Authorization | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/planning-runs` | Bearer JWT | List historical planning runs (supports `?status=completed&limit=50`). |
| `GET` | `/api/planning-runs/latest` | Bearer JWT | Retrieve metadata for the latest completed run. |
| `GET` | `/api/planning-runs/{run_id}` | Bearer JWT | Retrieve metadata for a specific run ID. |

### Preserved API Compatibility

Existing operational endpoints now support an optional `?run_id=<id>` query parameter:
- `GET /api/main-products?run_id=run_20261009_...`
- `GET /api/main-products/{main_product_template_id}?run_id=run_20261009_...`

If `run_id` is omitted, the API automatically defaults to `get_latest_completed_run_id()`, maintaining backward compatibility with single-run frontend expectations.

---

## 7. Verification Evidence & Test Coverage

### Test Results Summary

| Suite Name | Scope | Result | Details |
| :--- | :--- | :--- | :--- |
| `test_planning_run_architecture.py` | Lifecycle, concurrency, snapshot persistence, retention, API auth | **PASSED** | 7/7 tests passed in 1.1s |
| `test_security_remediation.py` | JWT authentication, 401/403 controls, CORS, password hashing | **PASSED** | 12/12 tests passed |
| Backend Pytest Suite | Full backend calculation and API suite | **PASSED** | 292 passed, 1 skipped |
| Forecasting Engine Suite | Engine calculation tests | **PASSED** | 2/2 passed |
| MCP Server Tools Suite | MCP 6 read-only tools suite | **PASSED** | 12/12 passed |

---

## 8. Operational Boundaries & Compliance

1. **Odoo Database Read-Only Isolation**: Odoo engine configured with strict driver option `-c default_transaction_read_only=on`.
2. **Tasks 4–11 Calculation Invariance**: Replenishment calculations, safety stock formulas, model ranking, and stockout treatments remain untouched.
3. **No HTTP Planning Trigger**: Planning runs are triggered strictly via CLI / scheduled job runner.
4. **Out-of-Scope Workflows Disabled**: Purchase order endpoints and approval actions return `403 Forbidden`.
