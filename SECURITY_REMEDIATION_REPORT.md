# Inventory Intelligence — Phase 1 Security Remediation Report

> **Status:** `REMEDIATION COMPLETE & VERIFIED`  
> **Date:** October 9, 2026  
> **Target Scope:** FastAPI Backend, Authentication & Authorization Layer, JWT Security, Database Connection Hardening, Error Sanitization, Odoo Read-Only Enforcement  

---

## 1. Executive Summary

This report documents the implementation and verification of the high-severity security remediations identified in `ARCHITECTURE_SECURITY_AUDIT.md`. 

All operational FastAPI endpoints now require cryptographic Bearer JWT authentication, `JWT_SECRET` is validated on server startup with zero fallback to insecure keys, password hashing employs unique per-user random salts with transparent legacy migration on login, public self-signup is disabled, the administrator bootstrap script is operational and idempotent, and Odoo PostgreSQL connections are strictly locked into read-only transactions at the database protocol driver level.

All mathematical forecasting models, inventory calculations (Tasks 4–11), cold-start diagnostics, and read-only MCP tools remain completely preserved and 100% functional.

### Remediation Verification Summary

| Component / Fix | Prior State | Remediated State | Test Verification | Status |
| :--- | :--- | :--- | :--- | :---: |
| **API Authentication** | Only `/api/auth/me` checked auth; 8 operational routers open to unauthenticated callers | Global `Depends(get_current_user)` applied to all operational routers; unauthenticated calls return `401` | `test_02_unauthenticated_access_rejected_on_all_protected_routers` | **VERIFIED** |
| **JWT Secret Safety** | Silently defaulted to `"super-secret-poc-key"` if unset | Mandatory $\ge 32$-character secret; server raises `RuntimeError` on startup if missing or weak | `test_06_jwt_secret_startup_validation` | **VERIFIED** |
| **Password Hashing** | Single static salt `b'some-fixed-salt-for-poc'` for all users | Scrypt with 16-byte cryptographically random salt per user (`scrypt$16384$8$1$...`) | `test_08_password_hashing_with_unique_salts` | **VERIFIED** |
| **Legacy Hash Migration** | Legacy hashes had no upgrade path | Dual-verification algorithm validates legacy hashes on login and automatically re-hashes with unique salt | `test_09_legacy_password_hash_verification_and_migration` | **VERIFIED** |
| **Public Registration** | Unrestricted open signup at `/api/auth/signup` | Public registration disabled; returns `403 Forbidden` | `test_04_public_signup_is_disabled` | **VERIFIED** |
| **Admin Bootstrap** | None (ad-hoc SQL script with static salt) | Idempotent CLI script `backend/scripts/bootstrap_admin.py` with environment variable support | `test_10_admin_bootstrap_idempotency` | **VERIFIED** |
| **Procurement Scope** | Out-of-scope PO endpoints exposed unauthenticated | `procurement_router` and `approvals_router` unregistered from app; PO creation endpoints return `403` | `test_05_purchase_order_creation_endpoints_are_disabled` | **VERIFIED** |
| **Odoo Read-Only Driver** | Enforced by application convention only | PostgreSQL connection option `-c default_transaction_read_only=on` enforced at driver level | `test_11_odoo_read_only_transaction_enforcement` | **VERIFIED** |
| **Connection Pooling** | Engines created and disposed per function call | Singleton connection pools (`pool_size=10, max_overflow=20, pool_pre_ping=True`) | Backend engine suite | **VERIFIED** |
| **Error Sanitization** | Raw database / SQL exceptions returned in HTTP 500s | Exceptions logged server-side; generic `"Internal server error"` returned to client | Global exception handler | **VERIFIED** |
| **CORS Configuration** | Hardcoded origins | Explicit environment variable `CORS_ALLOWED_ORIGINS` without credentials wildcard | `test_12_cors_configuration` | **VERIFIED** |

---

## 2. Router-by-Router Endpoint Access Audit

| Router Prefix | Tag / Purpose | Endpoints | Auth Requirement | Status |
| :--- | :--- | :--- | :---: | :---: |
| `/health` | Core | `GET /health` | **Public** | Active (200 OK) |
| `/api/auth` | Auth | `POST /login` | **Public** | Active (Authenticates & issues JWT) |
| `/api/auth` | Auth | `POST /signup` | **Disabled** | Returns `403 Forbidden` |
| `/api/auth` | Auth | `GET /me`, `POST /logout` | **Bearer JWT** | Requires valid user token |
| `/api/main-products` | Main Products | `GET /`, `GET /{id}`, `GET /{id}/forecast`, `GET /{id}/recommendation` | **Bearer JWT** | Protected (401 if unauthenticated) |
| `/api/main-products` | Main Products | `POST /{id}/create-po` | **Disabled** | Returns `403 Forbidden` (POC scope) |
| `/api/inventory` | Inventory | `GET /recommendations`, `GET /summary`, `GET /draft-pos`, `POST /approve`, `POST /reject` | **Bearer JWT** | Protected (401 if unauthenticated) |
| `/api/inventory` | Inventory | `POST /recommendations/{id}/create-draft-po` | **Disabled** | Returns `403 Forbidden` (POC scope) |
| `/api/forecast` | Forecast | `GET /product/{id}`, `GET /product/{id}/history` | **Bearer JWT** | Protected (401 if unauthenticated) |
| `/api/products` | Products | `GET /{id}/group`, `GET /{id}/group/history`, `GET /{id}/group/forecast`, `GET /{id}/group/recommendation` | **Bearer JWT** | Protected (401 if unauthenticated) |
| `/api/shadow` | Canary Shadow | `GET /snapshots`, `GET /exceptions/summary`, `GET /comparisons`, `GET /audit-log/{id}` | **Bearer JWT** | Protected (401 if unauthenticated) |
| `/api/ai` | AI Insights | `GET /explain/{id}` | **Bearer JWT** | Protected (401 if unauthenticated) |
| `/api/approvals` | Approvals | All approval routes | **Unregistered** | Excluded from active application |
| `/api/procurement` | Procurement | All procurement routes | **Unregistered** | Excluded from active application |

---

## 3. Detailed Implementation Changes

### 3.1 Authentication & Password Security (`backend/app/api/auth.py`)
1. **JWT Secret Enforcement**:
   - `get_jwt_secret()` validates `JWT_SECRET` from the environment.
   - Raises `RuntimeError` if missing or fewer than 32 characters.
   - Validated on application startup via FastAPI `lifespan`.
2. **Cryptographic Password Hashing**:
   - `hash_password(password)` uses `hashlib.scrypt` with `os.urandom(16)` per-user salt.
   - Serialized format: `scrypt$16384$8$1$<salt_hex>$<hash_hex>`.
3. **Dual-Verification & Transparent Migration**:
   - `verify_password()` detects whether the stored hash is modern (`scrypt$...`) or legacy 128-char hex string.
   - Legacy hashes are verified using `b'some-fixed-salt-for-poc'`.
   - On successful login, the user's password hash in the PostgreSQL database is automatically updated to the modern unique-salt format without user disruption.
4. **Public Signup Disabled**:
   - `/api/auth/signup` returns HTTP 403 with `detail="Public user registration is disabled. Please contact the system administrator for account provisioning."`.
5. **Dependency Injection**:
   - `get_current_user`: extracts and validates Bearer token, returning user claims (`id`, `name`, `email`, `role`).
   - `require_admin`: enforces administrative privileges.

### 3.2 Administrator Bootstrap (`backend/scripts/bootstrap_admin.py`)
- Standalone CLI command supporting arguments and environment variables (`ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_NAME`).
- Ensures `users` table exists with `role VARCHAR(50)` column.
- Idempotent: if the administrator account already exists, reports presence and exits cleanly without overwriting credentials unless `--force` is specified.
- Never prints or logs plain passwords.

### 3.3 Database Hardening (`backend/app/db/connection.py`)
1. **Odoo Driver-Level Read-Only Enforcement**:
   - Instantiates engine with `connect_args={"options": "-c default_transaction_read_only=on"}`.
   - Any write attempt (`INSERT`, `UPDATE`, `DELETE`, `CREATE TABLE`) is aborted by the PostgreSQL backend with `psycopg2.errors.ReadOnlySqlTransaction`.
2. **Connection Pooling & Engine Singletons**:
   - `get_poc_engine()` and `get_odoo_engine()` return cached engine singletons.
   - Configured with `pool_size=10`, `max_overflow=20`, `pool_recycle=3600`, and `pool_pre_ping=True` (detecting stale connections before query execution).

### 3.4 API Hardening & CORS (`backend/app/main.py`)
1. **Global Exception Handler**:
   - Catches unhandled server exceptions, logs tracebacks server-side, and returns sanitized `{ "detail": "Internal server error. Please contact the administrator." }` to prevent database schema or credential leakage.
2. **CORS Configuration**:
   - Allowed origins are read from `CORS_ALLOWED_ORIGINS` environment variable.
   - Wildcards (`*`) with credentials enabled are strictly avoided.

---

## 4. Test Suite Execution & Verification Results

### 4.1 Security Remediation Suite (`backend/tests/test_security_remediation.py`)
12 test cases covering every security dimension:
```text
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_01_public_health_check PASSED
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_02_unauthenticated_access_rejected_on_all_protected_routers PASSED
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_03_authenticated_access_succeeds_on_protected_endpoints PASSED
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_04_public_signup_is_disabled PASSED
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_05_purchase_order_creation_endpoints_are_disabled PASSED
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_06_jwt_secret_startup_validation PASSED
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_07_invalid_and_expired_jwt_tokens PASSED
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_08_password_hashing_with_unique_salts PASSED
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_09_legacy_password_hash_verification_and_migration PASSED
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_10_admin_bootstrap_idempotency PASSED
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_11_odoo_read_only_transaction_enforcement PASSED
backend/tests/test_security_remediation.py::TestSecurityRemediation::test_12_cors_configuration PASSED
======================== 12 passed in 6.06s ========================
```

### 4.2 Full Backend Regression Suite (`backend/tests/`)
```text
================= 285 passed, 1 skipped, 3 warnings in 17.64s =================
```

### 4.3 Forecasting Engine Regression Suite (`forecasting-engine/tests/`)
```text
============================== 2 passed in 0.65s ==============================
```

### 4.4 Live MCP Runtime Smoke Test (`scratch/mcp_client_smoke_test.py`)
```text
==================================================================
SMOKE TEST SUMMARY: 14/14 calls succeeded!
- check_database_connection       : SUCCESS (Read-only verified)
- get_product_info                : SUCCESS
- get_group_demand_history_tool   : SUCCESS
- get_group_forecast_tool         : SUCCESS
- get_group_recommendation_tool   : SUCCESS
- get_cold_start_diagnostic_tool  : SUCCESS
==================================================================
```

---

## 5. Invariant Confirmation & Preserved Contracts

1. **Tasks 4–11 Replenishment Math**: Fully intact ($\text{IP}$, 4-month horizon, $\text{RMSE}_{1M}$ error safety stock, out-of-sample confidence, rolling model selection, stockout censoring, $N \ge 6$ short-history rules, calculation breakdown).
2. **Cold-Start Analogue Diagnostic**: Remains strictly advisory for $N < 6$ groups with $0$ purchase quantity.
3. **MCP Tooling Sidecar**: Operates in clean read-only mode over `stdio` transport.
4. **Odoo Database Safety**: ZERO writes, ZERO mutations, 100% read-only confirmed.

---

## 6. Next Steps & Phase 2 Recommendations

1. **Phase 2 — Planning Run Architecture**: Implement explicit `run_id` planning cycles and point-in-time snapshot persistence.
2. **Phase 2 — Alembic Schema Migrations**: Initialize Alembic migration scripts to track and version POC database table schemas.
