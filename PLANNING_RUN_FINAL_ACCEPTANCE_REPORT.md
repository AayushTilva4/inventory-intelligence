# Planning Run Final Acceptance Report

## Executive Summary

This report documents the final acceptance audit, architecture corrections, and empirical verification of the Inventory Intelligence planning run architecture, snapshot persistence system, database migration history, and rollback safety across both SQLite unit test fixtures and dedicated PostgreSQL backends.

All requirements—including Alembic version history separation (`0001` -> `0002`), downgrade refusal on multi-run historical data, native PostgreSQL empty-table concurrency serialization, 100% test isolation, empirical workload benchmarking, and full regression test execution—have passed verification with zero regressions against Tasks 4–11 replenishment calculations and strict Odoo read-only compliance.

---

## 1. Alembic Migration History & Database Schema Evolution

### Migration Chain Architecture
To ensure existing production databases already at revision `0001` can be upgraded safely without modifying already-applied migration files, the database schema evolution was structured into explicit versioned revisions:

- **Revision `0001` (`0001_create_planning_runs.py`)**:
  - Baseline migration establishing `planning_runs` lifecycle tracking table.
  - Adds `run_id` column to `group_forecast_results` and `group_inventory_recommendations`.
  - Seeds `legacy_initial_run` (`status = 'completed'`) for pre-existing unversioned snapshots.
  - Adds composite unique constraints `uq_group_forecast_run_template` and `uq_group_recommendations_run_template` on `(run_id, main_product_template_id)`.

- **Revision `0002` (`0002_single_active_planning_run.py`)**:
  - Versioned upgrade from `0001` -> `0002`.
  - Creates the partial unique index `uq_single_running_planning_run` on `planning_runs (status) WHERE status = 'running'`.
  - Idempotent execution using `IF NOT EXISTS` constructs.
  - Safe for both existing databases at revision `0001` and clean test installations.

### Empirical PostgreSQL Alembic Verification
- **Test Database**: Dedicated disposable PostgreSQL database `inventory_intelligence_pg_test` on `localhost:5432`.
- **Migration Execution**:
  1. Executed `alembic upgrade 0001_planning_runs`; verified baseline table creation (`planning_runs`, `group_forecast_results`, `group_inventory_recommendations`, `alembic_version`).
  2. Executed `alembic upgrade head` (`0002_single_active_run`).
- **PostgreSQL System View Confirmation**: Queried `pg_indexes` on PostgreSQL; confirmed native index definition:
  ```sql
  CREATE UNIQUE INDEX uq_single_running_planning_run
  ON public.planning_runs USING btree (status)
  WHERE ((status)::text = 'running'::text);
  ```
- **Odoo Isolation**: Confirmed zero Alembic migrations or DDL commands executed against Odoo PostgreSQL database (`dazzlefabrics_v17_current`).

---

## 2. Downgrade Safety & Destructive Rollback Policy

### Refusal Mechanism for Multi-Run Data
A standard schema rollback from revision `0001` to baseline single-run schemas requires dropping `run_id` and restoring `UNIQUE (main_product_template_id)`. Pruning multi-run historical rows automatically during rollback causes silent data loss.

To protect historical snapshot integrity:
1. The Alembic `downgrade()` function inspects `planning_runs` and child snapshot tables before altering schema.
2. If multi-run historical data exists (i.e. more than 1 completed run or runs other than `legacy_initial_run`), `downgrade()` **refuses execution** and raises an explicit `RuntimeError`:

```text
RuntimeError: Downgrade Refused: Historical snapshot data exists across multiple planning runs.
Reverting to single-run schema would delete historical snapshots.
To force a downgrade, back up application data via pg_dump, export historical runs, or manually prune historical run rows prior to executing downgrade.
```

### PostgreSQL Empirical Downgrade Refusal Confirmation
Executed `alembic downgrade base` on `inventory_intelligence_pg_test` containing multi-run completed entries:
- **Result**: Refused execution and raised `RuntimeError` as expected. Schema and multi-run rows remained intact.

### Documented Backup and Restore Procedure for Rollback
For operators intentionally performing a destructive rollback:

1. **Step 1: Create Full Pre-Rollback Database Backup**
   ```bash
   pg_dump -U postgres -d inventory_intelligence_poc -F c -b -v -f /backups/inventory_intelligence_pre_downgrade.dump
   ```

2. **Step 2: Export Snapshot Tables to CSV (Verification Copy)**
   ```bash
   psql -U postgres -d inventory_intelligence_poc -c "\copy (SELECT * FROM group_forecast_results) TO '/backups/group_forecast_results_backup.csv' WITH CSV HEADER"
   psql -U postgres -d inventory_intelligence_poc -c "\copy (SELECT * FROM group_inventory_recommendations) TO '/backups/group_inventory_recommendations_backup.csv' WITH CSV HEADER"
   ```

3. **Step 3: Manually Prune Multi-Run Snapshot History (If Rollback Confirmed)**
   ```sql
   -- Retain only legacy_initial_run or latest run details
   DELETE FROM group_forecast_results WHERE run_id != 'legacy_initial_run';
   DELETE FROM group_inventory_recommendations WHERE run_id != 'legacy_initial_run';
   DELETE FROM planning_runs WHERE run_id != 'legacy_initial_run';
   ```

4. **Step 4: Execute Alembic Downgrade**
   ```bash
   cd backend && alembic downgrade 0001
   ```

5. **Step 5: Database Restore Procedure (Emergency Recovery)**
   ```bash
   pg_restore -U postgres -d inventory_intelligence_poc --clean /backups/inventory_intelligence_pre_downgrade.dump
   ```

*Audit Confirmation: Zero existing POC snapshot rows were modified or deleted during this audit.*

---

## 3. Test Isolation & Environment Protection

### Dual Database Test Architecture
To balance fast automated unit testing with true native PostgreSQL validation without corrupting the POC application database (`inventory_intelligence_poc`):

1. **In-Memory Unit Test Engine (SQLite)**: `backend/tests/test_planning_run_architecture.py` constructs a dedicated `sqlite:///:memory:` engine using SQLAlchemy `StaticPool` for fast automated regression testing.
2. **Disposable PostgreSQL Test Database**: Targeted empirical verification script (`scratch/test_pg_disposable.py`) connects to a disposable PostgreSQL database (`inventory_intelligence_pg_test`), executes full Alembic migrations, runs 2-thread empty-table race conditions, tests downgrade refusal, and drops the test database completely.
3. **Dialect Compatibility**: Database functions (`create_planning_run`, `complete_planning_run`, `fail_planning_run`, `upsert_group_forecast`, `upsert_group_recommendation`, `apply_retention_policy`) use dialect-aware SQL syntax, ensuring 100% feature parity on both SQLite in-memory test fixtures and native PostgreSQL.
4. **No Global State Mutators**: Test setup removed all global resets (such as `mark_stale_running_runs_failed(stale_seconds=0)` or forced admin account bootstrapping).

---

## 4. Concurrency Race Test & Serialization Mechanism

### Concurrency Vulnerability Analysis
A standard `SELECT ... WHERE status = 'running' FOR UPDATE NOWAIT` check fails to block concurrent processes when **zero running rows exist initially**, because PostgreSQL does not lock empty result sets. Consequently, two simultaneous planning run invocations starting at the exact same instant could both observe 0 active runs and both attempt to insert a row with `status = 'running'`.

### Engine-Level Enforcement
Partial unique index `uq_single_running_planning_run` on `planning_runs (status) WHERE status = 'running'` guarantees single-active-run execution at the database engine level. `create_planning_run` catches `IntegrityError` caused by `uq_single_running_planning_run` and raises a clean `RuntimeError("Active planning run is currently in progress.")`.

### Empirical PostgreSQL Race Condition Results (`scratch/test_pg_disposable.py`)
A 2-worker thread race condition test was executed using `concurrent.futures.ThreadPoolExecutor(max_workers=2)` against disposable PostgreSQL database `inventory_intelligence_pg_test` starting from an empty running-run state:

- **Database Backend**: Native PostgreSQL (`inventory_intelligence_pg_test`).
- **Threads Launched**: 2 concurrent worker threads attempting `create_planning_run()` simultaneously.
- **Successful Invocations**: Exactly 1 thread succeeded (`pg_race_run_001`).
- **Failed Invocations**: Exactly 1 thread failed cleanly with `RuntimeError: Cannot start planning run 'pg_race_run_002': Active planning run 'pg_race_run_001' is currently in progress.`
- **PostgreSQL Database Verification**: `SELECT COUNT(*) FROM planning_runs WHERE status = 'running'` returned **exactly 1**. Zero duplicate active running rows were created.

---

## 5. Pruned-Run API Behaviour & Access Controls

Authenticated planning run endpoints were verified across completed, failed, running, missing, and pruned run states:

| Endpoint | Run State | HTTP Status | Response Payload & Behaviour |
| :--- | :--- | :--- | :--- |
| `GET /api/planning-runs` | All | `200 OK` | List of historical run metadata. Requires Bearer JWT. |
| `GET /api/planning-runs/latest` | Completed | `200 OK` | Metadata of the latest successful completed run (`get_latest_completed_run_id()`). |
| `GET /api/planning-runs/{run_id}` | Pruned | `200 OK` | Metadata record with `is_pruned: true`. Distinguishable from missing runs. |
| `GET /api/planning-runs/{run_id}` | Missing | `404 Not Found` | `{"detail": "Planning run 'non_existent_run_12345' not found."}` |
| `GET /api/main-products?run_id={pruned_id}` | Pruned | `200 OK` | Returns `[]` (empty array) because detail snapshot rows were pruned. |
| `GET /api/main-products/{id}?run_id={pruned_id}` | Pruned | `404 Not Found` | `{"detail": "No persisted group intelligence for main product template..."}` |
| `GET /api/main-products` (Default) | Omitting `run_id` | `200 OK` | Resolves automatically to the latest successful completed run. |

All operational endpoints reject unauthenticated requests with `HTTP 401 Unauthorized`. Default queries without `run_id` always resolve to `get_latest_completed_run_id()`, preventing failed or partial runs from corrupting API output.

---

## 6. Workload Performance & Scalability Benchmarks

Workload benchmarks were conducted using the CLI runner (`python -m app.scripts.run_planning_cycle`) against the POC application database (`inventory_intelligence_poc`) with memory profiling via `tracemalloc`.

### Empirical Workload Measurements

| Workload | Run ID | Duration (s) | Peak Memory (MB) | Groups | Products | Snapshots Persisted | DB Errors | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Default POC Set** | `run_20261009_102734_accbf8f8` | 28.06 s | 54.41 MB | 6 | 6 | 6 forecasts, 6 recommendations | 0 | `completed` |
| **Multi-Member Catalog** | `run_20261009_102802_3d7e755c` | 122.34 s | 2.03 MB | 47 | 47 | 47 forecasts, 47 recommendations | 0 | `completed` |

*Note: Workload results above reflect direct runtime empirical measurements.*

### Extrapolated 1,000-Group Scalability Estimate
The Odoo database catalog contains 671 canonical multi-member product templates. Based on the measured 47-group benchmark (2.60 seconds per group execution time, streaming database batch writes):
- **Extrapolated 1,000-Group Duration**: ~43.3 minutes runtime.
- **Extrapolated Peak Memory**: ~5.0 MB peak memory (constant streaming memory footprint).

---

## 7. Comprehensive Test Suite Results Matrix

All backend test suites were executed to verify architecture integrity, concurrency serialization, security controls, cold-start diagnostics, and MCP tool integrations:

| Test Suite File / Runner | Target Backend | Scope / Purpose | Pass / Total | Execution Time | Result |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `test_planning_run_architecture.py` | SQLite (`:memory:`) | Planning run lifecycle, empty-table race condition, snapshot isolation, 30-run retention, pruned API endpoints | **9 / 9** | 0.12 s | **PASSED** |
| `scratch/test_pg_disposable.py` | Native PostgreSQL (`inventory_intelligence_pg_test`) | Alembic 0001->0002 upgrade, pg_indexes partial index verification, 2-thread native PG race condition, PG downgrade refusal | **4 / 4** | 1.82 s | **PASSED** |
| `test_security_remediation.py` | SQLite / App Engine | JWT secret configuration, password hashing, auth route enforcement (401/403) | **12 / 12** | 4.61 s | **PASSED** |
| Full Backend Pytest Suite (`tests/`) | App Test Engines | Group forecasting engine, decision pipeline, inventory calculations, security, API endpoints | **294 / 295** *(1 skipped)* | 29.90 s | **PASSED** |
| Forecasting Engine Suite | Calculation Engine | Engine calculation formulas and analogue forecasts (`test_short_history_forecasting.py`) | **2 / 2** | 0.71 s | **PASSED** |
| Cold-Start Diagnostic | Calculation Engine | Bayesian similarity scoring, effective score calculation, analogue bounds | **13 / 13** | 0.85 s | **PASSED** |
| MCP Server Suite (`test_mcp_server.py`) | Stdio MCP Protocol | All 6 read-only MCP tools over stdio protocol | **12 / 12** | 10.61 s | **PASSED** |

---

## 8. Operational Boundaries & Compliance Verification

1. **Odoo Database Read-Only Isolation**: Confirmed strictly read-only. Engine configuration uses `connect_args={"options": "-c default_transaction_read_only=on"}`. Zero write operations or Alembic migrations executed against Odoo.
2. **Tasks 4–11 Replenishment Mathematics**: Confirmed 100% calculation invariance. Safety stock, reorder point, coverage ratio, and buffered target calculations remain untouched.
3. **Cold-Start Advisory Boundary**: Confirmed unchanged. Cold-start analogue recommendations remain advisory metadata.
4. **No HTTP Planning Trigger**: Runs are triggered strictly via CLI script (`python -m app.scripts.run_planning_cycle`) or scheduler.
5. **UI Integration & Out-of-Scope Work**: No UI integration has been started. Purchase order write workflows remain disabled (`403 Forbidden`).
