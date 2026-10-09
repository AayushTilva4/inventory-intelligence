from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import get_current_user
from app.db.repository import (
    get_recommendations,
    update_approval_status,
    create_draft_po_for_product,
    get_all_draft_pos,
)
from app.api.schemas import (
    InventoryRecommendation,
    InventorySummary,
)

router = APIRouter(
    prefix="/api/inventory",
    tags=["Inventory"],
    dependencies=[Depends(get_current_user)],
)



@router.get(
    "/recommendations",
    response_model=list[InventoryRecommendation],
)
def inventory_recommendations():
    return get_recommendations()


@router.get("/draft-pos")
def draft_purchase_orders():
    raise HTTPException(
        status_code=403,
        detail="Draft purchase order operations are disabled in the read-only POC.",
    )


@router.get(
    "/summary",
    response_model=InventorySummary,
)
def inventory_summary():
    recommendations = get_recommendations()

    total = len(recommendations)

    action_counts = {}
    priority_counts = {}

    for item in recommendations:
        action = item.get("action")
        priority = item.get("priority")

        if action:
            action_counts[action] = (
                action_counts.get(action, 0) + 1
            )

        if priority:
            priority_counts[priority] = (
                priority_counts.get(priority, 0) + 1
            )

    return {
        "total_products": total,
        "actions": action_counts,
        "priorities": priority_counts,
    }


@router.post("/recommendations/{product_id}/approve")
def approve_recommendation(product_id: int):
    raise HTTPException(
        status_code=403,
        detail="Recommendation approval workflows are disabled in the read-only POC.",
    )


@router.post("/recommendations/{product_id}/reject")
def reject_recommendation(product_id: int):
    raise HTTPException(
        status_code=403,
        detail="Recommendation rejection workflows are disabled in the read-only POC.",
    )


@router.post("/recommendations/{product_id}/create-draft-po")
def create_draft_po(product_id: int):
    raise HTTPException(
        status_code=403,
        detail="Purchase order creation is disabled in the read-only POC.",
    )
