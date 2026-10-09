import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.db.planning_run_repository import (
    get_latest_completed_run_id,
    get_planning_run,
    list_planning_runs,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/planning-runs",
    tags=["Planning Runs"],
    dependencies=[Depends(get_current_user)],
)


class PlanningRunResponse(BaseModel):
    run_id: str
    started_at: Any
    completed_at: Optional[Any] = None
    status: str
    error_message: Optional[str] = None
    num_groups: int = 0
    num_products: int = 0
    config_metadata: dict[str, Any] = {}
    execution_summary: dict[str, Any] = {}
    is_pruned: bool = False
    created_at: Any


@router.get("", response_model=list[PlanningRunResponse])
def get_planning_runs(
    status: Optional[str] = Query(None, description="Filter by status (running, completed, failed)"),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve metadata list of historical planning runs."""
    runs = list_planning_runs(status=status, limit=limit)
    return runs


@router.get("/latest", response_model=PlanningRunResponse)
def get_latest_planning_run():
    """Retrieve metadata for the latest completed planning run."""
    latest_id = get_latest_completed_run_id()
    if not latest_id:
        raise HTTPException(
            status_code=404,
            detail="No completed planning runs found.",
        )
    run = get_planning_run(latest_id)
    if not run:
        raise HTTPException(
            status_code=404,
            detail=f"Planning run metadata for '{latest_id}' not found.",
        )
    return run


@router.get("/{run_id}", response_model=PlanningRunResponse)
def get_planning_run_by_id(run_id: str):
    """Retrieve metadata for a specific planning run by run_id."""
    run = get_planning_run(run_id)
    if not run:
        raise HTTPException(
            status_code=404,
            detail=f"Planning run '{run_id}' not found.",
        )
    return run
