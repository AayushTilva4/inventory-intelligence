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