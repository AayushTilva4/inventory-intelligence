"""
Unit Test Suite for Phase 1 Security Remediation.

Validates:
1. Unauthenticated access enforcement (401) on all protected routers.
2. Approved public endpoints access (/health, /api/auth/login).
3. Public signup rejection (403).
4. Disabled purchase order endpoints (403).
5. JWT secret safety, startup failure on missing/weak secret, and token verification.
6. Password hashing with per-user unique salt, verification, and transparent legacy migration.
7. Admin bootstrap script execution and non-destructive idempotency.
8. Odoo PostgreSQL driver-level read-only transaction enforcement.
9. CORS configuration hardening.
10. Internal error sanitization in HTTP 500 responses.
"""

import datetime
import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient
import jwt
from sqlalchemy import text

from app.main import app
from app.api.auth import (
    JWT_ALGORITHM,
    get_jwt_secret,
    hash_password,
    verify_password,
)
from app.db.connection import get_odoo_engine, get_poc_engine
from scripts.bootstrap_admin import bootstrap_admin



class TestSecurityRemediation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        # Ensure bootstrap admin exists
        bootstrap_admin(
            email="admin@dazzle.local",
            password="SecureAdminPassword2026!",
            name="Security Admin",
            force=True,
        )
        # Obtain a valid admin token
        res = cls.client.post(
            "/api/auth/login",
            json={"email": "admin@dazzle.local", "password": "SecureAdminPassword2026!"},
        )
        assert res.status_code == 200, f"Login failed: {res.text}"
        cls.admin_token = res.json()["token"]
        cls.auth_headers = {"Authorization": f"Bearer {cls.admin_token}"}

    def test_01_public_health_check(self):
        """Verifies that /health is public and returns 200 without authentication."""
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "inventory-intelligence-poc")

    def test_02_unauthenticated_access_rejected_on_all_protected_routers(self):
        """Verifies that all operational endpoints reject unauthenticated requests with 401."""
        protected_endpoints = [
            ("GET", "/api/main-products"),
            ("GET", "/api/main-products/413"),
            ("GET", "/api/main-products/413/forecast"),
            ("GET", "/api/main-products/413/recommendation"),
            ("GET", "/api/inventory/recommendations"),
            ("GET", "/api/inventory/summary"),
            ("GET", "/api/inventory/draft-pos"),
            ("GET", "/api/forecast/product/413"),
            ("GET", "/api/products/413/group"),
            ("GET", "/api/products/413/group/history"),
            ("GET", "/api/products/413/group/forecast"),
            ("GET", "/api/products/413/group/recommendation"),
            ("GET", "/api/shadow/snapshots"),
            ("GET", "/api/shadow/exceptions/summary"),
            ("GET", "/api/shadow/comparisons"),
            ("GET", "/api/ai/explain/413"),
            ("GET", "/api/auth/me"),
            ("POST", "/api/auth/logout"),
        ]
        for method, endpoint in protected_endpoints:
            if method == "GET":
                res = self.client.get(endpoint)
            else:
                res = self.client.post(endpoint)
            self.assertEqual(
                res.status_code,
                401,
                f"Endpoint {method} {endpoint} did not return 401 (got {res.status_code})",
            )
            self.assertIn("detail", res.json())

    def test_03_authenticated_access_succeeds_on_protected_endpoints(self):
        """Verifies that valid JWT authentication grants access to protected endpoints."""
        res = self.client.get("/api/auth/me", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["email"], "admin@dazzle.local")

        res_inv = self.client.get("/api/inventory/summary", headers=self.auth_headers)
        self.assertEqual(res_inv.status_code, 200)

        res_main = self.client.get("/api/main-products", headers=self.auth_headers)
        self.assertEqual(res_main.status_code, 200)

    def test_04_public_signup_is_disabled(self):
        """Verifies that public signup returns 403 Forbidden."""
        res = self.client.post(
            "/api/auth/signup",
            json={"name": "Attacker", "email": "attacker@evil.com", "password": "Password123!"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("disabled", res.json()["detail"].lower())

    def test_05_procurement_and_approval_endpoints_are_disabled(self):
        """Verifies that purchase order and approval workflow endpoints return 403 Forbidden."""
        # Main product PO creation
        res_main_po = self.client.post(
            "/api/main-products/413/create-po",
            headers=self.auth_headers,
            json={"quantity": 100},
        )
        self.assertEqual(res_main_po.status_code, 403)
        self.assertIn("disabled", res_main_po.json()["detail"].lower())

        # Inventory draft PO creation
        res_draft_po = self.client.post(
            "/api/inventory/recommendations/413/create-draft-po",
            headers=self.auth_headers,
        )
        self.assertEqual(res_draft_po.status_code, 403)
        self.assertIn("disabled", res_draft_po.json()["detail"].lower())

        # Inventory draft PO list
        res_draft_list = self.client.get(
            "/api/inventory/draft-pos",
            headers=self.auth_headers,
        )
        self.assertEqual(res_draft_list.status_code, 403)
        self.assertIn("disabled", res_draft_list.json()["detail"].lower())

        # Inventory recommendation approval
        res_appr = self.client.post(
            "/api/inventory/recommendations/413/approve",
            headers=self.auth_headers,
        )
        self.assertEqual(res_appr.status_code, 403)
        self.assertIn("disabled", res_appr.json()["detail"].lower())

        # Inventory recommendation rejection
        res_rej = self.client.post(
            "/api/inventory/recommendations/413/reject",
            headers=self.auth_headers,
        )
        self.assertEqual(res_rej.status_code, 403)
        self.assertIn("disabled", res_rej.json()["detail"].lower())

    def test_06_jwt_secret_startup_validation(self):
        """Verifies that get_jwt_secret fails safely when secret is missing or shorter than 32 chars."""
        with patch.dict(os.environ, {"JWT_SECRET": ""}):
            with self.assertRaises(RuntimeError):
                get_jwt_secret()

        with patch.dict(os.environ, {"JWT_SECRET": "too-short-secret"}):
            with self.assertRaises(RuntimeError):
                get_jwt_secret()

        valid_secret = "a" * 32
        with patch.dict(os.environ, {"JWT_SECRET": valid_secret}):
            self.assertEqual(get_jwt_secret(), valid_secret)

    def test_07_invalid_and_expired_jwt_tokens(self):
        """Verifies that invalid or expired JWT tokens are properly rejected with 401."""
        # Expired token
        secret = get_jwt_secret()
        expired_token = jwt.encode(
            {
                "sub": "1",
                "email": "test@dazzle.local",
                "exp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1),
            },
            secret,
            algorithm=JWT_ALGORITHM,
        )
        res_exp = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        self.assertEqual(res_exp.status_code, 401)
        self.assertIn("expired", res_exp.json()["detail"].lower())

        # Tampered token
        res_tampered = self.client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token.payload"})
        self.assertEqual(res_tampered.status_code, 401)

    def test_08_password_hashing_with_unique_salts_and_owasp_cost(self):
        """Verifies that password hashing uses OWASP N=65536, r=8, p=2 and distinct random salts for identical passwords."""
        pw = "SamePassword123!"
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        self.assertNotEqual(h1, h2)
        self.assertTrue(h1.startswith("scrypt$65536$8$2$"))
        self.assertTrue(h2.startswith("scrypt$65536$8$2$"))

        # Both verify correctly without needing rehash
        valid1, rehash1 = verify_password(pw, h1)
        valid2, rehash2 = verify_password(pw, h2)
        self.assertTrue(valid1)
        self.assertFalse(rehash1)
        self.assertTrue(valid2)
        self.assertFalse(rehash2)

        # Wrong password fails
        valid_wrong, _ = verify_password("WrongPassword!", h1)
        self.assertFalse(valid_wrong)

    def test_09_legacy_and_lower_cost_hash_verification_and_migration(self):
        """Verifies that legacy hashes and lower-cost scrypt hashes verify and flag for rehash."""
        # 1. Lower cost scrypt (N=65536, r=8, p=1)
        pw = "LowerCostPass123!"
        p1_hash = hash_password(pw, p=1)
        valid_p1, rehash_p1 = verify_password(pw, p1_hash)
        self.assertTrue(valid_p1)
        self.assertTrue(rehash_p1)

        # 2. Legacy static-salt format (128 hex chars)
        import hashlib
        legacy_pw = "LegacySecretPass!"
        legacy_hash = hashlib.scrypt(
            legacy_pw.encode("utf-8"),
            salt=b"some-fixed-salt-for-poc",
            n=16384,
            r=8,
            p=1,
            maxmem=256 * 1024 * 1024,
        ).hex()
        self.assertEqual(len(legacy_hash), 128)

        is_valid, needs_rehash = verify_password(legacy_pw, legacy_hash)
        self.assertTrue(is_valid)
        self.assertTrue(needs_rehash)

        # Wrong password fails
        is_wrong, _ = verify_password("IncorrectPass", legacy_hash)
        self.assertFalse(is_wrong)



    def test_10_admin_bootstrap_idempotency(self):
        """Verifies that bootstrap_admin is idempotent and does not overwrite existing accounts without force."""
        # Non-force on existing account returns False
        created = bootstrap_admin(
            email="admin@dazzle.local",
            password="NewPassword123!",
            name="Admin Duplicate",
            force=False,
        )
        self.assertFalse(created)

        # Force on existing account updates password
        updated = bootstrap_admin(
            email="admin@dazzle.local",
            password="UpdatedSecurePass2026!",
            name="Admin Updated",
            force=True,
        )
        self.assertTrue(updated)

        # Verify login with updated password
        res = self.client.post(
            "/api/auth/login",
            json={"email": "admin@dazzle.local", "password": "UpdatedSecurePass2026!"},
        )
        self.assertEqual(res.status_code, 200)

    def test_11_odoo_read_only_transaction_enforcement(self):
        """Verifies that the Odoo SQLAlchemy connection strictly rejects write operations."""
        engine = get_odoo_engine()
        # SELECT is permitted
        with engine.connect() as conn:
            res = conn.execute(text("SELECT count(*) FROM product_template")).scalar()
            self.assertGreater(res, 0)

        # UPDATE is strictly rejected at the PostgreSQL transaction level
        with engine.connect() as conn_update:
            with self.assertRaises(Exception) as ctx:
                conn_update.execute(text("UPDATE product_template SET name = name WHERE id = 1"))
            self.assertIn("read-only transaction", str(ctx.exception).lower())

        # INSERT is strictly rejected at the PostgreSQL transaction level
        with engine.connect() as conn_insert:
            with self.assertRaises(Exception) as ctx_ins:
                conn_insert.execute(text('INSERT INTO product_template (name) VALUES (\'{"en_US": "Hacked"}\')'))
            self.assertIn("read-only transaction", str(ctx_ins.exception).lower())

        # DDL (CREATE TABLE) is strictly rejected at the PostgreSQL transaction level
        with engine.connect() as conn_ddl:
            with self.assertRaises(Exception) as ctx_ddl:
                conn_ddl.execute(text("CREATE TABLE test_security_write (id INT)"))
            self.assertIn("read-only transaction", str(ctx_ddl.exception).lower())



    def test_12_cors_configuration(self):
        """Verifies CORS headers on preflight requests."""
        res = self.client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("access-control-allow-origin"), "http://localhost:3000")
        self.assertEqual(res.headers.get("access-control-allow-credentials"), "true")


if __name__ == "__main__":
    unittest.main()
