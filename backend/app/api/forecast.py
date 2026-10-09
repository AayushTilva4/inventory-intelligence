import logging
from fastapi import APIRouter, Depends, HTTPException
import pandas as pd

from app.api.auth import get_current_user
from app.forecasting.engine_adapter import load_forecasting_inputs
from app.forecasting.forecast_service import get_product_forecast


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/forecast",
    tags=["Forecast"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/product/{product_id}")
def product_forecast(product_id: int):
    try:
        return get_product_forecast(product_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("Product forecast generation failed for product_id=%s", product_id)
        raise HTTPException(
            status_code=500,
            detail="Forecast generation failed. Please contact the administrator.",
        )


@router.get("/product/{product_id}/history")
def product_history(product_id: int):
    try:
        inputs = load_forecasting_inputs()

        monthly_df = inputs["monthly_df"].copy()

        product_df = monthly_df[
            monthly_df["product_id"] == product_id
        ].copy()

        if product_df.empty:
            raise HTTPException(
                status_code=404,
                detail=f"Product {product_id} not found",
            )

        from src.sales_data import complete_product_series

        global_end_month = pd.to_datetime(
            monthly_df["month"]
        ).max()

        product_series = complete_product_series(
            product_df,
            end_date=global_end_month,
        )

        product_series["month"] = pd.to_datetime(
            product_series["month"]
        )

        product_series = (
            product_series
            .sort_values("month")
            .reset_index(drop=True)
        )

        return [
            {
                "month": row["month"].strftime("%Y-%m-%d"),
                "actual": float(row["total_quantity"]),
            }
            for _, row in product_series.iterrows()
        ]

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("Loading product history failed for product_id=%s", product_id)
        raise HTTPException(
            status_code=500,
            detail="Failed to load product history. Please contact the administrator.",
        )