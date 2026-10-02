import sys
from pathlib import Path

from sqlalchemy import text


# Add E:\Agent\backend to Python's import path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))


from app.db.connection import get_poc_engine


def main():
    engine = get_poc_engine()

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                ALTER TABLE inventory_recommendations
                ADD COLUMN IF NOT EXISTS approval_status VARCHAR(20)
                    NOT NULL DEFAULT 'pending';

                ALTER TABLE inventory_recommendations
                ADD COLUMN IF NOT EXISTS approval_updated_at TIMESTAMP NULL;
                """
            )
        )

    print("Approval fields added successfully.")


if __name__ == "__main__":
    main()