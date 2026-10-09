"""
Inventory Intelligence Read-Only MCP Server.

Provides a standardized, read-only Model Context Protocol (MCP) interface
exposing forecasting, replenishment recommendation, demand history, and cold-start
diagnostics to compatible AI agents.

Strict Safety Guarantees:
- Strictly READ-ONLY: Executes only SELECT statements against Odoo.
- No writes, purchase orders, RFQs, quants, moves, or schema modifications.
- Reuses the active Tasks 4–11 application service layer; no duplicate business logic.
- Maintains strict operational isolation: cold-start diagnostics are advisory-only.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from sqlalchemy import text

# Ensure backend root is on sys.path
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.connection import get_odoo_engine
from app.forecasting.group_forecast_service import get_group_forecast
from app.inventory.group_recommendation_service import get_group_recommendation
from app.odoo.group_demand_service import get_group_demand_history
from app.forecasting.cold_start_analogue_service import get_cold_start_analogues
from app.odoo.product_group_service import get_main_product, get_group_members


# Initialize MCP Server instance
mcp = MCPServer("Inventory Intelligence Read-Only MCP")


def _resolve_product_id(identifier: str | int) -> dict[str, Any] | None:
    """
    Resolves a product code, default_code, name, or integer ID to its
    canonical product_template_id and product_product_id.
    """
    if identifier is None:
        return None

    engine = get_odoo_engine()
    with engine.connect() as conn:
        # Check if identifier is an integer ID or digit string
        if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.strip().isdigit()):
            int_id = int(identifier)
            row = conn.execute(
                text("""
                    SELECT 
                        pp.id as product_id,
                        pt.id as product_template_id,
                        pp.default_code,
                        pt.name->>'en_US' as product_name,
                        pt.categ_id,
                        pt.main_product
                    FROM product_template pt
                    LEFT JOIN product_product pp ON pp.product_tmpl_id = pt.id
                    WHERE pt.id = :id OR pp.id = :id
                    LIMIT 1
                """),
                {"id": int_id}
            ).mappings().first()
            if row:
                d = dict(row)
                if not d.get("default_code"):
                    d["default_code"] = d.get("product_name")
                return d

        # Lookup by default_code or name
        str_id = str(identifier).strip()
        row = conn.execute(
            text("""
                SELECT 
                    pp.id as product_id,
                    pt.id as product_template_id,
                    pp.default_code,
                    pt.name->>'en_US' as product_name,
                    pt.categ_id,
                    pt.main_product
                FROM product_template pt
                LEFT JOIN product_product pp ON pp.product_tmpl_id = pt.id
                WHERE pp.default_code = :code OR pt.name->>'en_US' = :code
                ORDER BY (pp.default_code = :code) DESC
                LIMIT 1
            """),
            {"code": str_id}
        ).mappings().first()
        if row:
            d = dict(row)
            if not d.get("default_code"):
                d["default_code"] = d.get("product_name")
            return d

        # Fallback template name search
        row_tmpl = conn.execute(
            text("""
                SELECT 
                    NULL as product_id,
                    pt.id as product_template_id,
                    NULL as default_code,
                    pt.name->>'en_US' as product_name,
                    pt.categ_id,
                    pt.main_product
                FROM product_template pt
                WHERE pt.name->>'en_US' ILIKE :code
                LIMIT 1
            """),
            {"code": f"%{str_id}%"}
        ).mappings().first()
        if row_tmpl:
            d = dict(row_tmpl)
            if not d.get("default_code"):
                d["default_code"] = d.get("product_name")
            return d

    return None


@mcp.tool()
def check_database_connection() -> dict[str, Any]:
    """
    Test whether the MCP server has an active, verified read-only connection to PostgreSQL/Odoo.
    """
    try:
        engine = get_odoo_engine()
        with engine.connect() as conn:
            val = conn.execute(text("SELECT 1")).scalar()
            db_name = conn.execute(text("SELECT current_database()")).scalar()
        return {
            "status": "connected",
            "database": db_name,
            "read_only": True,
            "message": "Read-only PostgreSQL connection verified successfully.",
        }
    except Exception as e:
        return {
            "status": "error",
            "read_only": True,
            "error": str(e),
            "message": "Failed to connect to database.",
        }


@mcp.tool()
def get_product_info(identifier: str | int) -> dict[str, Any]:
    """
    Look up product metadata, category, and main-product group hierarchy.

    Args:
        identifier: Product ID (integer), default_code (e.g. '351-02'), or product name.
    """
    try:
        resolved = _resolve_product_id(identifier)
        if not resolved:
            return {
                "found": False,
                "identifier": identifier,
                "message": f"Product '{identifier}' was not found in the catalog.",
            }

        tmpl_id = resolved["product_template_id"]
        main_prod = get_main_product(tmpl_id)
        members = get_group_members(tmpl_id)

        return {
            "found": True,
            "identifier": identifier,
            "product_id": resolved.get("product_id"),
            "product_template_id": tmpl_id,
            "product_name": resolved.get("product_name"),
            "default_code": resolved.get("default_code"),
            "category_id": resolved.get("categ_id"),
            "main_product_id": resolved.get("main_product") or tmpl_id,
            "is_group_leader": (resolved.get("main_product") is None or resolved.get("main_product") == tmpl_id),
            "group_member_count": len(members),
            "group_members": [
                {
                    "product_id": m.get("product_id"),
                    "product_template_id": m.get("product_template_id"),
                    "product_name": m.get("product_name"),
                    "default_code": m.get("default_code"),
                }
                for m in members
            ],
        }
    except Exception as e:
        return {
            "found": False,
            "identifier": identifier,
            "error": str(e),
        }


@mcp.tool()
def get_group_demand_history_tool(identifier: str | int) -> dict[str, Any]:
    """
    Get full monthly demand history for a product group with zero-filling and stockout censoring metadata.

    Args:
        identifier: Product ID, template ID, or code (e.g. '351-02').
    """
    try:
        resolved = _resolve_product_id(identifier)
        if not resolved:
            return {
                "status": "not_found",
                "identifier": identifier,
                "message": f"Product '{identifier}' not found.",
            }

        tmpl_id = resolved["product_template_id"]
        history = get_group_demand_history(tmpl_id)
        if not history:
            return {
                "status": "no_history",
                "identifier": identifier,
                "product_template_id": tmpl_id,
                "message": "No demand history found for this product group.",
            }

        return {
            "status": "ok",
            "identifier": identifier,
            "main_product_template_id": history.get("main_product_template_id"),
            "main_product_name": history.get("main_product_name"),
            "total_demand": history.get("total_demand"),
            "months_count": len(history.get("months", [])),
            "months_with_demand": history.get("months_with_demand"),
            "stockout_months_count": history.get("stockout_months_count"),
            "months": history.get("months", []),
        }
    except Exception as e:
        return {
            "status": "error",
            "identifier": identifier,
            "error": str(e),
        }


@mcp.tool()
def get_group_forecast_tool(identifier: str | int) -> dict[str, Any]:
    """
    Get canonical group demand forecast and statistical error metrics.
    For groups with >= 6 months of history, returns the selected operational forecast model.
    For groups with < 6 months, returns 'insufficient_group_history' with an advisory cold-start diagnostic.

    Args:
        identifier: Product ID, template ID, or product code.
    """
    try:
        resolved = _resolve_product_id(identifier)
        if not resolved:
            return {
                "status": "not_found",
                "identifier": identifier,
                "message": f"Product '{identifier}' not found.",
            }

        tmpl_id = resolved["product_template_id"]
        forecast_res = get_group_forecast(tmpl_id)
        if not forecast_res:
            return {
                "status": "unavailable",
                "identifier": identifier,
                "product_template_id": tmpl_id,
                "message": "Group forecast is unavailable.",
            }

        return {
            "status": forecast_res.get("status"),
            "identifier": identifier,
            "main_product_template_id": forecast_res.get("main_product_template_id"),
            "main_product_name": forecast_res.get("main_product_name"),
            "months_available": forecast_res.get("months_available"),
            "best_model": forecast_res.get("best_model"),
            "next_month_forecast": forecast_res.get("next_month_forecast"),
            "forecast_3_months": forecast_res.get("forecast_3_months"),
            "confidence": forecast_res.get("confidence"),
            "mae": forecast_res.get("mae"),
            "wape": forecast_res.get("wape"),
            "mase": forecast_res.get("mase"),
            "cold_start_diagnostic": forecast_res.get("cold_start_diagnostic"),
        }
    except Exception as e:
        return {
            "status": "error",
            "identifier": identifier,
            "error": str(e),
        }


@mcp.tool()
def get_group_recommendation_tool(identifier: str | int) -> dict[str, Any]:
    """
    Get inventory replenishment recommendation, safety stock, target stock, stock gap,
    and transparent calculation breakdown for a product group.

    Args:
        identifier: Product ID, template ID, or product code.
    """
    try:
        resolved = _resolve_product_id(identifier)
        if not resolved:
            return {
                "status": "not_found",
                "identifier": identifier,
                "message": f"Product '{identifier}' not found.",
            }

        tmpl_id = resolved["product_template_id"]
        rec = get_group_recommendation(tmpl_id)
        if not rec:
            return {
                "status": "unavailable",
                "identifier": identifier,
                "product_template_id": tmpl_id,
                "message": "Group recommendation is unavailable.",
            }

        return {
            "status": rec.get("status"),
            "identifier": identifier,
            "main_product_template_id": rec.get("main_product_template_id"),
            "main_product_name": rec.get("main_product_name"),
            "action": rec.get("action"),
            "group_suggested_purchase_qty": rec.get("group_suggested_purchase_qty"),
            "monthly_forecast": rec.get("monthly_forecast"),
            "horizon_forecast": rec.get("horizon_forecast"),
            "safety_stock": rec.get("safety_stock"),
            "target_stock": rec.get("target_stock"),
            "inventory_position": rec.get("inventory_position"),
            "stock_gap": rec.get("stock_gap"),
            "reason_codes": rec.get("reason_codes", []),
            "calculation_breakdown": rec.get("calculation_breakdown"),
            "cold_start_diagnostic": rec.get("cold_start_diagnostic"),
        }
    except Exception as e:
        return {
            "status": "error",
            "identifier": identifier,
            "error": str(e),
        }


@mcp.tool()
def get_cold_start_diagnostic_tool(identifier: str | int) -> dict[str, Any]:
    """
    Get advisory-only cold-start similar-product analogue diagnostic for product groups with < 6 months history.
    Identifies comparable historical products (N >= 6), scores attribute similarity, and calculates Bayesian blend.

    Args:
        identifier: Product ID, template ID, or code.
    """
    try:
        resolved = _resolve_product_id(identifier)
        if not resolved:
            return {
                "status": "not_found",
                "identifier": identifier,
                "message": f"Product '{identifier}' not found.",
            }

        tmpl_id = resolved["product_template_id"]
        diag = get_cold_start_analogues(tmpl_id)
        return diag
    except Exception as e:
        return {
            "status": "error",
            "identifier": identifier,
            "error": str(e),
        }


def create_mcp_server() -> MCPServer:
    """Factory function returning the configured MCPServer instance."""
    return mcp


if __name__ == "__main__":
    mcp.run()
