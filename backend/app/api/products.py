from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    GroupDemandHistoryResponse,
    GroupForecastResponse,
    GroupRecommendationResponse,
    ProductGroupResponse,
)
from app.odoo.group_demand_service import get_group_demand_history
from app.odoo.product_group_service import get_product_group
from app.forecasting.group_forecast_service import get_group_forecast
from app.inventory.group_recommendation_service import get_group_recommendation


router = APIRouter(
    prefix="/api/products",
    tags=["Products"],
)


@router.get("/{product_id}/group", response_model=ProductGroupResponse)
def product_group(product_id: int):
    group = get_product_group(product_id)
    if group is None:
        raise HTTPException(
            status_code=404,
            detail=f"Product {product_id} not found",
        )
    return group


@router.get(
    "/{product_id}/group/history",
    response_model=GroupDemandHistoryResponse,
)
def product_group_history(product_id: int):
    history = get_group_demand_history(product_id)
    if history is None:
        raise HTTPException(
            status_code=404,
            detail=f"Product {product_id} not found",
        )
    return history


@router.get(
    "/{product_id}/group/forecast",
    response_model=GroupForecastResponse,
)
def product_group_forecast(product_id: int):
    forecast = get_group_forecast(product_id)
    if forecast is None:
        raise HTTPException(
            status_code=404,
            detail=f"Product {product_id} not found",
        )
    return forecast


@router.get(
    "/{product_id}/group/recommendation",
    response_model=GroupRecommendationResponse,
)
def product_group_recommendation(product_id: int):
    recommendation = get_group_recommendation(product_id)
    if recommendation is None:
        raise HTTPException(
            status_code=404,
            detail=f"Product {product_id} not found",
        )
    return recommendation