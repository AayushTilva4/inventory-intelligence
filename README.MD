# Inventory Intelligence

An AI-powered inventory demand forecasting and replenishment recommendation portal integrated with Odoo 17.

---

## Prerequisites

- **Odoo 17** (Restored database running on PostgreSQL)
- **PostgreSQL**
- **Python 3.10+**
- **Node.js 18+**
- **Git**

---

## First-Time Setup

1. **Clone the repository:**
   ```bash
   git clone <repository_url>
   cd inventory-intelligence
   ```

2. **Configure environment settings:**
   ```powershell
   Copy-Item backend\.env.example backend\.env
   ```

3. **Edit `backend\.env`** to supply your database and service credentials:
   - `ODOO_DB_*`: Credentials for your read-only Odoo PostgreSQL database.
   - `POC_DB_*`: Credentials for the separate application POC PostgreSQL database.
   - `GEMINI_API_KEY`: *(Optional)* Gemini API key for AI explanations.
   - `JWT_SECRET`: Secret key for authentication tokens.

4. **Run the automatic setup script:**
   ```powershell
   .\setup.ps1
   ```

---

## Running the Application

Start both Backend (FastAPI) and Frontend (Next.js) with a single command:

```powershell
.\run.ps1
```

Access the portal:
- **Frontend App:** [http://localhost:3000](http://localhost:3000)
- **Backend API Docs:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## Stopping Services

To stop all background processes:

```powershell
.\stop.ps1
```
