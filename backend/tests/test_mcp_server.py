import unittest
from app.mcp.server import (
    check_database_connection,
    get_product_info,
    get_group_demand_history_tool,
    get_group_forecast_tool,
    get_group_recommendation_tool,
    get_cold_start_diagnostic_tool,
    _resolve_product_id,
)


class TestMCPServer(unittest.TestCase):
    def test_database_connection_tool(self):
        """check_database_connection returns connected status and read-only flag."""
        res = check_database_connection()
        self.assertEqual(res["status"], "connected")
        self.assertTrue(res["read_only"])
        self.assertIsNotNone(res["database"])

    def test_resolve_product_id(self):
        """_resolve_product_id resolves product code, template ID, and name."""
        # By numeric template ID (e.g. 21)
        res_id = _resolve_product_id(21)
        self.assertIsNotNone(res_id)
        self.assertEqual(res_id["product_template_id"], 21)

        # By code / name (e.g. '351-02')
        res_code = _resolve_product_id("351-02")
        self.assertIsNotNone(res_code)
        self.assertEqual(res_code["default_code"], "351-02")

        # Invalid identifier
        res_invalid = _resolve_product_id("INVALID_NONEXISTENT_XYZ_9999")
        self.assertIsNone(res_invalid)

    def test_get_product_info_valid(self):
        """get_product_info returns product metadata and group hierarchy."""
        res = get_product_info("351-02")
        self.assertTrue(res["found"])
        self.assertEqual(res["default_code"], "351-02")
        self.assertIsNotNone(res["product_template_id"])
        self.assertIn("group_members", res)
        self.assertGreaterEqual(res["group_member_count"], 1)

    def test_get_product_info_invalid(self):
        """get_product_info handles non-existent product gracefully."""
        res = get_product_info("NON_EXISTENT_PRODUCT_12345")
        self.assertFalse(res["found"])
        self.assertIn("message", res)

    def test_get_group_demand_history_valid(self):
        """get_group_demand_history_tool returns monthly series with stockout flags."""
        res = get_group_demand_history_tool("351-02")
        self.assertEqual(res["status"], "ok")
        self.assertIn("months", res)
        self.assertGreater(res["months_count"], 0)
        self.assertIn("total_demand", res)
        self.assertIn("stockout_months_count", res)

    def test_get_group_demand_history_invalid(self):
        """get_group_demand_history_tool handles invalid product gracefully."""
        res = get_group_demand_history_tool("NON_EXISTENT_99999")
        self.assertEqual(res["status"], "not_found")

    def test_get_group_forecast_mature_product(self):
        """get_group_forecast_tool returns operational forecast for mature product (N >= 6)."""
        res = get_group_forecast_tool(21)  # 351-09 (18 months)
        self.assertEqual(res["status"], "ok")
        self.assertIsNotNone(res["next_month_forecast"])
        self.assertIsNotNone(res["best_model"])
        self.assertGreaterEqual(res["months_available"], 6)

    def test_get_group_forecast_cold_start_product(self):
        """get_group_forecast_tool returns insufficient_group_history with advisory diagnostic for N < 6."""
        res = get_group_forecast_tool(18569)  # 426-01 (<6 months)
        if res["status"] != "not_found":
            self.assertEqual(res["status"], "insufficient_group_history")
            self.assertIsNone(res["next_month_forecast"])
            self.assertIn("cold_start_diagnostic", res)

    def test_get_group_recommendation_tool_valid(self):
        """get_group_recommendation_tool returns structured inventory decision metrics."""
        res = get_group_recommendation_tool(7737)  # 376-13
        self.assertEqual(res["status"], "ok")
        self.assertIn("action", res)
        self.assertIn("group_suggested_purchase_qty", res)
        self.assertIn("safety_stock", res)
        self.assertIn("inventory_position", res)
        self.assertIn("calculation_breakdown", res)
        self.assertIsNotNone(res["calculation_breakdown"])

    def test_get_group_recommendation_tool_cold_start(self):
        """get_group_recommendation_tool returns review action and 0 purchase qty for cold-start groups."""
        res = get_group_recommendation_tool(18569)  # 426-01
        self.assertIn("action", res)
        self.assertEqual(res["group_suggested_purchase_qty"], 0)

    def test_get_cold_start_diagnostic_tool(self):
        """get_cold_start_diagnostic_tool returns advisory analogue candidate diagnostics."""
        res = get_cold_start_diagnostic_tool(7737)
        self.assertIn("status", res)
        self.assertEqual(res["diagnostic_type"], "cold_start_historical_analogue")
        self.assertIn("limitations", res)
        if res["status"] == "cold_start_analogue_available":
            self.assertIsNotNone(res["summary_analogue_estimate"])
            self.assertGreater(res["candidate_count"], 0)

    def test_tools_return_json_serializable_dicts(self):
        """All MCP tools must return standard Python dicts serializable to JSON."""
        import json
        t1 = check_database_connection()
        json.dumps(t1)
        t2 = get_product_info("351-02")
        json.dumps(t2)
        t3 = get_group_demand_history_tool("351-02")
        json.dumps(t3)
        t4 = get_group_forecast_tool("351-02")
        json.dumps(t4)
        t5 = get_group_recommendation_tool(7737)
        json.dumps(t5)


if __name__ == "__main__":
    unittest.main()
