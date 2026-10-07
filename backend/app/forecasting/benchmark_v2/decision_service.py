"""
End-to-End Inventory Decision Pipeline & Supplier Constraint Engine for Step 14.

Implements:
1. Exact Mathematical Transformation Flow:
   forecast_1m
   → forecast_h3 (3-month import lead-time demand)
   → safety_buffer (empirical service level)
   → target_stock (forecast_h3 + safety_buffer)
   → current_stock (max(0.0, stock_on_hand))
   → stock_position (net inventory available)
   → suggested_purchase (max(0.0, target_stock - current_stock))
2. Main-Product / Similar Product Group Inventory Absorption:
   Evaluates aggregate group stock across equivalent colorways/variants.
   If group stock >= group target, suppresses redundant single-variant purchasing.
3. Supplier Constraint Simulation:
   MOQ, standard roll length multiples (e.g. 50m), purchase UOM, lead time.
   Maintains strict separation between:
   - AI recommendation (pure mathematical need)
   - Planner-approved quantity
   - Supplier-constrained portal PO quantity
4. Exception Governance & Auditability:
   Emits structured planner exceptions for unresolved procurement conditions.
5. Strictly Read-Only with respect to Odoo: Zero writes, zero schema modifications, zero Odoo POs.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence
import numpy as np
import pandas as pd
from sqlalchemy import text, Engine

from app.db.connection import get_poc_engine
from .universal_engine import UniversalForecastingEngine, UniversalForecastResult


@dataclass(frozen=True)
class SupplierConstraints:
    """Supplier procurement constraints for a product or category."""
    vendor_id: int | None = None
    vendor_name: str | None = None
    moq: float = 100.0                # Minimum Order Quantity (e.g. 100m)
    standard_roll_length: float = 50.0  # Fabric roll multiple (e.g. 50m)
    purchase_uom: str = "m"           # Unit of Measure
    lead_time_days: int = 90          # Operational import lead time
    rounding_method: str = "ceil_roll"  # ceil_roll, ceil_moq, exact
    constraint_source: str = "DEFAULT_ASSUMPTION"  # ODOO_VENDOR_DATA, PORTAL_CONFIGURED, DEFAULT_ASSUMPTION, MISSING

    def apply(self, raw_quantity: float) -> tuple[float, list[str]]:
        """
        Applies supplier constraints to raw recommended purchase quantity.
        Zero purchase protection: Never turns 0 into positive purchase!
        Returns (constrained_quantity, list_of_reasons).
        """
        qty = max(0.0, float(raw_quantity or 0.0))
        if qty <= 0.0:
            return 0.0, []

        reasons = []
        # 1. Round up to standard fabric roll length multiple
        if self.standard_roll_length > 0:
            rolls = math.ceil(qty / self.standard_roll_length)
            roll_qty = round(rolls * self.standard_roll_length, 2)
            if roll_qty > qty:
                reasons.append(f"rounded_to_roll_length_multiple_{int(self.standard_roll_length)}m")
            qty = roll_qty

        # 2. Check Minimum Order Quantity (MOQ)
        if self.moq > 0 and qty < self.moq:
            reasons.append(f"adjusted_to_supplier_moq_{int(self.moq)}m")
            qty = float(self.moq)

        return qty, reasons


@dataclass(frozen=True)
class GroupInventoryEvaluation:
    """Canonical main-product / similar product group evaluation."""
    main_product_id: int | None
    is_grouped: bool
    group_size: int
    product_stock: float
    group_stock: float
    product_target: float
    group_target: float
    group_purchase_need: float
    group_stock_status: str         # standalone, group_stock_sufficient, group_partially_covered, all_understocked
    group_stock_absorbed: bool      # True if individual purchase was suppressed because group stock covers target
    substitutability_status: str    # clearly_interchangeable, operationally_substitutable, uncertain_substitutability, standalone
    group_notes: str | None


@dataclass(frozen=True)
class EndToEndDecisionResult:
    """Complete mathematical decision trace from forecast to portal PO."""
    product_id: int
    product_name: str
    category_id: str | None
    demand_pattern: str
    forecast_1m: float
    forecast_h3: float
    safety_buffer: float
    target_stock: float
    current_stock: float
    stock_position: float
    raw_purchase_need: float
    group_evaluation: GroupInventoryEvaluation
    suggested_purchase_ai: float
    supplier_constraints: SupplierConstraints
    constrained_purchase_qty: float
    constraint_multiplier: float
    constraint_adjustment_reasons: list[str]
    planner_exceptions: list[str]
    inbound_pending_qty: float
    is_ready_for_approval: bool

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["group_evaluation"] = asdict(self.group_evaluation)
        d["supplier_constraints"] = asdict(self.supplier_constraints)
        return d


class InventoryDecisionPipeline:
    """
    Executes end-to-end inventory decisions from forecast to supplier constraints.
    Enforces exact mathematical flow and transparent auditability.
    """

    def __init__(
        self,
        universal_engine: UniversalForecastingEngine | None = None,
        default_supplier_constraints: SupplierConstraints | None = None,
    ):
        self.engine = universal_engine or UniversalForecastingEngine()
        self.default_constraints = default_supplier_constraints or SupplierConstraints()

    def evaluate_product_decision(
        self,
        product_id: int,
        sales_series: Sequence[float] | pd.Series,
        current_stock: float = 0.0,
        product_name: str | None = None,
        category_id: str | None = None,
        group_members_stock: Mapping[int, float] | None = None,
        group_members_targets: Mapping[int, float] | None = None,
        main_product_id: int | None = None,
        supplier_constraints: SupplierConstraints | None = None,
        inbound_pending_qty: float = 0.0,
        substitutability_status: str | None = None,
        is_stockable: bool = True,
        product_type: str = "product",
    ) -> EndToEndDecisionResult:
        """
        Executes complete end-to-end mathematical decision for a product.
        """
        pid = int(product_id)
        pname = str(product_name or f"Product {pid}")
        cat_id = str(category_id) if category_id else None
        stock_val = max(0.0, float(current_stock or 0.0))
        constraints = supplier_constraints or self.default_constraints

        # 0. Service / Non-Inventory Item Exclusion (Step 18 Task 2)
        if not is_stockable or product_type in ("service", "consu") or cat_id in ("216", "Reward") or "gift card" in pname.lower():
            group_eval = GroupInventoryEvaluation(
                main_product_id=main_product_id,
                is_grouped=False,
                group_size=1,
                product_stock=stock_val,
                group_stock=stock_val,
                product_target=0.0,
                group_target=0.0,
                group_purchase_need=0.0,
                group_stock_status="standalone",
                group_stock_absorbed=False,
                substitutability_status="standalone",
                group_notes="Service / non-inventory item excluded from physical replenishment.",
            )
            return EndToEndDecisionResult(
                product_id=pid,
                product_name=pname,
                category_id=cat_id,
                demand_pattern="service_excluded",
                forecast_1m=0.0,
                forecast_h3=0.0,
                safety_buffer=0.0,
                target_stock=0.0,
                current_stock=stock_val,
                stock_position=stock_val,
                raw_purchase_need=0.0,
                group_evaluation=group_eval,
                suggested_purchase_ai=0.0,
                supplier_constraints=constraints,
                constrained_purchase_qty=0.0,
                constraint_multiplier=1.0,
                constraint_adjustment_reasons=[],
                planner_exceptions=["service_non_inventory_excluded"],
                inbound_pending_qty=inbound_pending_qty,
                is_ready_for_approval=False,
            )

        # 1. Step 1-3: Universal Forecast & Calibration
        fc_res: UniversalForecastResult = self.engine.forecast_product(
            product_id=pid,
            series=sales_series,
            current_stock=stock_val,
            product_name=pname,
            category_id=cat_id,
        )

        fc_1m = fc_res.forecast_1m
        fc_h3 = fc_res.forecast_h3
        safety_buf = fc_res.safety_buffer
        tgt_stock = fc_res.target_stock
        stock_pos = stock_val
        raw_need = max(0.0, round(tgt_stock - stock_pos, 2))

        # 2. Main-Product / Similar Product Group Evaluation (Task 5 & 6)
        grp_stock_map = dict(group_members_stock or {})
        grp_tgt_map = dict(group_members_targets or {})
        is_grouped = (main_product_id is not None and len(grp_stock_map) > 1)

        group_stock_absorbed = False
        group_notes = None
        sub_status = substitutability_status or ("operationally_substitutable" if is_grouped else "standalone")

        if is_grouped:
            group_size = len(grp_stock_map)
            total_group_stock = float(sum(grp_stock_map.values()))
            total_group_target = float(sum(grp_tgt_map.values())) if grp_tgt_map else tgt_stock
            group_need = max(0.0, round(total_group_target - total_group_stock, 2))

            if raw_need > 0 and total_group_stock >= total_group_target:
                # Individual variant understocked, but aggregate group stock covers target!
                group_stock_status = "group_stock_sufficient"
                group_stock_absorbed = True
                ai_suggested_buy = 0.0
                group_notes = f"Reorder suppressed: variant needs {raw_need}m, but group has {total_group_stock:.1f}m stock covering group target ({total_group_target:.1f}m)."
            elif raw_need > 0 and total_group_stock > stock_val:
                group_stock_status = "group_partially_covered"
                # Scale buy need to not exceed net group deficiency
                ai_suggested_buy = min(raw_need, group_need)
                group_notes = f"Partially absorbed by group stock: adjusted from {raw_need}m to {ai_suggested_buy}m."
            elif total_group_stock < total_group_target:
                group_stock_status = "all_understocked"
                ai_suggested_buy = raw_need
            else:
                group_stock_status = "group_stock_sufficient"
                ai_suggested_buy = 0.0
        else:
            group_size = 1
            total_group_stock = stock_val
            total_group_target = tgt_stock
            group_need = raw_need
            group_stock_status = "standalone"
            ai_suggested_buy = raw_need

        # 3. Dead Stock Hard Clamping Invariant
        if fc_res.demand_pattern == "dead_stock":
            ai_suggested_buy = 0.0

        # 4. Supplier Constraint Simulation (Step 15 Task 9)
        constrained_buy, constraint_reasons = constraints.apply(ai_suggested_buy)

        # Multiplier Calculation
        if ai_suggested_buy > 0.0:
            constraint_multiplier = round(constrained_buy / ai_suggested_buy, 2)
        else:
            constraint_multiplier = 1.0

        # 5. Planner Exception Governance (Step 15 Task 10)
        planner_exceptions: list[str] = list(fc_res.diagnostic_flags)

        # Missing metadata
        if constraints.vendor_id is None:
            planner_exceptions.append("missing_supplier")
        if not constraints.purchase_uom:
            planner_exceptions.append("missing_uom")
        if constraints.lead_time_days <= 0:
            planner_exceptions.append("missing_lead_time")

        # Default constraint alerts
        if constraints.constraint_source == "DEFAULT_ASSUMPTION":
            if any("moq" in r for r in constraint_reasons):
                planner_exceptions.append("default_moq_used")
            if any("roll_length" in r for r in constraint_reasons):
                planner_exceptions.append("default_roll_length_used")

        # Multiplier inflation alerts
        if constraint_multiplier > 3.0:
            planner_exceptions.append("constraint_multiplier_gt_3x")
        elif constraint_multiplier > 2.0:
            planner_exceptions.append("constraint_multiplier_gt_2x")

        # Inbound PO conflict (Task 7)
        if inbound_pending_qty > 0.0:
            planner_exceptions.append("possible_inbound_stock_conflict")

        # Group absorption & substitutability (Task 5)
        if group_stock_absorbed:
            planner_exceptions.append("group_stock_available_elsewhere")
            if sub_status == "uncertain_substitutability":
                planner_exceptions.append("uncertain_group_substitutability")

        if constrained_buy > 300.0:
            planner_exceptions.append("unusually_large_purchase_quantity")
        if "stockout_suppressed_demand_risk" in fc_res.diagnostic_flags:
            planner_exceptions.append("stockout_suppressed_risk")
        if "recent_reactivation_candidate" in fc_res.diagnostic_flags:
            planner_exceptions.append("recent_reactivation_review")
        if "single_recent_sale_diagnostic" in fc_res.diagnostic_flags:
            planner_exceptions.append("single_recent_sale_review")

        # Ready for approval gating: missing mandatory metadata blocks automatic approval
        blocking_errors = {"missing_supplier", "missing_uom", "missing_lead_time"}
        is_ready = not bool(blocking_errors.intersection(planner_exceptions))

        group_eval = GroupInventoryEvaluation(
            main_product_id=main_product_id,
            is_grouped=is_grouped,
            group_size=group_size,
            product_stock=stock_val,
            group_stock=total_group_stock,
            product_target=tgt_stock,
            group_target=total_group_target,
            group_purchase_need=group_need,
            group_stock_status=group_stock_status,
            group_stock_absorbed=group_stock_absorbed,
            substitutability_status=sub_status,
            group_notes=group_notes,
        )

        return EndToEndDecisionResult(
            product_id=pid,
            product_name=pname,
            category_id=cat_id,
            demand_pattern=fc_res.demand_pattern,
            forecast_1m=fc_1m,
            forecast_h3=fc_h3,
            safety_buffer=safety_buf,
            target_stock=tgt_stock,
            current_stock=stock_val,
            stock_position=stock_pos,
            raw_purchase_need=raw_need,
            group_evaluation=group_eval,
            suggested_purchase_ai=ai_suggested_buy,
            supplier_constraints=constraints,
            constrained_purchase_qty=constrained_buy,
            constraint_multiplier=constraint_multiplier,
            constraint_adjustment_reasons=constraint_reasons,
            planner_exceptions=planner_exceptions,
            inbound_pending_qty=inbound_pending_qty,
            is_ready_for_approval=is_ready,
        )
