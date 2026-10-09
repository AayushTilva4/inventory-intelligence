"""
Administrator Bootstrap Script for Inventory Intelligence POC.

Provisions the initial administrative user using environment variables or CLI arguments.
Enforces per-user unique salt password hashing and assigns the 'admin' role.

Usage:
    python -m app.scripts.bootstrap_admin
    or
    python backend/scripts/bootstrap_admin.py --email admin@dazzle.local --password "SecurePass123!"
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure backend root is on sys.path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv(BACKEND_ROOT / ".env")

from app.api.auth import hash_password
from app.db.connection import get_poc_engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("bootstrap_admin")


def bootstrap_admin(
    email: str | None = None,
    password: str | None = None,
    name: str | None = None,
    force: bool = False,
) -> bool:
    """
    Bootstraps an administrative user.
    Returns True if user was created or updated, False if user already exists and no overwrite requested.
    """
    admin_email = (email or os.getenv("ADMIN_EMAIL") or "").strip().lower()
    admin_password = password or os.getenv("ADMIN_PASSWORD") or ""
    admin_name = (name or os.getenv("ADMIN_NAME") or "System Administrator").strip()

    if not admin_email:
        logger.error("Admin bootstrap failed: ADMIN_EMAIL is not specified.")
        return False

    if not admin_password or len(admin_password) < 8:
        logger.error(
            "Admin bootstrap failed: ADMIN_PASSWORD must be provided and contain at least 8 characters."
        )
        return False

    engine = get_poc_engine()
    with engine.begin() as conn:
        # Ensure users table exists with all required columns
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(50) NOT NULL DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
        )
        conn.execute(
            text("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(50) NOT NULL DEFAULT 'user';
            """)
        )

        existing = conn.execute(
            text("SELECT id, name, email, role FROM users WHERE email = :email"),
            {"email": admin_email},
        ).first()

        pw_hash = hash_password(admin_password)

        if existing:
            if not force:
                logger.info(
                    "Administrator account (%s) already exists (id=%s). No changes made. Pass --force to overwrite.",
                    admin_email,
                    existing[0],
                )
                return False
            else:
                conn.execute(
                    text("""
                    UPDATE users
                    SET name = :name, password_hash = :hash, role = 'admin'
                    WHERE email = :email
                    """),
                    {"name": admin_name, "hash": pw_hash, "email": admin_email},
                )
                logger.info("Administrator account (%s) successfully updated.", admin_email)
                return True
        else:
            conn.execute(
                text("""
                INSERT INTO users (name, email, password_hash, role)
                VALUES (:name, :email, :hash, 'admin')
                """),
                {"name": admin_name, "email": admin_email, "hash": pw_hash},
            )
            logger.info("Administrator account (%s) successfully created.", admin_email)
            return True


def main():
    parser = argparse.ArgumentParser(description="Bootstrap Administrator Account")
    parser.add_argument("--email", help="Admin email address", default=None)
    parser.add_argument("--password", help="Admin password (min 8 chars)", default=None)
    parser.add_argument("--name", help="Admin full name", default=None)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite password if account already exists",
    )
    args = parser.parse_args()

    success = bootstrap_admin(
        email=args.email,
        password=args.password,
        name=args.name,
        force=args.force,
    )
    if not success and not (args.email or os.getenv("ADMIN_EMAIL")):
        sys.exit(1)


if __name__ == "__main__":
    main()
