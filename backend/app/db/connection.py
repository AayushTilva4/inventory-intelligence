import os
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine


load_dotenv()

_poc_engine: Optional[Engine] = None
_odoo_engine: Optional[Engine] = None


def get_poc_engine() -> Engine:
    """Returns a pooled SQLAlchemy engine connected to the POC application database."""
    global _poc_engine
    if _poc_engine is not None:
        return _poc_engine

    host = os.getenv("POC_DB_HOST")
    port = os.getenv("POC_DB_PORT")
    database = os.getenv("POC_DB_NAME")
    user = os.getenv("POC_DB_USER")
    password = os.getenv("POC_DB_PASSWORD")

    required = {
        "POC_DB_HOST": host,
        "POC_DB_PORT": port,
        "POC_DB_NAME": database,
        "POC_DB_USER": user,
        "POC_DB_PASSWORD": password,
    }

    missing = [
        key
        for key, value in required.items()
        if not value
    ]

    if missing:
        raise RuntimeError(
            "Missing POC database configuration: "
            + ", ".join(missing)
        )

    _poc_engine = create_engine(
        f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}",
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
        pool_pre_ping=True,
    )
    return _poc_engine


def get_odoo_engine() -> Engine:
    """Returns a SQLAlchemy engine connected to the Odoo database. Enforces strict read-only transactions."""
    global _odoo_engine
    if _odoo_engine is not None:
        return _odoo_engine

    host = os.getenv("ODOO_DB_HOST")
    port = os.getenv("ODOO_DB_PORT")
    database = os.getenv("ODOO_DB_NAME")
    user = os.getenv("ODOO_DB_USER")
    password = os.getenv("ODOO_DB_PASSWORD")

    required = {
        "ODOO_DB_HOST": host,
        "ODOO_DB_PORT": port,
        "ODOO_DB_NAME": database,
        "ODOO_DB_USER": user,
        "ODOO_DB_PASSWORD": password,
    }

    missing = [key for key, value in required.items() if not value]
    if missing:
        raise RuntimeError("Missing Odoo database configuration: " + ", ".join(missing))

    _odoo_engine = create_engine(
        f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}",
        connect_args={"options": "-c default_transaction_read_only=on"},
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
        pool_pre_ping=True,
    )
    return _odoo_engine


def reset_engines() -> None:
    """Disposes and resets engine singletons (useful for test isolation)."""
    global _poc_engine, _odoo_engine
    if _poc_engine is not None:
        _poc_engine.dispose()
        _poc_engine = None
    if _odoo_engine is not None:
        _odoo_engine.dispose()
        _odoo_engine = None