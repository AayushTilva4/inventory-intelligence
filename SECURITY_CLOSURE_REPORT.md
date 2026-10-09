# Inventory Intelligence — Security Closure Correction & Verification Report

> **Status:** `CLOSURE AUDIT & CORRECTION COMPLETE — VERIFIED`  
> **Date:** October 9, 2026  
> **Target Scope:** OpenAPI Route Audit, OWASP Scrypt Calibration ($N=65536, r=8, p=2$), Odoo PostgreSQL Privilege Clarification, Full Regression Verification  

---

## 1. Executive Summary

This report records the focused security corrections and final closure verification for the Inventory Intelligence backend prior to architecture planning.

All FastAPI application routes have been reconciled against the live OpenAPI specification; out-of-scope procurement and approval endpoints are explicitly disabled with HTTP `403 Forbidden`. Scrypt password hashing has been calibrated and adopted at OWASP's exact listed configuration ($N=65536, r=8, p=2$), benchmarked under single-thread (~360 ms) and 4-worker concurrent login load (~450 ms total), with transparent versioned parsing and safe rehash-on-login migration. Session-level driver read-only transaction protection (`-c default_transaction_read_only=on`) is active on all Odoo connections, while database-level role privilege isolation is formally documented as an outstanding DBA action.

---

## 2. Route Exposure & Discrepancy Resolution

### 2.1 Live OpenAPI Route Matrix

The complete set of routes exposed by the active FastAPI application is documented below:

| Route Path | HTTP Method | Router Tag | Operational Status | Authorization Level |
| :--- | :---: | :--- | :---: | :---: |
| `/health` | `GET` | Core | **Active** (200 OK) | **Public** (No Auth) |
| `/api/auth/login` | `POST` | Auth | **Active** (Issues JWT) | **Public** (No Auth) |
| `/api/auth/signup` | `POST` | Auth | **Disabled** (403 Forbidden) | **Blocked** |
| `/api/auth/me` | `GET` | Auth | **Active** (User profile) | `Depends(get_current_user)` |
| `/api/auth/logout` | `POST` | Auth | **Active** (Session invalidation) | `Depends(get_current_user)` |
| `/api/main-products` | `GET` | Main Product Groups | **Active** (Group catalog list) | `Depends(get_current_user)` |
| `/api/main-products/{id}` | `GET` | Main Product Groups | **Active** (Group detail view) | `Depends(get_current_user)` |
| `/api/main-products/{id}/forecast` | `GET` | Main Product Groups | **Active** (Group forecast) | `Depends(get_current_user)` |
| `/api/main-products/{id}/recommendation` | `GET` | Main Product Groups | **Active** (Group recommendation) | `Depends(get_current_user)` |
| `/api/main-products/{id}/create-po` | `POST` | Main Product Groups | **Disabled** (403 Forbidden) | **Blocked (Out of POC Scope)** |
| `/api/inventory/recommendations` | `GET` | Inventory | **Active** (Product recommendations) | `Depends(get_current_user)` |
| `/api/inventory/summary` | `GET` | Inventory | **Active** (Inventory summary counts) | `Depends(get_current_user)` |
| `/api/inventory/draft-pos` | `GET` | Inventory | **Disabled** (403 Forbidden) | **Blocked (Out of POC Scope)** |
| `/api/inventory/recommendations/{id}/approve` | `POST` | Inventory | **Disabled** (403 Forbidden) | **Blocked (Out of POC Scope)** |
| `/api/inventory/recommendations/{id}/reject` | `POST` | Inventory | **Disabled** (403 Forbidden) | **Blocked (Out of POC Scope)** |
| `/api/inventory/recommendations/{id}/create-draft-po` | `POST` | Inventory | **Disabled** (403 Forbidden) | **Blocked (Out of POC Scope)** |
| `/api/forecast/product/{id}` | `GET` | Forecast | **Active** (Product forecast) | `Depends(get_current_user)` |
| `/api/forecast/product/{id}/history` | `GET` | Forecast | **Active** (Historical monthly sales) | `Depends(get_current_user)` |
| `/api/products/{id}/group` | `GET` | Products | **Active** (Live Odoo product group) | `Depends(get_current_user)` |
| `/api/products/{id}/group/history` | `GET` | Products | **Active** (Group demand history) | `Depends(get_current_user)` |
| `/api/products/{id}/group/forecast` | `GET` | Products | **Active** (Group forecast calculation) | `Depends(get_current_user)` |
| `/api/products/{id}/group/recommendation` | `GET` | Products | **Active** (Group replenishment breakdown)| `Depends(get_current_user)` |
| `/api/shadow/snapshots` | `GET` | Canary Shadow | **Active** (Canary shadow snapshots) | `Depends(get_current_user)` |
| `/api/shadow/exceptions/summary` | `GET` | Canary Shadow | **Active** (Planner exception breakdown)| `Depends(get_current_user)` |
| `/api/shadow/comparisons` | `GET` | Canary Shadow | **Active** (Canary shadow comparisons) | `Depends(get_current_user)` |
| `/api/shadow/audit-log/{id}` | `GET` | Canary Shadow | **Active** (Product audit trail) | `Depends(get_current_user)` |
| `/api/ai/explain/{id}` | `GET` | AI | **Active** (Gemini AI explanation) | `Depends(get_current_user)` |

### 2.2 Discrepancy Resolution & Authorization Hardening
1. While `procurement_router` and `approvals_router` were unregistered from `main.py`, secondary PO and approval routes in `inventory.py` and `main_products.py` have been explicitly disabled with HTTP `403 Forbidden`.
2. All transactional purchase order creation and approval mutations are completely blocked.
3. Ordinary read-only forecasting, inventory summary, group hierarchy, canary shadow, and AI insight endpoints remain fully accessible to authenticated users (`Depends(get_current_user)`).
4. Privileged administrative operations (such as user management) require explicit `require_admin` role validation.

---

## 3. Scrypt Parameter Calibration & Login Benchmark

### 3.1 OWASP Configuration Benchmarking

We benchmarked scrypt password hashing configurations under realistic login conditions on the target application environment:

| Scrypt Configuration | Memory Footprint / Hash | Single-Thread Mean Latency | Min / Max Latency | 4 Concurrent Logins Total Time | OWASP Listed Alignment | Adopted Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| $N = 16384, r = 8, p = 1$ | $16\text{ MB}$ | $85.77\text{ ms}$ | $64.00 / 111.39\text{ ms}$ | $112.50\text{ ms}$ | Legacy Minimum | Rehash Target |
| $N = 65536, r = 8, p = 1$ | $64\text{ MB}$ | $201.18\text{ ms}$ | $183.92 / 226.93\text{ ms}$ | $266.01\text{ ms}$ | Moderate | Rehash Target |
| **$N = 65536, r = 8, p = 2$** | **$128\text{ MB}$** | **$360.04\text{ ms}$** | **$345.62 / 375.77\text{ ms}$** | **$450.72\text{ ms}$** | **OWASP Primary Listed** | **ADOPTED** |

### 3.2 Decision & Rationale
- **Decision:** Adopted OWASP's exact listed configuration: **$N = 65536, r = 8, p = 2, \text{maxmem} = 256\text{ MB}$**.
- **Performance Trade-off Analysis:** Single-login latency of ~360 ms and 4-worker concurrent burst processing of ~450 ms fall comfortably within accepted enterprise login SLA targets (< 500 ms) while maximizing resistance against GPU/ASIC offline hash cracking.

### 3.3 Versioned Hash Format & Migration Rules
- **Serialized Header:** `scrypt$65536$8$2$<16_byte_salt_hex>$<hash_hex>`
- **Parsing & Migration Logic:**
  1. `verify_password()` dynamically extracts cost parameters ($N, r, p$) and salt from the header.
  2. If the verified password matches a hash with $N < 65536$, $r < 8$, $p < 2$, or legacy 128-char hex format, `needs_rehash` is set to `True`.
  3. The `/api/auth/login` endpoint automatically upgrades the user's database credential to $N=65536, r=8, p=2$ on successful authentication without logging credentials.

---

## 4. Odoo Read-Only Safeguard & Outstanding DBA Action

### 4.1 Session-Level vs Role-Level Security Clarification

Empirical database inspection confirms the actual Odoo PostgreSQL session state:

```text
=== ODOO POSTGRESQL PRIVILEGE INSPECTION ===
Session Info: User 'odoo' connected to database 'dazzlefabrics_v17_current'
Role Attributes: rolname='odoo', rolsuper=False, rolinherit=True, rolcreaterole=False, rolcreatedb=True, rolcanlogin=True
Table Privilege Check for user 'odoo':
  - product_template : SELECT=True, INSERT=True, UPDATE=True, DELETE=True
  - stock_move       : SELECT=True, INSERT=True, UPDATE=True, DELETE=True
  - purchase_order   : SELECT=True, INSERT=True, UPDATE=True, DELETE=True
  - stock_quant      : SELECT=True, INSERT=True, UPDATE=True, DELETE=True
```

### 4.2 Status of Active Safeguards
1. **Implemented & Verified Safeguard:** Driver-level session read-only transaction protection (`connect_args={"options": "-c default_transaction_read_only=on"}`) is active on all Odoo engine connections. Any write query (`INSERT`, `UPDATE`, `DELETE`, `CREATE TABLE`) is blocked at the transaction boundary with `psycopg2.errors.ReadOnlySqlTransaction`.
2. **Outstanding DBA Action:** Because the application connects using the table-owner account (`odoo`), full multi-tier defense-in-depth requires a dedicated read-only PostgreSQL role created by a Database Administrator.

### 4.3 Documented Outstanding DBA Requirements
The application layer does not alter Odoo database roles or schema privileges automatically. The following SQL script is documented as an **outstanding DBA requirement** for production deployment:

```sql
-- OUTSTANDING DBA ACTION FOR PRODUCTION HARDENING:
-- 1. Create dedicated read-only role for Inventory Intelligence
CREATE ROLE inventory_intelligence_ro WITH LOGIN PASSWORD 'SET_STRONG_PRODUCTION_PASSWORD';

-- 2. Grant connection and schema access
GRANT CONNECT ON DATABASE dazzlefabrics_v17_current TO inventory_intelligence_ro;
GRANT USAGE ON SCHEMA public TO inventory_intelligence_ro;

-- 3. Grant SELECT privileges on all current and future tables
GRANT SELECT ON ALL TABLES IN SCHEMA public TO inventory_intelligence_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO inventory_intelligence_ro;

-- 4. Explicitly revoke mutation permissions
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM inventory_intelligence_ro;
```

---

## 5. Regression Verification Results

### 5.1 Security Unit Test Suite (`backend/tests/test_security_remediation.py`)
```text
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_01_public_health_check PASSED [  8%]
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_02_unauthenticated_access_rejected_on_all_protected_routers PASSED [ 16%]
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_03_authenticated_access_succeeds_on_protected_endpoints PASSED [ 25%]
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_04_public_signup_is_disabled PASSED [ 33%]
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_05_procurement_and_approval_endpoints_are_disabled PASSED [ 41%]
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_06_jwt_secret_startup_validation PASSED [ 50%]
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_07_invalid_and_expired_jwt_tokens PASSED [ 58%]
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_08_password_hashing_with_unique_salts_and_owasp_cost PASSED [ 66%]
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_09_legacy_and_lower_cost_hash_verification_and_migration PASSED [ 75%]
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_10_admin_bootstrap_idempotency PASSED [ 83%]
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_11_odoo_read_only_transaction_enforcement PASSED [ 91%]
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_12_cors_configuration PASSED [100%]
======================= 12 passed in 11.06s ========================
```

### 5.2 Full Backend Test Suite (`backend/tests/`)
```text
================= 285 passed, 1 skipped, 3 warnings in 20.21s =================
```

### 5.3 Forecasting Engine Test Suite (`forecasting-engine/tests/`)
```text
============================== 2 passed in 0.95s ==============================
```

### 5.4 Model Context Protocol (MCP) Runtime Smoke Test (`scratch/mcp_client_smoke_test.py`)
```text
==================================================================
INVENTORY INTELLIGENCE MCP SERVER RUNTIME SMOKE TEST
==================================================================
Discovered & Invoked Tools:
  - check_database_connection       : SUCCESS (Read-only verified)
  - get_product_info                : SUCCESS
  - get_group_demand_history_tool   : SUCCESS
  - get_group_forecast_tool         : SUCCESS
  - get_group_recommendation_tool   : SUCCESS
  - get_cold_start_diagnostic_tool  : SUCCESS
==================================================================
SMOKE TEST SUMMARY: 14/14 calls succeeded!
==================================================================
```

---

## 6. Preservation of Operational Invariants

The following core modules and contracts are audited and confirmed to remain **100% untouched and invariant**:

1. **Tasks 4–11 Mathematical Core**: Canonical inventory position ($\text{IP}$), 4-month operational replenishment horizon ($H=4$), forecast-error safety stock ($SS$), real out-of-sample error confidence scoring, rolling multi-origin model selection, stockout month censoring, $N \ge 6$ short-history fallback, and recommendation calculation breakdown.
2. **Cold-Start Analogue Diagnostic**: Advisory-only Bayesian credibility blend ($z = \frac{N}{N+3}$) with $0$ purchase quantity for $N < 6$.
3. **MCP Tooling Sidecar**: 6-tool standard read-only stdio interface.
4. **Odoo Database Safety**: 0 writes, 0 mutations, 100% read-only confirmed.

---

> **Final Closure Notice:** This report completes the security correction audit. No planning-run architecture, procurement workflows, frontend navigation modifications, or git commits/pushes were performed.
