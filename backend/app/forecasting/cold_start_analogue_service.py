"""
Cold-Start Similar-Product Analogue Diagnostic Service.

Provides technical and lineage-based historical analogue diagnostics for product groups
with fewer than 6 months of usable history (N < 6).

All Odoo database access in this module is strictly READ-ONLY.
Analogue estimates are for cold-start diagnostic guidance only and do NOT replace
operational forecasts or alter Tasks 4–11 recommendation invariants.
"""

from __future__ import annotations

import math
from typing import Any, Sequence
import numpy as np
import pandas as pd
from sqlalchemy import text

from app.db.connection import get_odoo_engine


MIN_ANALOGUE_HISTORY_MONTHS = 6
DEFAULT_MAX_ANALOGUES = 5
MIN_EFFECTIVE_SIMILARITY_THRESHOLD = 0.30
CREDIBILITY_CONSTANT_K = 3.0  # Bayesian credibility smoothing constant for N=1..5


def _parse_gsm(val: Any) -> float | None:
    if val is None:
        return None
    s = str(val).strip()
    digits = "".join(ch for ch in s if ch.isdigit() or ch == ".")
    try:
        f = float(digits)
        return f if f > 0 else None
    except Exception:
        return None


def _normalize_text(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip().lower()
    return s if s else None


def compute_attribute_similarity(target: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """
    Computes a verified attribute similarity score and evidence coverage between a target
    cold-start product and a candidate historical analogue.

    Distinguishes:
    - raw_similarity_score: normalized over available attributes [0.0, 1.0]
    - evidence_coverage: fraction of standard attribute weights present and verified [0.0, 1.0]
    - effective_similarity_score: coverage-adjusted similarity score [0.0, 1.0]
    - matched_attribute_count: number of distinct attributes independently matched
    - matching_attributes, unmatched_attributes, missing_attributes
    - has_explicit_link / explicit lineage sources

    Does NOT invent missing attributes or silently treat missing values as matches.
    """
    score = 0.0
    available_weight = 0.0
    matching_attrs: dict[str, Any] = {}
    unmatched_attrs: list[str] = []
    missing_attrs: list[str] = []
    matched_count = 0

    # 1. Explicit Linkage (High confidence lineage signal)
    has_explicit_link = False
    link_sources = candidate.get("link_sources")
    if link_sources:
        has_explicit_link = True
        score += 0.35
        available_weight += 0.35
        matched_count += 1
        matching_attrs["link_sources"] = link_sources

    is_same_main = (
        target.get("main_product") is not None
        and candidate.get("main_product") is not None
        and target.get("main_product") == candidate.get("main_product")
        and target.get("main_product") != target.get("id")
    )
    if is_same_main:
        has_explicit_link = True
        score += 0.25
        available_weight += 0.25
        matched_count += 1
        matching_attrs["shared_main_product"] = target.get("main_product")

    # 2. Category Match (Weight: 0.25)
    t_cat, c_cat = target.get("categ_id"), candidate.get("categ_id")
    if t_cat is None or c_cat is None:
        missing_attrs.append("categ_id")
    else:
        available_weight += 0.25
        if t_cat == c_cat:
            score += 0.25
            matched_count += 1
            matching_attrs["categ_id"] = t_cat
        else:
            unmatched_attrs.append("categ_id")

    # 3. Brand Match (Weight: 0.15)
    t_brand, c_brand = target.get("brand_id"), candidate.get("brand_id")
    if t_brand is None or c_brand is None:
        missing_attrs.append("brand_id")
    else:
        available_weight += 0.15
        if t_brand == c_brand:
            score += 0.15
            matched_count += 1
            matching_attrs["brand_id"] = t_brand
        else:
            unmatched_attrs.append("brand_id")

    # 4. Composition Match (Weight: 0.15)
    t_comp, c_comp = _normalize_text(target.get("composition")), _normalize_text(candidate.get("composition"))
    if t_comp is None or c_comp is None:
        missing_attrs.append("composition")
    else:
        available_weight += 0.15
        if t_comp == c_comp:
            score += 0.15
            matched_count += 1
            matching_attrs["composition"] = target.get("composition")
        elif t_comp in c_comp or c_comp in t_comp:
            score += 0.10
            matched_count += 1
            matching_attrs["composition"] = {"target": target.get("composition"), "candidate": candidate.get("composition"), "partial_match": True}
        else:
            unmatched_attrs.append("composition")

    # 5. Quality Match (Weight: 0.10)
    t_qual, c_qual = _normalize_text(target.get("quality")), _normalize_text(candidate.get("quality"))
    if t_qual is None or c_qual is None:
        missing_attrs.append("quality")
    else:
        available_weight += 0.10
        if t_qual == c_qual:
            score += 0.10
            matched_count += 1
            matching_attrs["quality"] = target.get("quality")
        else:
            unmatched_attrs.append("quality")

    # 6. GSM Proximity (Weight: 0.05)
    t_gsm, c_gsm = _parse_gsm(target.get("gsm")), _parse_gsm(candidate.get("gsm"))
    if t_gsm is None or c_gsm is None:
        missing_attrs.append("gsm")
    else:
        available_weight += 0.05
        diff_pct = abs(t_gsm - c_gsm) / max(t_gsm, c_gsm)
        if diff_pct <= 0.25:
            gsm_contrib = 0.05 * (1.0 - diff_pct / 0.25)
            score += gsm_contrib
            matched_count += 1
            matching_attrs["gsm"] = {"target": t_gsm, "candidate": c_gsm, "proximity": round(1.0 - diff_pct, 2)}
        else:
            unmatched_attrs.append("gsm")

    # 7. Price Proximity (Weight: 0.05)
    try:
        t_price = float(target.get("list_price") or 0.0)
        c_price = float(candidate.get("list_price") or 0.0)
    except (ValueError, TypeError):
        t_price, c_price = 0.0, 0.0

    if t_price <= 0.0 or c_price <= 0.0:
        missing_attrs.append("list_price")
    else:
        available_weight += 0.05
        price_diff = abs(t_price - c_price) / max(t_price, c_price)
        if price_diff <= 0.35:
            price_contrib = 0.05 * (1.0 - price_diff / 0.35)
            score += price_contrib
            matched_count += 1
            matching_attrs["list_price"] = {"target": t_price, "candidate": c_price, "proximity": round(1.0 - price_diff, 2)}
        else:
            unmatched_attrs.append("list_price")

    # Standard total potential weight of all physical attributes
    # Physical attributes sum to 0.75 (categ: 0.25, brand: 0.15, comp: 0.15, quality: 0.10, gsm: 0.05, price: 0.05)
    # When explicit lineage links are evaluated, standard total potential benchmark is 1.00
    benchmark_denom = 1.0 if has_explicit_link else 0.75
    standard_denom = max(available_weight, benchmark_denom)
    
    raw_similarity = (score / available_weight) if available_weight > 0 else 0.0
    evidence_coverage = min(round(available_weight / benchmark_denom, 4), 1.0)
    
    # Effective similarity applies coverage dampening to prevent false 100% scores when sparse
    effective_similarity = min(round(score / standard_denom, 4), 1.0) if standard_denom > 0 else 0.0

    return {
        "similarity_score": effective_similarity,
        "raw_similarity_score": min(round(raw_similarity, 4), 1.0),
        "effective_similarity_score": effective_similarity,
        "evidence_coverage": evidence_coverage,
        "available_weight": round(available_weight, 4),
        "matched_attribute_count": matched_count,
        "has_explicit_link": has_explicit_link,
        "matching_attributes": matching_attrs,
        "unmatched_attributes": unmatched_attrs,
        "missing_attributes": missing_attrs,
    }


def get_cold_start_analogues(
    target_product_id: int,
    target_history_sales: pd.Series | Sequence[float] | None = None,
    max_analogues: int = DEFAULT_MAX_ANALOGUES,
    min_analogue_history: int = MIN_ANALOGUE_HISTORY_MONTHS,
) -> dict[str, Any]:
    """
    Identifies comparable historical products (with >= 6 months of sales history)
    for a cold-start product (N < 6 months), computes attribute similarity,
    and derives a diagnostic demand estimate.

    Does NOT mutate any database tables or alter operational recommendation invariants.
    """
    engine = get_odoo_engine()

    with engine.connect() as conn:
        # 1. Fetch Target Product Attributes
        target_q = text("""
            SELECT pt.id, pt.name->>'en_US' as name, pt.categ_id, pt.brand_id,
                   pt.quality, pt.composition, pt.gsm, pt.list_price, pt.main_product
            FROM product_template pt
            WHERE pt.id = :tid OR pt.id = (SELECT product_tmpl_id FROM product_product WHERE id = :tid LIMIT 1)
            LIMIT 1
        """)
        t_row = conn.execute(target_q, {"tid": target_product_id}).mappings().first()
        if not t_row:
            return {
                "status": "cold_start_target_not_found",
                "diagnostic_type": "cold_start_historical_analogue",
                "target_product_id": target_product_id,
                "candidate_count": 0,
                "analogue_candidates": [],
                "summary_analogue_estimate": None,
                "confidence": "very_low",
                "limitations": ["Target product template not found in database."],
            }

        target_dict = dict(t_row)
        actual_tid = target_dict["id"]
        target_name = target_dict["name"] or str(actual_tid)

        # 2. Fetch Explicit Linkages & Candidates with >= min_analogue_history months of sales
        candidates_q = text("""
            WITH sales_history AS (
                SELECT sol.main_product as template_id,
                       count(DISTINCT DATE_TRUNC('month', so.date_order))::int as selling_months,
                       sum(sol.product_uom_qty)::float as total_sales,
                       avg(sol.product_uom_qty)::float as avg_line_sales
                FROM sale_order_line sol
                JOIN sale_order so ON so.id = sol.order_id
                WHERE so.state = 'sale' AND sol.main_product IS NOT NULL
                GROUP BY sol.main_product
                HAVING count(DISTINCT DATE_TRUNC('month', so.date_order)) >= :min_m
            ),
            links AS (
                SELECT dest_id as related_tid, 'similar_relation' as source
                FROM product_template_similar_rel
                WHERE src_id = :tid
                UNION
                SELECT src_id as related_tid, 'similar_relation' as source
                FROM product_template_similar_rel
                WHERE dest_id = :tid
                UNION
                SELECT main_product as related_tid, 'main_product_lineage' as source
                FROM product_template
                WHERE id = :tid AND main_product IS NOT NULL AND main_product != :tid
            )
            SELECT pt.id, pt.name->>'en_US' as name, pt.categ_id, pt.brand_id,
                   pt.quality, pt.composition, pt.gsm, pt.list_price, pt.main_product,
                   sh.selling_months, sh.total_sales,
                   l.source as link_sources
            FROM product_template pt
            JOIN sales_history sh ON sh.template_id = pt.id
            LEFT JOIN links l ON l.related_tid = pt.id
            WHERE pt.id != :tid
              AND (
                  l.related_tid IS NOT NULL
                  OR pt.categ_id = :categ_id
                  OR (pt.brand_id IS NOT NULL AND pt.brand_id = :brand_id)
              )
            ORDER BY l.source IS NOT NULL DESC, sh.selling_months DESC
            LIMIT 50
        """)

        candidate_rows = conn.execute(
            candidates_q,
            {
                "tid": actual_tid,
                "min_m": min_analogue_history,
                "categ_id": target_dict.get("categ_id") or -1,
                "brand_id": target_dict.get("brand_id") or -1,
            },
        ).mappings().all()

    if not candidate_rows:
        return {
            "status": "cold_start_no_suitable_analogue",
            "diagnostic_type": "cold_start_historical_analogue",
            "target_product_id": actual_tid,
            "target_product_name": target_name,
            "candidate_count": 0,
            "analogue_candidates": [],
            "summary_analogue_estimate": None,
            "confidence": "very_low",
            "limitations": [
                "No candidate products with >= 6 months of sales history matched verified category or lineage attributes.",
                "Analogue estimation requires at least one verified historical peer with >= 6 selling months.",
            ],
        }

    # 3. Score and Rank Candidates
    scored_candidates: list[dict[str, Any]] = []
    own_sales = pd.Series(target_history_sales if target_history_sales is not None else [], dtype=float).reset_index(drop=True)
    own_n = len(own_sales)
    own_mean = float(own_sales.mean()) if own_n > 0 else 0.0

    for cand_row in candidate_rows:
        cand_dict = dict(cand_row)
        sim_res = compute_attribute_similarity(target_dict, cand_dict)
        eff_score = sim_res["effective_similarity_score"]
        has_link = sim_res["has_explicit_link"]
        matched_count = sim_res["matched_attribute_count"]

        # Minimum evidence threshold: explicit link OR (at least 2 attributes matched AND score >= 0.30)
        if not has_link and (matched_count < 2 or eff_score < MIN_EFFECTIVE_SIMILARITY_THRESHOLD):
            continue

        selling_m = int(cand_dict["selling_months"])
        tot_sales = float(cand_dict["total_sales"])
        cand_avg_d = tot_sales / max(1, selling_m)

        # Analogue demand signal preserves candidate mature volume level
        analogue_demand_signal = round(cand_avg_d, 2)

        scored_candidates.append(
            {
                "analogue_template_id": cand_dict["id"],
                "analogue_name": cand_dict["name"] or str(cand_dict["id"]),
                "similarity_score": eff_score,
                "raw_similarity_score": sim_res["raw_similarity_score"],
                "effective_similarity_score": eff_score,
                "evidence_coverage": sim_res["evidence_coverage"],
                "matched_attribute_count": matched_count,
                "has_explicit_link": has_link,
                "history_months": selling_m,
                "avg_monthly_demand": round(cand_avg_d, 2),
                "analogue_forecast_signal": analogue_demand_signal,
                "matching_attributes": sim_res["matching_attributes"],
                "unmatched_attributes": sim_res["unmatched_attributes"],
                "missing_attributes": sim_res["missing_attributes"],
            }
        )

    # Sort primarily by effective similarity score descending, secondarily by history months descending
    scored_candidates.sort(key=lambda x: (x["effective_similarity_score"], x["history_months"]), reverse=True)
    top_candidates = scored_candidates[:max_analogues]

    if not top_candidates:
        return {
            "status": "cold_start_no_suitable_analogue",
            "diagnostic_type": "cold_start_historical_analogue",
            "target_product_id": actual_tid,
            "target_product_name": target_name,
            "candidate_count": 0,
            "analogue_candidates": [],
            "summary_analogue_estimate": None,
            "confidence": "very_low",
            "limitations": [
                "Candidates were evaluated but none met the minimum verified similarity threshold (score >= 0.30 with >= 2 matching attributes).",
                "Missing or sparse product attributes prevented safe analogue matching.",
            ],
        }

    # Summary estimate derivation
    candidate_signals = [c["analogue_forecast_signal"] for c in top_candidates]
    analogue_prior_median = float(np.median(candidate_signals))

    # Bayesian Credibility Blending for N = 1..5:
    # z = N / (N + K) balances observed target data with the analogue prior
    if own_n == 0:
        summary_estimate = round(analogue_prior_median, 2)
        credibility_z = 0.0
    else:
        credibility_z = round(own_n / (own_n + CREDIBILITY_CONSTANT_K), 3)
        blended = (1.0 - credibility_z) * analogue_prior_median + credibility_z * own_mean
        summary_estimate = round(blended, 2)

    confidence = "low" if len(top_candidates) >= 2 and top_candidates[0]["effective_similarity_score"] >= 0.50 else "very_low"

    return {
        "status": "cold_start_analogue_available",
        "diagnostic_type": "cold_start_historical_analogue",
        "target_product_id": actual_tid,
        "target_product_name": target_name,
        "target_history_months": own_n,
        "target_observed_mean": round(own_mean, 2) if own_n > 0 else None,
        "analogue_prior_median": round(analogue_prior_median, 2),
        "credibility_weight_z": credibility_z,
        "candidate_count": len(top_candidates),
        "summary_analogue_estimate": summary_estimate,
        "confidence": confidence,
        "analogue_candidates": top_candidates,
        "limitations": [
            "Analogue estimates are for cold-start diagnostic guidance only and do NOT replace operational forecasts.",
            "Operational purchase recommendation remains review with status 'insufficient_group_history'.",
            "Analogue candidates are borrowed from historical peers with >= 6 months of sales data.",
            "Demand patterns may diverge based on new launch marketing, regional preferences, or seasonal shifts.",
        ],
    }
