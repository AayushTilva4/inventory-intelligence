"""
Inventory Intelligence Read-Only MCP Server CLI Entrypoint.

Usage:
  python mcp_server.py
"""

from app.mcp.server import mcp

if __name__ == "__main__":
    mcp.run()
