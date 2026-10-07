"""
FastAPI Router for Human Planner Approval Governance (Step 11).

Provides:
- GET  /api/approvals: Query approval recommendations with filters
- GET  /api/approvals/{approval_id}: Get detailed recommendation with audit trail
- POST /api/approvals/{approval_id}/approve: Transactional planner approval
- POST /api/approvals/{approval_id}/reject: Transactional planner rejection
- POST /api/approvals/{approval_id}/edit: Transactional override (stores original & edited)
- GET  /api/approvals/summary: Status and exception queue breakdown
- POST /api/approvals/sync: Ingest pending recommendations from canary shadow snapshot

STRICT INVARIANTS:
- ZERO Odoo database writes.
- ZERO Odoo PO or RFQ generation.
- Clearly labeled: "AI RECOMMENDATION — REQUIRES PLANNER APPROVAL"
"""

from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.forecasting.benchmark_v2.approvals import PlannerApprovalService

router = APIRouter(
    prefix="/api/approvals",
    tags=["Planner Approvals"],
)

_service: PlannerApprovalService | None = None


def get_approval_service() -> PlannerApprovalService:
    global _service
    if _service is None:
        _service = PlannerApprovalService()
    return _service


class ApproveRequest(BaseModel):
    planner_id: str = Field(..., description="Unique identifier of the approving planner")
    comment: Optional[str] = Field(None, description="Optional approval comments")
    warning_acknowledged: bool = Field(False, description="Acknowledgment for high-risk exception categories")


class RejectRequest(BaseModel):
    planner_id: str = Field(..., description="Unique identifier of the rejecting planner")
    reason: str = Field(..., min_length=3, description="Mandatory reason for rejection")


class EditRequest(BaseModel):
    planner_id: str = Field(..., description="Unique identifier of the overriding planner")
    edited_target_stock: float = Field(..., ge=0, description="Overridden target stock")
    edited_purchase_qty: float = Field(..., ge=0, description="Overridden purchase quantity")
    reason: str = Field(..., min_length=3, description="Mandatory explanation for override")


@router.get("")
def list_approvals(
    snapshot_id: Optional[str] = None,
    status: Optional[str] = None,
    exception_category: Optional[str] = None,
    pattern: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Returns list of recommendations in planner approval queue."""
    service = get_approval_service()
    # Auto-sync if table is empty
    summary = service.get_summary(snapshot_id)
    if summary["total_items"] == 0:
        service.sync_from_snapshot(snapshot_id)

    return service.list_approvals(
        snapshot_id=snapshot_id,
        status=status,
        exception_category=exception_category,
        pattern=pattern,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/summary")
def get_approvals_summary(snapshot_id: Optional[str] = None) -> dict[str, Any]:
    """Provides status and exception queue summary counts."""
    service = get_approval_service()
    res = service.get_summary(snapshot_id)
    if res["total_items"] == 0:
        service.sync_from_snapshot(snapshot_id)
        res = service.get_summary(snapshot_id)
    return res


@router.post("/sync")
def sync_approvals_from_snapshot(snapshot_id: Optional[str] = None) -> dict[str, Any]:
    """Syncs pending recommendations from a canary shadow snapshot."""
    service = get_approval_service()
    inserted = service.sync_from_snapshot(snapshot_id)
    return {
        "status": "success",
        "inserted_pending_records": inserted,
        "disclaimer": "AI RECOMMENDATION — REQUIRES PLANNER APPROVAL",
    }


@router.get("/{approval_id}")
def get_approval_detail(approval_id: str) -> dict[str, Any]:
    """Retrieves an individual recommendation with its full audit trail."""
    service = get_approval_service()
    record = service.get_approval(approval_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Approval record '{approval_id}' not found.")
    return record


@router.post("/{approval_id}/approve")
def approve_recommendation_endpoint(approval_id: str, req: ApproveRequest) -> dict[str, Any]:
    """Approves an AI recommendation without modifying original figures."""
    service = get_approval_service()
    try:
        updated = service.approve_recommendation(
            approval_id=approval_id,
            planner_id=req.planner_id,
            comment=req.comment,
            warning_acknowledged=req.warning_acknowledged,
        )
        return {
            "status": "success",
            "message": "Recommendation successfully APPROVED. No Odoo PO created.",
            "record": updated,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Approval failed: {exc}")


@router.post("/{approval_id}/reject")
def reject_recommendation_endpoint(approval_id: str, req: RejectRequest) -> dict[str, Any]:
    """Rejects an AI recommendation. Requires a mandatory reason."""
    service = get_approval_service()
    try:
        updated = service.reject_recommendation(
            approval_id=approval_id,
            planner_id=req.planner_id,
            reason=req.reason,
        )
        return {
            "status": "success",
            "message": "Recommendation successfully REJECTED. Original AI values preserved.",
            "record": updated,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Rejection failed: {exc}")


@router.post("/{approval_id}/edit")
def edit_recommendation_endpoint(approval_id: str, req: EditRequest) -> dict[str, Any]:
    """Overrides quantities while preserving original AI recommendation."""
    service = get_approval_service()
    try:
        updated = service.edit_recommendation(
            approval_id=approval_id,
            planner_id=req.planner_id,
            edited_target=req.edited_target_stock,
            edited_purchase=req.edited_purchase_qty,
            reason=req.reason,
        )
        return {
            "status": "success",
            "message": "Recommendation overridden and marked EDITED. Original AI values preserved.",
            "record": updated,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Edit failed: {exc}")
