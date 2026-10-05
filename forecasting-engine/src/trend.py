import pandas as pd


def detect_trend(sales: pd.Series, recent_window: int = 3, prior_window: int = 3) -> dict:
    """
    Compares average sales over the most recent `recent_window` months
    against the `prior_window` months before that, to flag whether
    demand is currently rising, falling, or stable.
    """
    total_needed = recent_window + prior_window

    if len(sales) < total_needed:
        return {"trend": "insufficient_data", "trend_pct_change": None}

    recent = sales.iloc[-recent_window:].mean()
    prior = sales.iloc[-total_needed:-recent_window].mean()

    if prior == 0:
        if recent == 0:
            return {"trend": "flat", "trend_pct_change": 0.0}
        return {"trend": "rising", "trend_pct_change": None}

    # Guard against a near-zero prior period producing an absurd
    # percentage (e.g. 8900%) — report direction only in that case.
    if prior < 1.0:
        return {"trend": "rising" if recent > prior else "flat", "trend_pct_change": None}

    pct_change = (recent - prior) / prior

    if pct_change >= 0.20:
        trend = "rising"
    elif pct_change <= -0.20:
        trend = "falling"
    else:
        trend = "flat"

    pct_change_capped = max(min(pct_change, 5.0), -5.0)  # cap at +/-500%

    return {"trend": trend, "trend_pct_change": round(float(pct_change_capped), 4)}