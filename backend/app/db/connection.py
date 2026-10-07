import os

from dotenv import load_dotenv
from sqlalchemy import create_engine


load_dotenv()


def get_poc_engine():
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

    return create_engine(
        f"postgresql+psycopg2://{user}:{password}"
        f"@{host}:{port}/{database}"
    )


def get_odoo_engine():
    """Returns a SQLAlchemy engine connected to the Odoo database. Strictly for READ-ONLY queries."""
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

    return create_engine(
        f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
    )