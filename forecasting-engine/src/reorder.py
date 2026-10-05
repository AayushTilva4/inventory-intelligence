import pandas as pd


def calculate_reorder_point(
    sales: pd.Series,
    lead_time_months: int = 3,
    safety_stock_months: float = 1.0,
) -> dict:
    """
    reorder_point = (avg monthly demand x lead time) + safety stock
    lead_time_months: the client's ~3-month import wait from China.
    """
    window = min(6, len(sales))
    if window == 0:
        return {"reorder_point": 0.0, "avg_monthly_demand": 0.0}

    avg_monthly_demand = float(sales.iloc[-window:].mean())
    reorder_point = avg_monthly_demand * (lead_time_months + safety_stock_months)

    return {
        "reorder_point": round(reorder_point, 1),
        "avg_monthly_demand": round(avg_monthly_demand, 1),
    }