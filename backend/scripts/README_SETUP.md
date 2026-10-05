# Inventory Intelligence — Setup Guide

This directory contains setup scripts for initializing the dedicated POC PostgreSQL database and refreshing initial intelligence snapshots from Odoo data.

---

## 1. Environment Variables

Configure your database and environment credentials in `backend/.env`.

### Required Variables
```env
# Odoo Database (Read-Only)
ODOO_DB_HOST=localhost
ODOO_DB_PORT=5432
ODOO_DB_NAME=your_odoo_db
ODOO_DB_USER=your_odoo_user
ODOO_DB_PASSWORD=your_odoo_password

# POC Database (Application Store)
POC_DB_HOST=localhost
POC_DB_PORT=5432
POC_DB_NAME=inventory_intelligence_poc
POC_DB_USER=inventory_poc_user
POC_DB_PASSWORD=your_poc_password

# Forecasting Engine Path
FORECAST_ENGINE_ROOT=../forecasting-engine
```

### Optional PostgreSQL Admin Variables
If the POC database or user role does not exist yet and the POC user lacks `CREATEDB` / superuser permissions, provide administrator credentials for one-time initialization:
```env
PG_ADMIN_HOST=localhost      # Optional: defaults to POC_DB_HOST
PG_ADMIN_PORT=5432           # Optional: defaults to POC_DB_PORT
PG_ADMIN_DB=postgres         # Optional: defaults to 'postgres'
PG_ADMIN_USER=postgres       # Optional: defaults to 'postgres'
PG_ADMIN_PASSWORD=your_admin_password
```
*(Admin credentials are read only during initial DB creation and never stored anywhere).*

---

## 2. Setup Commands

Execute the setup flow in two clean steps from the `backend/` directory:

### Step 1: Run Database Setup
Idempotently creates the POC database role/schema and initializes application tables.
```bash
python scripts/setup_poc_db.py
```

### Step 2: Run Initial Intelligence Setup
Verifies read-only Odoo access, initializes the POC database, generates initial forecasts & recommendations, and populates POC intelligence tables.
```bash
python scripts/setup_initial_data.py
```

*(You can also run both commands from the repository root, e.g. `python backend/scripts/setup_initial_data.py`).*

---

## 3. Behavior & Safety

- **Odoo Read-Only**: Odoo is queried only for sales, product, stock, and category data. No `INSERT`, `UPDATE`, `DELETE`, `CREATE`, `ALTER`, or `DROP` statements are ever run against Odoo.
- **Persistence Safety**: Refreshing intelligence retains existing recommendation approval decisions (`approval_status` and `approval_updated_at`) and does not corrupt application tables.
- **Idempotency**: Running these scripts multiple times is completely safe and non-destructive.
