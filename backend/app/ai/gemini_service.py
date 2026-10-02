import os
from typing import Any

from dotenv import load_dotenv
from google import genai


load_dotenv()


def get_gemini_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing from backend .env"
        )

    return genai.Client(api_key=api_key)


def explain_product_intelligence(
    intelligence: dict[str, Any],
    recent_history: list[dict[str, Any]] | None = None,
) -> str:
    model = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.8-flash",
    )

    recent_history = recent_history or []

    prompt = f"""
You are the explanation layer of an inventory intelligence system.

Your job is ONLY to explain the recommendation produced by the
deterministic inventory engine.

Do NOT:
- change the recommendation
- invent quantities
- calculate a different purchase quantity
- override the confidence level
- claim that a purchase is guaranteed to be correct

Use only the supplied data.

Product:
- ID: {intelligence.get("product_id")}
- Name: {intelligence.get("product_name")}

Forecast:
- Next month forecast: {intelligence.get("next_month_forecast")}
- Best model: {intelligence.get("best_model")}
- Confidence: {intelligence.get("confidence")}
- Trend: {intelligence.get("trend")}
- Trend percentage change: {intelligence.get("trend_pct_change")}
- Average monthly demand: {intelligence.get("avg_monthly_demand")}

Inventory:
- Current stock: {intelligence.get("stock_on_hand")}
- Reorder point: {intelligence.get("reorder_point")}
- Buffered target stock: {intelligence.get("buffered_target_stock")}
- Stock gap: {intelligence.get("stock_gap")}
- Coverage ratio: {intelligence.get("coverage_ratio")}

Recommendation:
- Action: {intelligence.get("action")}
- Priority: {intelligence.get("priority")}
- Suggested purchase quantity: {intelligence.get("suggested_purchase_qty")}
- Reason codes: {intelligence.get("reason_codes")}

Recent monthly demand:
{recent_history}

Write a concise explanation for an inventory manager.

Use exactly this structure:

Decision:
<one sentence describing the existing recommendation>

Why:
<2 to 4 sentences explaining the main evidence>

Caution:
<one sentence describing any uncertainty or reason for human review;
if there is no material uncertainty, say "No additional caution flagged.">
"""

    client = get_gemini_client()

    chat = client.chats.create(model=model)

    response = chat.send_message(prompt)

    text = response.text

    if not text:
        raise RuntimeError(
            "Gemini returned an empty response"
        )

    return text.strip()