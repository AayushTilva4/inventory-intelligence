"""Refresh the local historical-similar-product snapshot.

IMPORTANT: this script only reads Odoo with SELECT statements. It never
creates, updates, deletes, or alters anything in the Odoo database.
"""

from pathlib import Path

from src.similar_products import fetch_historical_similarity_candidates


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "historical_similar_product_candidates.csv"


def main() -> None:
    print("Reading historical similar-product links from Odoo (read-only)...")
    df = fetch_historical_similarity_candidates(
        recent_months=12,
        min_old_selling_months=6,
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT, index=False)

    print(f"Saved {len(df)} usable links to: {OUTPUT}")
    print(f"New products covered: {df['new_product_id'].nunique()}")
    print(f"Old products covered: {df['old_product_id'].nunique()}")


if __name__ == "__main__":
    main()
