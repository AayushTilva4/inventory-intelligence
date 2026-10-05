from fastapi import APIRouter, HTTPException

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
)


@router.get(
    "/recommendations",
    response_model=list[InventoryRecommendation],
)
def inventory_recommendations():
    return get_recommendations()


@router.get("/draft-pos")
def draft_purchase_orders():
    return get_all_draft_pos()


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
    updated = update_approval_status(
        product_id,
        "approved",
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Recommendation for product "
                f"{product_id} not found"
            ),
        )

    return {
        "product_id": product_id,
        "approval_status": "approved",
    }


@router.post("/recommendations/{product_id}/reject")
def reject_recommendation(product_id: int):
    updated = update_approval_status(
        product_id,
        "rejected",
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Recommendation for product "
                f"{product_id} not found"
            ),
        )

    return {
        "product_id": product_id,
        "approval_status": "rejected",
    }


@router.post("/recommendations/{product_id}/create-draft-po")
def create_draft_po(product_id: int):
    try:
        po_info = create_draft_po_for_product(product_id)
        return po_info
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))