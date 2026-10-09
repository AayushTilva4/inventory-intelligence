import logging
from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import get_current_user
from app.ai.gemini_service import explain_product_intelligence
from app.db.repository import get_product_intelligence
from app.forecasting.engine_adapter import load_forecasting_inputs


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/ai",
    tags=["AI"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/explain/{product_id}")
def explain_product(product_id: int):
    intelligence = get_product_intelligence(product_id)

    if intelligence is None:
        raise HTTPException(
            status_code=404,
            detail=f"Product {product_id} not found",
        )

    try:
        inputs = load_forecasting_inputs()

        history_df = inputs["monthly_df"][
            inputs["monthly_df"]["product_id"] == product_id
        ].copy()

        history_df["month"] = (
            history_df["month"]
            .astype(str)
        )

        history_df = (
            history_df
            .sort_values("month")
            .tail(12)
        )

        recent_history = [
            {
                "month": str(row["month"]),
                "actual": float(row["total_quantity"]),
            }
            for _, row in history_df.iterrows()
        ]

        explanation = explain_product_intelligence(
            intelligence=intelligence,
            recent_history=recent_history,
        )

        return {
            "product_id": product_id,
            "product_name": intelligence["product_name"],
            "action": intelligence["action"],
            "priority": intelligence["priority"],
            "suggested_purchase_qty": intelligence[
                "suggested_purchase_qty"
            ],
            "explanation": explanation,
        }

    except Exception as exc:
        logger.exception("AI explanation failed for product_id=%s", product_id)
        raise HTTPException(
            status_code=500,
            detail="AI explanation failed. Please contact the administrator.",
        )