# Inventory Intelligence — Read-Only MCP Server Integration Report

## 1. Executive Summary

This report documents the design, implementation, and verification of the **Read-Only Model Context Protocol (MCP) Server** for the Inventory Intelligence platform.

Adapted from the mentor reference architecture (`forecasting-engine/mcp_server/server.py`), this MCP server exposes the active Tasks 4–11 forecasting, inventory recommendation, demand history, and cold-start diagnostic capabilities to external AI agents using the open MCP 2.x standard.

### Core Architectural Guarantees

1. **Strictly Read-Only**: Every exposed tool executes only `SELECT` statements. The server is mathematically and architecturally incapable of executing purchase orders, RFQs, inventory quant updates, stock moves, or schema mutations.
2. **Zero Business Logic Duplication**: Calls the active, verified service layer directly (`group_forecast_service`, `group_recommendation_service`, `group_demand_service`, `cold_start_analogue_service`, and `product_group_service`).
3. **Operational Invariant Protection**: Tasks 4–11 mathematical formulas remain untouched. For groups with $N < 6$, recommendations remain `review` with $0$ purchase quantity, and cold-start diagnostics are labeled as advisory-only.
4. **Independent Sidecar Process**: The MCP server operates as an isolated stdio process independent of the FastAPI REST API, allowing modular startup and shutdown.

---

## 2. Architecture & Exposed MCP Tools

The MCP server uses the `MCPServer` transport interface from the official Python MCP SDK (`mcp` 2.x), communicating via standard input/output (`stdio`) JSON-RPC.

```
+-----------------------------------------------------------------------------------+
|                            AI AGENT / MCP CLIENT                                  |
+-----------------------------------------------------------------------------------+
                                         |  (JSON-RPC 2.0 over stdio)
                                         v
+-----------------------------------------------------------------------------------+
|                 INVENTORY INTELLIGENCE MCP SERVER (mcp_server.py)                 |
+-----------------------------------------------------------------------------------+
       |                    |                    |                    |
       v                    v                    v                    v
+---------------+  +-----------------+  +-----------------+  +--------------------+
|  Demand Hist  |  | Group Forecast  |  | Recommendation  |  | Cold-Start Analogue|
|  (Task 9)     |  | (Tasks 8, 10)   |  | (Tasks 4-7, 11) |  | (Advisory-Only)    |
+---------------+  +-----------------+  +-----------------+  +--------------------+
       |                    |                    |                    |
       +--------------------+--------------------+--------------------+
                                         |
                                         v
                         [ PostgreSQL / Odoo Read-Only ]
```

### Exposed Tool Registry

| MCP Tool Name | Description | Primary Service Reused | Output Format |
| :--- | :--- | :--- | :--- |
| `check_database_connection` | Tests live read-only connectivity to PostgreSQL. | `app.db.connection.get_odoo_engine` | `dict` (`status`, `database`, `read_only: True`) |
| `get_product_info` | Looks up product metadata, default code, name, category, and main-product group hierarchy. | `app.odoo.product_group_service` | `dict` (`product_id`, `template_id`, `group_members`, `is_group_leader`) |
| `get_group_demand_history_tool` | Returns continuous monthly demand history with zero-filling and stockout censoring metadata. | `app.odoo.group_demand_service` | `dict` (`months`, `total_demand`, `stockout_months_count`, `months_count`) |
| `get_group_forecast_tool` | Returns canonical group demand forecast and statistical error metrics ($N \ge 6$) or insufficient history with advisory diagnostic ($N < 6$). | `app.forecasting.group_forecast_service` | `dict` (`best_model`, `next_month_forecast`, `forecast_3_months`, `wape`, `mase`) |
| `get_group_recommendation_tool` | Returns inventory replenishment recommendation, safety stock, target stock, stock gap, and transparent calculation breakdown. | `app.inventory.group_recommendation_service` | `dict` (`action`, `suggested_purchase_qty`, `safety_stock`, `target_stock`, `breakdown`) |
| `get_cold_start_diagnostic_tool` | Returns advisory cold-start analogue candidate diagnostics for product groups with $N < 6$ months history. | `app.forecasting.cold_start_analogue_service` | `dict` (`candidate_count`, `summary_analogue_estimate`, `analogue_candidates`, `limitations`) |

---

## 3. Files Changed and New Components

1. **`backend/app/mcp/__init__.py`** *(New File)*:
   - Exports `create_mcp_server` and `mcp` instance.
2. **`backend/app/mcp/server.py`** *(New File)*:
   - Implements the MCP tool definitions with input validation, identifier resolution (`default_code`, `name`, numeric ID), and error boundaries.
   - Enforces read-only database connections and structured JSON return formats.
3. **`backend/mcp_server.py`** *(New File)*:
   - Standalone CLI runner entry point for local stdio MCP client connections.
4. **`backend/tests/test_mcp_server.py`** *(New Test Suite)*:
   - 12 comprehensive unit and integration tests verifying all MCP tools, identifier resolutions, JSON serializability, error resilience, and operational invariants.

---

## 4. Setup, Configuration & Client Connection

### 4.1 Running the MCP Server
To run the MCP server in standalone mode over `stdio`:

```bash
cd backend
python mcp_server.py
```

### 4.2 MCP Client Configuration (e.g. Claude Desktop / Gemini / Custom Agents)
Add the server configuration to your MCP client configuration file (e.g., `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "inventory-intelligence": {
      "command": "python",
      "args": [
        "e:/Agent/backend/mcp_server.py"
      ],
      "env": {
        "ODOO_DB_HOST": "localhost",
        "ODOO_DB_PORT": "5432",
        "ODOO_DB_NAME": "odoo",
        "ODOO_DB_USER": "odoo",
        "ODOO_DB_PASSWORD": "..."
      }
    }
  }
}
```

---

## 5. Regression & Verification Evidence

All test suites were executed to verify that the MCP server integration introduced zero regressions into the core platform:

### 5.1 Test Suite Outcomes

- **Dedicated MCP Test Suite (`backend/tests/test_mcp_server.py`)**: **12 passed in 11.51s** (100% pass rate).
  - Verified `check_database_connection` tool status.
  - Verified identifier resolution by ID, default_code, and product name.
  - Verified `get_product_info`, `get_group_demand_history_tool`, `get_group_forecast_tool`, `get_group_recommendation_tool`, and `get_cold_start_diagnostic_tool`.
  - Verified JSON serializability and invalid input safety.
- **Dedicated Cold-Start Suite (`backend/tests/test_cold_start_analogue.py`)**: **13 passed in 8.83s** (100% pass rate).
- **Full Backend Pytest Suite (`backend/tests`)**: **272 passed, 1 skipped in 19.78s** (100% pass rate).
- **Forecasting Engine Pytest Suite (`forecasting-engine/tests`)**: **2 passed in 0.72s** (100% pass rate).

### 5.2 Read-Only & Security Audit
- Verified database engine uses read-only transactions.
- Zero purchase orders, RFQs, stock moves, or quants created during MCP execution.
- No database credentials or internal API tokens are exposed through tool payloads.

---

## 6. Limitations & Deferred Scope

1. **Transport**: The initial implementation uses standard `stdio` JSON-RPC transport. SSE / HTTP streaming transports remain deferred for future cloud microservice deployments if required.
2. **Read-Only Scope**: In strict compliance with system invariants, no write or procurement execution tools were implemented in MCP. Procurement approval remains exclusively within the human planner review workflow.
