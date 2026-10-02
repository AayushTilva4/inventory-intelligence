import os
import sys
from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.db.connection import get_poc_engine

def create_table():
    engine = get_poc_engine()
    query = """
    CREATE TABLE IF NOT EXISTS draft_purchase_orders (
        id SERIAL PRIMARY KEY,
        po_number VARCHAR(255) NOT NULL UNIQUE,
        product_id INT NOT NULL,
        product_name VARCHAR(255),
        quantity INT NOT NULL,
        status VARCHAR(50) DEFAULT 'draft',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    with engine.begin() as conn:
        conn.execute(text(query))
    print("Table created successfully")

if __name__ == "__main__":
    create_table()
