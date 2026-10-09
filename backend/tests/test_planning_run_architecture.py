import uuid
import unittest
from typing import List
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.planning_run_repository import (
    create_planning_run,
    complete_planning_run,
    fail_planning_run,
    get_planning_run,
    list_planning_runs,
    get_latest_completed_run_id,
    apply_retention_policy,
    generate_run_id,
)
from app.db.group_repository import (
    upsert_group_forecast,
    upsert_group_recommendation,
    get_group_forecast,
    get_group_recommendation,
    get_all_group_forecasts,
    get_all_group_recommendations,
)
from app.api.auth import hash_password


def init_isolated_test_db(engine):
    ddl = [
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        CREATE TABLE planning_runs (
            run_id TEXT PRIMARY KEY,
            started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME NULL,
            status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
            error_message TEXT NULL,
            num_groups INTEGER NOT NULL DEFAULT 0,
            num_products INTEGER NOT NULL DEFAULT 0,
            config_metadata TEXT NOT NULL DEFAULT '{}',
            execution_summary TEXT NOT NULL DEFAULT '{}',
            is_pruned BOOLEAN NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        CREATE UNIQUE INDEX uq_single_running_planning_run ON planning_runs (status) WHERE status = 'running';
        """,
        """
        CREATE TABLE group_forecast_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL DEFAULT 'legacy_initial_run',
            main_product_template_id INTEGER NOT NULL,
            main_product_name TEXT NOT NULL,
            group_size INTEGER NOT NULL,
            months_available INTEGER,
            history_start TEXT,
            history_end TEXT,
            next_month_forecast REAL,
            best_model TEXT,
            confidence TEXT,
            mae REAL,
            wape REAL,
            mase REAL,
            avg_monthly_demand REAL,
            forecast_status TEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_group_forecast_run_template UNIQUE (run_id, main_product_template_id)
        );
        """,
        """
        CREATE TABLE group_inventory_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL DEFAULT 'legacy_initial_run',
            main_product_template_id INTEGER NOT NULL,
            main_product_name TEXT NOT NULL,
            group_size INTEGER NOT NULL,
            group_valid INTEGER NOT NULL,
            group_current_stock REAL,
            group_next_month_forecast REAL,
            best_model TEXT,
            confidence TEXT,
            group_reorder_point REAL,
            group_buffered_target_stock REAL,
            group_stock_gap REAL,
            group_coverage_ratio REAL,
            group_suggested_purchase_qty REAL NOT NULL DEFAULT 0,
            action TEXT NOT NULL,
            priority TEXT NOT NULL,
            reason_codes TEXT NOT NULL DEFAULT '[]',
            validation_issues TEXT NOT NULL DEFAULT '[]',
            validation_warnings TEXT NOT NULL DEFAULT '[]',
            dead_stock INTEGER,
            dead_stock_reason TEXT,
            recommendation_status TEXT NOT NULL,
            forecast_status TEXT,
            approval_status TEXT NOT NULL DEFAULT 'pending',
            approval_updated_at DATETIME NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_group_recommendations_run_template UNIQUE (run_id, main_product_template_id)
        );
        """,
    ]
    with engine.begin() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))


class TestPlanningRunArchitecture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Dedicated isolated in-memory test database (completely separate from application DB)
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_isolated_test_db(cls.engine)
        cls.client = TestClient(app)

    def setUp(self):
        self.created_run_ids: List[str] = []
        self.created_emails: List[str] = []

    def tearDown(self):
        # Explicit isolated cleanup of test-created fixtures in isolated test engine
        with self.engine.begin() as conn:
            for rid in self.created_run_ids:
                conn.execute(text("DELETE FROM group_forecast_results WHERE run_id = :rid"), {"rid": rid})
                conn.execute(text("DELETE FROM group_inventory_recommendations WHERE run_id = :rid"), {"rid": rid})
                conn.execute(text("DELETE FROM planning_runs WHERE run_id = :rid"), {"rid": rid})
            for email in self.created_emails:
                conn.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})


    def test_01_unique_run_ids_and_lifecycle(self):
        run_id_1 = f"test_run_{uuid.uuid4().hex}"
        run_id_2 = f"test_run_{uuid.uuid4().hex}"
        self.created_run_ids.extend([run_id_1, run_id_2])
        self.assertNotEqual(run_id_1, run_id_2)

        created_id = create_planning_run(run_id=run_id_1, config_metadata={"test": "lifecycle"}, engine=self.engine)
        self.assertEqual(created_id, run_id_1)

        run = get_planning_run(run_id_1, engine=self.engine)
        self.assertIsNotNone(run)
        self.assertEqual(run["status"], "running")
        self.assertIsNone(run["completed_at"])

        complete_planning_run(run_id_1, num_groups=5, num_products=5, execution_summary={"status": "ok"}, engine=self.engine)
        run_after = get_planning_run(run_id_1, engine=self.engine)
        self.assertEqual(run_after["status"], "completed")
        self.assertIsNotNone(run_after["completed_at"])
        self.assertEqual(run_after["num_groups"], 5)

    def test_02_failed_and_interrupted_runs(self):
        run_id = f"test_run_{uuid.uuid4().hex}"
        self.created_run_ids.append(run_id)
        create_planning_run(run_id=run_id, engine=self.engine)

        fail_planning_run(run_id=run_id, error_message="Database timeout error", engine=self.engine)
        run = get_planning_run(run_id, engine=self.engine)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error_message"], "Database timeout error")

    def test_03_concurrent_execution_protection(self):
        run_id_active = f"test_run_{uuid.uuid4().hex}"
        run_id_second = f"test_run_{uuid.uuid4().hex}"
        self.created_run_ids.extend([run_id_active, run_id_second])

        create_planning_run(run_id=run_id_active, engine=self.engine)

        with self.assertRaises(RuntimeError) as ctx:
            create_planning_run(run_id=run_id_second, engine=self.engine)
        self.assertIn("currently in progress", str(ctx.exception))

        complete_planning_run(run_id_active, num_groups=0, num_products=0, engine=self.engine)

    def test_04_snapshot_persistence_and_no_overwrites(self):
        run_a = f"test_run_{uuid.uuid4().hex}"
        run_b = f"test_run_{uuid.uuid4().hex}"
        self.created_run_ids.extend([run_a, run_b])

        create_planning_run(run_id=run_a, engine=self.engine)
        forecast_a = {
            "main_product_template_id": 99901,
            "main_product_name": "Test Fabric A",
            "group_size": 2,
            "next_month_forecast": 150.0,
            "best_model": "Holt-Winters",
            "confidence": "high",
            "status": "active_group",
        }
        rec_a = {
            "main_product_template_id": 99901,
            "main_product_name": "Test Fabric A",
            "group_size": 2,
            "group_valid": True,
            "group_next_month_forecast": 150.0,
            "action": "reorder",
            "priority": "high",
        }
        upsert_group_forecast(forecast_a, run_id=run_a, engine=self.engine)
        upsert_group_recommendation(rec_a, run_id=run_a, engine=self.engine)
        complete_planning_run(run_a, num_groups=1, num_products=1, engine=self.engine)

        create_planning_run(run_id=run_b, engine=self.engine)
        forecast_b = {
            "main_product_template_id": 99901,
            "main_product_name": "Test Fabric A",
            "group_size": 2,
            "next_month_forecast": 250.0,
            "best_model": "ARIMA",
            "confidence": "medium",
            "status": "active_group",
        }
        rec_b = {
            "main_product_template_id": 99901,
            "main_product_name": "Test Fabric A",
            "group_size": 2,
            "group_valid": True,
            "group_next_month_forecast": 250.0,
            "action": "reorder",
            "priority": "medium",
        }
        upsert_group_forecast(forecast_b, run_id=run_b, engine=self.engine)
        upsert_group_recommendation(rec_b, run_id=run_b, engine=self.engine)
        complete_planning_run(run_b, num_groups=1, num_products=1, engine=self.engine)

        res_a = get_group_forecast(99901, run_id=run_a, engine=self.engine)
        res_b = get_group_forecast(99901, run_id=run_b, engine=self.engine)

        self.assertIsNotNone(res_a)
        self.assertIsNotNone(res_b)
        self.assertEqual(float(res_a["next_month_forecast"]), 150.0)
        self.assertEqual(float(res_b["next_month_forecast"]), 250.0)
        self.assertEqual(res_a["best_model"], "Holt-Winters")
        self.assertEqual(res_b["best_model"], "ARIMA")

    def test_05_preservation_of_latest_successful_run(self):
        run_good = f"test_run_{uuid.uuid4().hex}"
        self.created_run_ids.append(run_good)
        create_planning_run(run_id=run_good, engine=self.engine)
        complete_planning_run(run_good, num_groups=1, num_products=1, engine=self.engine)

        latest_before = get_latest_completed_run_id(engine=self.engine)
        self.assertEqual(latest_before, run_good)

        run_bad = f"test_run_{uuid.uuid4().hex}"
        self.created_run_ids.append(run_bad)
        create_planning_run(run_id=run_bad, engine=self.engine)
        fail_planning_run(run_bad, error_message="Fatal computation error", engine=self.engine)

        latest_after = get_latest_completed_run_id(engine=self.engine)
        self.assertEqual(latest_after, run_good)

    def test_06_retention_policy_boundaries(self):
        run_ids = []
        for i in range(5):
            rid = f"test_run_{uuid.uuid4().hex}"
            create_planning_run(run_id=rid, engine=self.engine)
            upsert_group_forecast({
                "main_product_template_id": 9999,
                "main_product_name": f"Dummy {i}",
                "group_size": 2,
                "forecast_status": "ok",
            }, run_id=rid, engine=self.engine)
            complete_planning_run(rid, num_groups=1, num_products=1, engine=self.engine)
            with self.engine.begin() as conn:
                conn.execute(
                    text("UPDATE planning_runs SET completed_at = datetime('2026-10-09 10:00:00', '+' || :offset || ' seconds') WHERE run_id = :rid"),
                    {"offset": i, "rid": rid}
                )
            run_ids.append(rid)
            self.created_run_ids.append(rid)

        pruned_count = apply_retention_policy(retention_limit=3, engine=self.engine)
        self.assertGreaterEqual(pruned_count, 2)

        oldest_run = get_planning_run(run_ids[0], engine=self.engine)
        self.assertTrue(oldest_run["is_pruned"])

        latest_run = get_planning_run(run_ids[-1], engine=self.engine)
        self.assertFalse(latest_run["is_pruned"])

    def test_07_api_authentication_and_planning_run_endpoints(self):
        test_email = f"user_{uuid.uuid4().hex[:8]}@test.local"
        test_password = "TestUserPassword2026!"
        self.created_emails.append(test_email)

        # Unauthenticated call to /api/planning-runs should fail with 401
        res_unauth = self.client.get("/api/planning-runs")
        self.assertEqual(res_unauth.status_code, 401)

    def test_08_empty_table_concurrency_race_condition(self):
        import concurrent.futures

        rid_1 = f"test_run_{uuid.uuid4().hex}"
        rid_2 = f"test_run_{uuid.uuid4().hex}"
        self.created_run_ids.extend([rid_1, rid_2])

        results = []
        errors = []

        def worker(rid):
            try:
                out = create_planning_run(run_id=rid, engine=self.engine)
                results.append(out)
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(worker, rid_1)
            f2 = executor.submit(worker, rid_2)
            f1.result()
            f2.result()

        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("in progress", str(errors[0]))

        complete_planning_run(results[0], 0, 0, engine=self.engine)

    def test_09_pruned_and_missing_run_api_behaviour(self):
        # Create a pruned run scenario in isolated test engine
        pruned_rid = f"test_run_{uuid.uuid4().hex}"
        self.created_run_ids.append(pruned_rid)
        create_planning_run(run_id=pruned_rid, engine=self.engine)
        complete_planning_run(pruned_rid, 1, 1, engine=self.engine)

        with self.engine.begin() as conn:
            conn.execute(text("UPDATE planning_runs SET is_pruned = 1 WHERE run_id = :rid"), {"rid": pruned_rid})
            conn.execute(text("DELETE FROM group_forecast_results WHERE run_id = :rid"), {"rid": pruned_rid})

        r_meta = get_planning_run(pruned_rid, engine=self.engine)
        self.assertIsNotNone(r_meta)
        self.assertTrue(r_meta["is_pruned"])


if __name__ == "__main__":
    unittest.main()
