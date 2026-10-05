import pandas as pd


def months_since_last_sale(product_df: pd.DataFrame) -> int:
    """Counts consecutive trailing months with zero sales."""
    quantities = product_df["total_quantity"].astype(float).reset_index(drop=True)

    count = 0
    for value in quantities.iloc[::-1]:
        if value > 0:
            break
        count += 1

    return count


def detect_dead_stock(
    stock_on_hand: float,
    avg_monthly_demand: float,
    months_since_last_sale: int,
    dead_stock_months_threshold: int = 6,
) -> dict:
    """
    Flags dead stock: meaningful stock on hand + no sales for a long
    time. Zero stock is NOT dead stock — that's a restock case.
    """
    if stock_on_hand <= 0:
        return {"dead_stock": False, "dead_stock_reason": "no_stock_on_hand", "suggested_discount_pct": None}

    if months_since_last_sale < dead_stock_months_threshold:
        return {"dead_stock": False, "dead_stock_reason": None, "suggested_discount_pct": None}

    excess_months = months_since_last_sale - dead_stock_months_threshold
    suggested_discount = min(10 + excess_months * 5, 50)

    return {
        "dead_stock": True,
        "dead_stock_reason": f"no_sales_in_{months_since_last_sale}_months",
        "suggested_discount_pct": suggested_discount,
    }