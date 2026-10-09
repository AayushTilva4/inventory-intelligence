from datetime import datetime
from typing import Literal, Any

from pydantic import BaseModel


class InventoryRecommendation(BaseModel):
    scenario: str
    product_id: int
    product_name: str | None

    action: Literal[
        "purchase",
        "review",
        "hold",
        "excess_stock",
        "dead_stock",
    ]

    priority: Literal[
        "high",
        "medium",
        "low",
    ]

    next_month_forecast: float
    current_stock: float
    reorder_point: float
    buffered_target_stock: float
    stock_gap: float
    coverage_ratio: float | None
    suggested_purchase_qty: int

    reason_codes: list[str]

    usable_qty: float | None = None
    cut_piece_qty: float | None = None

    draft_po_number: str | None = None
    draft_po_status: str | None = None
    draft_po_created_at: datetime | str | None = None
    approval_status: str | None = None
    approval_updated_at: datetime | str | None = None

    months_available: int | None = None
    confidence: str | None = None
    trend: str | None = None
    best_model: str | None = None
    forecast_status: str | None = None
    months_since_last_sale: float | None = None
    dead_stock: bool | None = None
    dead_stock_reason: str | None = None

    analogue_count: int | None = None
    analogue_products: list[str] | None = None
    analogue_details: list[dict[str, Any]] | None = None
    analogue_history: list[dict[str, Any]] | None = None
    similar_products: list[dict[str, Any]] | None = None


class InventorySummary(BaseModel):
    total_products: int
    actions: dict[str, int]
    priorities: dict[str, int]


class ProductGroupMember(BaseModel):
    product_id: int
    template_id: int
    product_name: str | None
    is_main_similar: bool | None
    main_product_id: int | None
    main_product_template_id: int | None
    current_stock: float


class ProductGroupResponse(BaseModel):
    product_id: int
    template_id: int
    product_name: str | None
    main_product_id: int
    main_product_template_id: int
    main_product_name: str | None
    is_main_similar: bool | None
    group_members: list[ProductGroupMember]
    template_count: int
    variant_count: int
    group_size: int
    group_valid: bool
    validation_issues: list[str]
    validation_warnings: list[str]


class GroupDemandMonth(BaseModel):
    month: str
    actual: float


class GroupDemandHistoryResponse(BaseModel):
    main_product_template_id: int
    main_product_name: str | None
    months: list[GroupDemandMonth]
    total_demand: float
    months_with_demand: int


class GroupForecastStep(BaseModel):
    month: str
    forecast: float


class GroupForecastResponse(BaseModel):
    status: str
    forecast_scope: str
    main_product_template_id: int
    main_product_name: str | None
    group_size: int
    months_available: int
    history_start: str | None
    history_end: str | None
    next_month_forecast: float | None
    forecast_3_months: list[GroupForecastStep] | None = None
    best_model: str | None
    confidence: str | None
    mae: float | None
    wape: float | None
    mase: float | None
    avg_monthly_demand: float
    group_history: list[GroupDemandMonth]


class GroupRecommendationResponse(BaseModel):
    status: str
    recommendation_scope: str
    main_product_template_id: int
    main_product_name: str | None
    group_size: int
    group_valid: bool
    validation_issues: list[str]
    validation_warnings: list[str]
    group_current_stock: float
    group_next_month_forecast: float | None
    best_model: str | None
    confidence: str | None
    group_reorder_point: float | None
    group_buffered_target_stock: float | None
    group_stock_gap: float | None
    group_coverage_ratio: float | None
    group_suggested_purchase_qty: int
    action: str
    priority: str
    reason_codes: list[str]
    dead_stock: bool | None
    dead_stock_reason: str | None
    zero_purchase_explanation: str | None = None
    calculation_breakdown: dict[str, Any] | None = None


class PersistedGroupForecastResponse(BaseModel):
    id: int
    forecast_scope: str
    main_product_template_id: int
    main_product_name: str
    group_size: int
    months_available: int | None
    history_start: str | None
    history_end: str | None
    next_month_forecast: float | None
    forecast_3_months: list[GroupForecastStep] | None = None
    best_model: str | None
    confidence: str | None
    mae: float | None
    wape: float | None
    mase: float | None
    avg_monthly_demand: float | None
    forecast_status: str
    created_at: datetime
    updated_at: datetime


class PersistedGroupRecommendationResponse(BaseModel):
    id: int
    recommendation_scope: str
    main_product_template_id: int
    main_product_name: str
    group_size: int
    group_valid: bool
    group_current_stock: float | None
    group_next_month_forecast: float | None
    best_model: str | None
    confidence: str | None
    group_reorder_point: float | None
    group_buffered_target_stock: float | None
    group_stock_gap: float | None
    group_coverage_ratio: float | None
    group_suggested_purchase_qty: float
    action: str
    priority: str
    reason_codes: list[str]
    validation_issues: list[str]
    validation_warnings: list[str]
    dead_stock: bool | None
    dead_stock_reason: str | None
    recommendation_status: str
    forecast_status: str | None
    approval_status: Literal["pending", "approved", "rejected"]
    approval_updated_at: datetime | None
    zero_purchase_explanation: str | None = None
    calculation_breakdown: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class MainProductListItem(BaseModel):
    main_product_template_id: int
    main_product_name: str
    group_size: int
    group_valid: bool
    group_current_stock: float | None
    group_usable_qty: float | None = None
    group_cut_piece_qty: float | None = None
    group_forecasted_stock: float | None = None
    group_next_month_forecast: float | None
    best_model: str | None
    confidence: str | None
    group_reorder_point: float | None
    group_buffered_target_stock: float | None
    group_stock_gap: float | None
    group_suggested_purchase_qty: float
    action: str
    priority: str
    approval_status: Literal["pending", "approved", "rejected"]
    forecast_status: str
    recommendation_scope: str
    forecast_scope: str


class MainProductIdentity(BaseModel):
    template_id: int
    product_id: int | None = None
    name: str | None
    is_main_similar: bool | None
    current_stock: float | None
    usable_qty: float | None = None
    cut_piece_qty: float | None = None
    forecasted_stock: float | None = None
    incoming_qty: float | None = None
    outgoing_qty: float | None = None


class MainProductGroupMember(BaseModel):
    product_id: int
    template_id: int
    name: str | None
    is_main_similar: bool | None
    main_product_template_id: int | None
    current_stock: float
    usable_qty: float | None = None
    cut_piece_qty: float | None = None
    forecasted_stock: float | None = None
    incoming_qty: float | None = None
    outgoing_qty: float | None = None


class MainProductGroupDetail(BaseModel):
    group_valid: bool
    group_size: int
    validation_issues: list[str]
    validation_warnings: list[str]
    persisted_group_valid: bool
    persisted_validation_issues: list[str]
    persisted_validation_warnings: list[str]
    total_current_stock: float | None = None
    total_usable_qty: float | None = None
    total_cut_piece_qty: float | None = None
    total_forecasted_stock: float | None = None
    total_incoming_qty: float | None = None
    total_outgoing_qty: float | None = None
    members: list[MainProductGroupMember]


class MainProductDetailResponse(BaseModel):
    main_product: MainProductIdentity
    group: MainProductGroupDetail
    forecast: PersistedGroupForecastResponse
    recommendation: PersistedGroupRecommendationResponse


class CreateGroupPoRequest(BaseModel):
    quantity: float


class GroupPoResponse(BaseModel):
    po_number: str
    product_id: int
    product_name: str
    quantity: float
    status: str
    created_at: datetime | str | None = None