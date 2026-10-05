# Inventory Intelligence

An AI-powered inventory demand forecasting and replenishment recommendation portal integrated with Odoo 17.

---

## Prerequisites

- **Operating System:** Windows
- **Odoo 17** (Installed/configured with access to your Odoo database `.dump`)
- **PostgreSQL** (Running locally or on an accessible network host)
- **Node.js** 18+ & **npm**
- **Python** 3.10+
- **Git**

---

## Deployment & Installation Guide

### Step A: Restore Odoo Database
Restore your existing Odoo `.dump` file into your PostgreSQL server using standard pgAdmin / `pg_restore` tools.
*(Note: The Odoo database dump is not part of this repository; access is strictly read-only).*

### Step B: Create Empty POC Database
Create an empty PostgreSQL database and database role for the Inventory Intelligence application:
- **Database Name:** `inventory_intelligence` (or `inventory_intelligence_poc`)
- **Owner / User:** `inventory_poc` (or your preferred username)
- **Password:** `<your_poc_db_password>`

*(This POC database is kept completely separate from your Odoo database).*

### Step C: Clone Repository
```powershell
git clone <repository-url>
cd inventory-intelligence
```

### Step D: Configure Environment (`backend/.env`)
Copy the environment template:
```powershell
Copy-Item backend\.env.example backend\.env
```

Edit `backend\.env` and supply your database connection parameters:
```env
# Odoo Database Connection (Read-Only Access)
ODOO_DB_HOST=localhost
ODOO_DB_PORT=5432
ODOO_DB_NAME=your_odoo_db_name
ODOO_DB_USER=your_odoo_db_user
ODOO_DB_PASSWORD=your_odoo_db_password

# Application POC Database Connection
POC_DB_HOST=localhost
POC_DB_PORT=5432
POC_DB_NAME=inventory_intelligence
POC_DB_USER=inventory_poc
POC_DB_PASSWORD=your_poc_db_password

# Authentication & Forecasting Configuration
JWT_SECRET=your-secure-random-jwt-secret-key
FORECAST_ENGINE_ROOT=../forecasting-engine

# Optional AI Explanations
GEMINI_API_KEY=your_optional_gemini_api_key
GEMINI_MODEL=gemini-3.8-flash
```

### Step E: Run Setup Script
Execute the automated setup script:
```powershell
.\setup.ps1
```
This script automatically:
1. Validates Python 3.10+ and Node.js availability.
2. Creates the Python virtual environment (`backend\.venv`) and installs backend requirements.
3. Installs frontend npm packages (`frontend\node_modules`).
4. Generates `frontend\.env.local` if missing.
5. Connects to your empty POC database and initializes application tables (`IF NOT EXISTS`).
6. Reads your Odoo data and populates initial forecasts and recommendation snapshots.

### Step F: Run Application
Start the application backend and frontend:
```powershell
.\run.ps1
```

### Step G: Access Portal
Open your web browser:
- **Application Portal:** [http://localhost:3000](http://localhost:3000)
- **Backend API Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Step H: Stop Application
To stop all running backend and frontend background processes:
```powershell
.\stop.ps1
```

---

## Troubleshooting

- **POC Database Does Not Exist:**
  If `setup.ps1` fails with `POC database '<name>' must already exist`, ensure you have created the empty PostgreSQL database in PostgreSQL before running setup.

- **Odoo Connection Failed:**
  Verify `ODOO_DB_HOST`, `ODOO_DB_PORT`, `ODOO_DB_NAME`, `ODOO_DB_USER`, and `ODOO_DB_PASSWORD` in `backend\.env`. Ensure PostgreSQL is running and accepting connections.

- **Backend Port 8000 Already in Use:**
  Run `.\stop.ps1` or terminate any existing processes listening on port 8000 (`netstat -ano | findstr :8000`).

- **Frontend Port 3000 Already in Use:**
  Run `.\stop.ps1` or terminate any existing node/next processes (`netstat -ano | findstr :3000`).

- **npm Installation Problem:**
  Delete `frontend\node_modules` and `frontend\package-lock.json`, then rerun `.\setup.ps1`.

- **Python Dependency Problem:**
  Delete `backend\.venv`, ensure Python 3.10+ is in your PATH, and rerun `.\setup.ps1`.
