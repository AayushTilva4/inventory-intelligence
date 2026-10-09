"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AppLayout, { sanitizeErrorMessage } from "@/components/AppLayout";
import { usePlanningRun } from "@/components/PlanningRunContext";
import MonthlyDemandChart, { GroupHistoryPoint } from "@/components/MonthlyDemandChart";
import StockCompositionBar from "@/components/StockCompositionBar";

type MainProductListItem = {
  main_product_template_id: number;
  main_product_name: string;
  group_size: number;
  group_valid: boolean;
  group_current_stock: number | null;
  group_usable_qty?: number | null;
  group_cut_piece_qty?: number | null;
  group_forecasted_stock?: number | null;
  group_next_month_forecast: number | null;
  best_model: string | null;
  confidence: string | null;
  group_reorder_point: number | null;
  group_buffered_target_stock: number | null;
  group_stock_gap: number | null;
  group_suggested_purchase_qty: number;
  action: string;
  priority: string;
  approval_status: "pending" | "approved" | "rejected";
  forecast_status: string;
  recommendation_scope: string;
  forecast_scope: string;
};

type MainProductMember = {
  product_id: number;
  template_id: number;
  name: string | null;
  is_main_similar: boolean | null;
  main_product_template_id: number | null;
  current_stock: number;
  usable_qty?: number | null;
  cut_piece_qty?: number | null;
  forecasted_stock?: number | null;
  incoming_qty?: number | null;
  outgoing_qty?: number | null;
};

type ForecastStep = {
  month: string;
  forecast: number;
};

type CalculationBreakdown = {
  forecast_breakdown?: {
    lead_time_months?: number;
    review_period_months?: number;
    forecast_horizon_months?: number;
    monthly_forecasts?: number[];
    monthly_forecast?: number;
    lead_time_demand?: number;
    review_period_demand?: number;
    forecasted_horizon_demand?: number;
    best_model?: string;
    selected_model?: string;
    model_selection_reason?: string;
    selection_reason?: string;
    usable_history_months?: number;
    usable_observations?: number;
    history_months?: number;
    confidence?: string;
    wape?: number;
    mase?: number;
    rmse?: number;
    forecast_warnings?: string[];
  };
  safety_stock_breakdown?: {
    safety_stock_method?: string;
    service_level?: number;
    z_score?: number;
    sigma_error_1m?: number;
    sigma_horizon?: number;
    raw_safety_stock?: number;
    cap_applied?: boolean;
    cap_value?: number;
    safety_stock?: number;
    final_safety_stock?: number;
    horizon_scale_factor?: number;
    operational_horizon_months?: number;
    dead_stock_safeguard?: boolean;
    lead_time_months?: number;
    review_period_months?: number;
  };
  inventory_position_breakdown?: {
    stock_on_hand?: number;
    usable_stock?: number;
    cut_piece_stock?: number;
    cut_piece_stock_excluded?: number;
    incoming_stock?: number;
    committed_stock?: number;
    inventory_position?: number;
    formula?: string;
  };
  target_and_purchase_breakdown?: {
    lead_time_demand?: number;
    review_period_demand?: number;
    forecasted_horizon_demand?: number;
    safety_stock?: number;
    target_stock?: number;
    buffered_target_stock?: number;
    inventory_position?: number;
    stock_gap?: number;
    suggested_purchase_qty?: number;
  };
  zero_purchase_explanation?: string;
};

type MainProductDetail = {
  main_product: {
    template_id: number;
    product_id?: number | null;
    name: string | null;
    is_main_similar: boolean | null;
    current_stock: number | null;
    usable_qty?: number | null;
    cut_piece_qty?: number | null;
    forecasted_stock?: number | null;
    incoming_qty?: number | null;
    outgoing_qty?: number | null;
  };
  group: {
    group_valid: boolean;
    group_size: number;
    validation_issues: string[];
    validation_warnings: string[];
    persisted_group_valid: boolean;
    persisted_validation_issues: string[];
    persisted_validation_warnings: string[];
    total_current_stock?: number | null;
    total_usable_qty?: number | null;
    total_cut_piece_qty?: number | null;
    total_forecasted_stock?: number | null;
    total_incoming_qty?: number | null;
    total_outgoing_qty?: number | null;
    members: MainProductMember[];
  };
  forecast: {
    forecast_scope: string;
    main_product_template_id: number;
    main_product_name: string;
    group_size: number;
    months_available: number | null;
    history_start: string | null;
    history_end: string | null;
    next_month_forecast: number | null;
    forecast_3_months?: ForecastStep[];
    best_model: string | null;
    confidence: string | null;
    mae: number | null;
    wape: number | null;
    mase: number | null;
    avg_monthly_demand: number | null;
    forecast_status: string;
  };
  recommendation: {
    recommendation_scope: string;
    main_product_template_id: number;
    main_product_name: string;
    group_size: number;
    group_valid: boolean;
    group_current_stock: number | null;
    group_forecasted_stock?: number | null;
    group_next_month_forecast: number | null;
    group_lead_time_demand?: number | null;
    group_review_period_demand?: number | null;
    group_forecasted_horizon_demand?: number | null;
    best_model: string | null;
    confidence: string | null;
    group_reorder_point: number | null;
    group_buffered_target_stock: number | null;
    group_stock_gap: number | null;
    group_coverage_ratio: number | null;
    group_suggested_purchase_qty: number;
    action: string;
    priority: string;
    reason_codes: string[];
    validation_issues: string[];
    validation_warnings: string[];
    dead_stock?: boolean | null;
    dead_stock_reason?: string | null;
    forecast_status?: string | null;
    recommendation_status: string;
    approval_status: "pending" | "approved" | "rejected";
    zero_purchase_explanation?: string | null;
    calculation_breakdown?: CalculationBreakdown | null;
  };
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

function formatNumber(value: number | null | undefined, maxFrac = 1) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: maxFrac }).format(value);
}

function actionBadge(action: string) {
  switch (action) {
    case "purchase":
      return "bg-blue-50 text-blue-700 border-blue-200";
    case "review":
      return "bg-amber-50 text-amber-800 border-amber-200";
    case "excess_stock":
      return "bg-purple-50 text-purple-700 border-purple-200";
    case "dead_stock":
      return "bg-rose-50 text-rose-700 border-rose-200";
    case "hold":
    default:
      return "bg-emerald-50 text-emerald-700 border-emerald-200";
  }
}

function actionLabel(action: string) {
  switch (action) {
    case "purchase":
      return "Needs Purchase";
    case "review":
      return "Review Required";
    case "excess_stock":
      return "Excess Stock";
    case "dead_stock":
      return "Dead Stock";
    case "hold":
    default:
      return "Stock Sufficient";
  }
}

export default function MainProductsPage() {
  const { activeEffectiveRun, effectiveRunId } = usePlanningRun();

  const [groups, setGroups] = useState<MainProductListItem[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState("");

  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null);
  const [detail, setDetail] = useState<MainProductDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [groupHistory, setGroupHistory] = useState<GroupHistoryPoint[]>([]);
  const [groupHistoryLoading, setGroupHistoryLoading] = useState(false);
  const [techDetailsExpanded, setTechDetailsExpanded] = useState(false);

  // Search with debounce
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<string>("priority");
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  const requestId = useRef(0);

  // Lock body scroll when modal is open
  useEffect(() => {
    if (selectedTemplateId !== null) {
      const originalOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = originalOverflow;
      };
    }
  }, [selectedTemplateId]);

  // Debounce search input (250ms)
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedSearch(searchInput);
      setCurrentPage(1);
    }, 250);
    return () => clearTimeout(handler);
  }, [searchInput]);

  const loadGroups = useCallback(async () => {
    const token = sessionStorage.getItem("auth_token");
    if (!token) return;

    try {
      setListLoading(true);
      setListError("");

      const queryParam = effectiveRunId ? `?run_id=${encodeURIComponent(effectiveRunId)}` : "";
      const res = await fetch(`${API_BASE}/api/main-products${queryParam}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) {
        if (res.status === 404 && activeEffectiveRun?.is_pruned) {
          setGroups([]);
          setListLoading(false);
          return;
        }
        throw new Error(`Failed to load product groups (HTTP ${res.status})`);
      }

      const data: MainProductListItem[] = await res.json();
      setGroups(Array.isArray(data) ? data : []);
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Unable to load product groups");
    } finally {
      setListLoading(false);
    }
  }, [effectiveRunId, activeEffectiveRun]);

  useEffect(() => {
    loadGroups();
  }, [loadGroups]);

  // Filtered and Sorted Groups
  const filteredAndSortedGroups = useMemo(() => {
    let result = [...groups];

    if (activeFilter !== "all") {
      result = result.filter((g) => g.action === activeFilter);
    }

    if (debouncedSearch.trim()) {
      const q = debouncedSearch.toLowerCase().trim();
      result = result.filter(
        (g) =>
          g.main_product_name.toLowerCase().includes(q) ||
          String(g.main_product_template_id).includes(q)
      );
    }

    result.sort((a, b) => {
      if (sortBy === "suggested_qty") {
        return (b.group_suggested_purchase_qty || 0) - (a.group_suggested_purchase_qty || 0);
      }
      if (sortBy === "forecast") {
        return (b.group_next_month_forecast || 0) - (a.group_next_month_forecast || 0);
      }
      if (sortBy === "stock_gap") {
        return (b.group_stock_gap || 0) - (a.group_stock_gap || 0);
      }
      if (sortBy === "stock") {
        return (b.group_current_stock || 0) - (a.group_current_stock || 0);
      }
      if (sortBy === "name") {
        return a.main_product_name.localeCompare(b.main_product_name);
      }
      if (sortBy === "template_id") {
        return a.main_product_template_id - b.main_product_template_id;
      }
      // default: priority order
      const pOrder: Record<string, number> = { high: 0, medium: 1, low: 2 };
      const pa = pOrder[a.priority] ?? 3;
      const pb = pOrder[b.priority] ?? 3;
      if (pa !== pb) return pa - pb;
      return (b.group_suggested_purchase_qty || 0) - (a.group_suggested_purchase_qty || 0);
    });

    return result;
  }, [groups, activeFilter, debouncedSearch, sortBy]);

  const totalPages = Math.max(1, Math.ceil(filteredAndSortedGroups.length / pageSize));
  const paginatedGroups = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredAndSortedGroups.slice(start, start + pageSize);
  }, [filteredAndSortedGroups, currentPage, pageSize]);

  // Open Detail Panel
  const openDetail = useCallback(
    async (templateId: number) => {
      const currentRequest = ++requestId.current;
      setSelectedTemplateId(templateId);
      setDetailLoading(true);
      setDetailError("");
      setGroupHistory([]);
      setGroupHistoryLoading(true);
      setTechDetailsExpanded(false);

      const token = sessionStorage.getItem("auth_token");
      if (!token) return;

      const queryParam = effectiveRunId ? `?run_id=${encodeURIComponent(effectiveRunId)}` : "";

      // 1. Fetch main product detail
      fetch(`${API_BASE}/api/main-products/${templateId}${queryParam}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(async (res) => {
          if (!res.ok) {
            const body = await res.json().catch(() => ({}));
            throw new Error(body.detail || `Failed to load detail (HTTP ${res.status})`);
          }
          const data: MainProductDetail = await res.json();
          if (currentRequest === requestId.current) {
            setDetail(data);
            setDetailLoading(false);
          }
        })
        .catch((err) => {
          if (currentRequest === requestId.current) {
            setDetailLoading(false);
            setDetailError(err instanceof Error ? err.message : "Unable to load group detail");
          }
        });

      // 2. Fetch live demand history
      fetch(`${API_BASE}/api/products/${templateId}/group/history`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(async (res) => {
          if (!res.ok) throw new Error("History unavailable");
          const data = await res.json();
          const points: GroupHistoryPoint[] = Array.isArray(data)
            ? data
            : Array.isArray(data?.months)
            ? data.months
            : [];
          if (currentRequest === requestId.current) {
            setGroupHistory(points);
            setGroupHistoryLoading(false);
          }
        })
        .catch(() => {
          if (currentRequest === requestId.current) {
            setGroupHistoryLoading(false);
          }
        });
    },
    [effectiveRunId]
  );

  const closeDetail = useCallback(() => {
    requestId.current += 1;
    setSelectedTemplateId(null);
    setDetail(null);
    setDetailError("");
  }, []);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && selectedTemplateId !== null) {
        closeDetail();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedTemplateId, closeDetail]);

  const cb = detail?.recommendation.calculation_breakdown;

  // Determine whether group has insufficient history (<6 months)
  const isInsufficientHistory = useMemo(() => {
    if (!detail) return false;
    const months = detail.forecast.months_available;
    return (
      (months !== null && months !== undefined && months < 6) ||
      detail.forecast.forecast_status?.includes("insufficient") ||
      detail.recommendation.forecast_status?.includes("insufficient") ||
      detail.recommendation.recommendation_status?.includes("insufficient")
    );
  }, [detail]);

  const isColdStart = useMemo(() => {
    if (!detail) return false;
    return (
      isInsufficientHistory ||
      (detail.recommendation.action === "review" &&
        (detail.recommendation.best_model?.includes("analogue") ||
          detail.forecast.forecast_status?.includes("cold_start")))
    );
  }, [detail, isInsufficientHistory]);

  // Reconciled operational horizon & demand numbers
  const horizonMonths = cb?.safety_stock_breakdown?.operational_horizon_months ?? 4.0;
  const leadTimeDemand =
    cb?.target_and_purchase_breakdown?.lead_time_demand ??
    detail?.recommendation.group_lead_time_demand ??
    (detail?.recommendation.group_next_month_forecast !== null && detail?.recommendation.group_next_month_forecast !== undefined
      ? detail.recommendation.group_next_month_forecast * 3.0
      : null);
  const reviewPeriodDemand =
    cb?.target_and_purchase_breakdown?.review_period_demand ??
    detail?.recommendation.group_review_period_demand ??
    (detail?.recommendation.group_next_month_forecast !== null && detail?.recommendation.group_next_month_forecast !== undefined
      ? detail.recommendation.group_next_month_forecast * 1.0
      : null);
  const forecastedHorizonDemand =
    cb?.target_and_purchase_breakdown?.forecasted_horizon_demand ??
    cb?.forecast_breakdown?.forecasted_horizon_demand ??
    detail?.recommendation.group_forecasted_horizon_demand ??
    (leadTimeDemand !== null && reviewPeriodDemand !== null ? leadTimeDemand + reviewPeriodDemand : null);

  // Reconciled stock breakdown
  const totalPhysicalStock =
    detail?.group.total_current_stock ?? detail?.recommendation.group_current_stock ?? 0;
  const usableStock =
    cb?.inventory_position_breakdown?.usable_stock ??
    detail?.group.total_usable_qty ??
    totalPhysicalStock;
  const cutPiecesExcluded =
    cb?.inventory_position_breakdown?.cut_piece_stock_excluded ??
    detail?.group.total_cut_piece_qty ??
    0;
  const incomingStock =
    cb?.inventory_position_breakdown?.incoming_stock ??
    detail?.group.total_incoming_qty ??
    0;
  const committedStock =
    cb?.inventory_position_breakdown?.committed_stock ??
    detail?.group.total_outgoing_qty ??
    0;
  const netInventoryPosition =
    cb?.inventory_position_breakdown?.inventory_position ??
    (usableStock + incomingStock - committedStock);

  const targetStock =
    cb?.target_and_purchase_breakdown?.target_stock ??
    cb?.target_and_purchase_breakdown?.buffered_target_stock ??
    detail?.recommendation.group_buffered_target_stock;

  const stockGap =
    cb?.target_and_purchase_breakdown?.stock_gap ??
    detail?.recommendation.group_stock_gap;

  return (
    <AppLayout>
      <div className="space-y-5 max-w-7xl mx-auto">
        {/* Header & Controls Bar */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900">
              Main Product Groups Catalogue
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">
              Multi-member product group catalog with inventory positions, forecasts, and replenishment recommendations.
            </p>
          </div>

          {/* Search Input (Debounced) */}
          <div className="relative w-full md:w-72">
            <svg
              className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder="Search product name or ID..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="block w-full rounded-lg border border-slate-300 pl-9 pr-3 py-1.5 text-xs text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white"
            />
          </div>
        </div>

        {/* Improved Responsive Toolbar (No horizontal clipping, wrapping chips, robust flex pagination) */}
        <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-3 border-y border-slate-200 py-3 bg-white px-3.5 rounded-xl shadow-2xs">
          {/* Action Filter Chips: Wrap into multiple rows on small screens without scrollbars */}
          <div className="flex flex-wrap items-center gap-1.5">
            {[
              { id: "all", label: "All Groups", count: groups.length },
              {
                id: "purchase",
                label: "Needs Purchase",
                count: groups.filter((g) => g.action === "purchase").length,
              },
              {
                id: "review",
                label: "Review Required",
                count: groups.filter((g) => g.action === "review").length,
              },
              {
                id: "excess_stock",
                label: "Excess Stock",
                count: groups.filter((g) => g.action === "excess_stock").length,
              },
              {
                id: "dead_stock",
                label: "Dead Stock",
                count: groups.filter((g) => g.action === "dead_stock").length,
              },
              {
                id: "hold",
                label: "Stock Sufficient",
                count: groups.filter((g) => g.action === "hold").length,
              },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveFilter(tab.id);
                  setCurrentPage(1);
                }}
                className={`whitespace-nowrap px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  activeFilter === tab.id
                    ? "bg-slate-900 text-white shadow-2xs"
                    : "bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200"
                }`}
              >
                {tab.label} ({tab.count})
              </button>
            ))}
          </div>

          {/* Sorting, Page Size, and Aligned Non-Wrapping Pagination */}
          <div className="flex flex-wrap items-center justify-between xl:justify-end gap-3 text-xs text-slate-600">
            <div className="flex items-center gap-1.5">
              <span className="text-slate-400">Sort:</span>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 font-medium focus:outline-none"
              >
                <option value="priority">Priority Order</option>
                <option value="suggested_qty">Suggested Purchase (High → Low)</option>
                <option value="forecast">1M Forecast (High → Low)</option>
                <option value="stock_gap">Stock Gap (High → Low)</option>
                <option value="stock">Current Stock (High → Low)</option>
                <option value="name">Product Name (A → Z)</option>
                <option value="template_id">Template ID</option>
              </select>
            </div>

            <div className="flex items-center gap-1.5">
              <span className="text-slate-400">Rows:</span>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setCurrentPage(1);
                }}
                className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 font-medium focus:outline-none"
              >
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </div>

            {/* Pagination Controls with whitespace-nowrap protection */}
            <div className="flex items-center gap-1.5 whitespace-nowrap">
              <span className="font-medium text-slate-500 whitespace-nowrap">
                {filteredAndSortedGroups.length === 0
                  ? "0 groups"
                  : `${(currentPage - 1) * pageSize + 1}–${Math.min(
                      currentPage * pageSize,
                      filteredAndSortedGroups.length
                    )} of ${filteredAndSortedGroups.length}`}
              </span>
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="px-2 py-1 rounded-md border border-slate-300 bg-white font-medium hover:bg-slate-50 disabled:opacity-40 transition-colors"
                aria-label="Previous Page"
              >
                ←
              </button>
              <span className="px-1.5 font-bold text-slate-900 whitespace-nowrap">
                {currentPage}/{totalPages}
              </span>
              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage >= totalPages}
                className="px-2 py-1 rounded-md border border-slate-300 bg-white font-medium hover:bg-slate-50 disabled:opacity-40 transition-colors"
                aria-label="Next Page"
              >
                →
              </button>
            </div>
          </div>
        </div>

        {/* Content Body: Responsive Scannable Table */}
        {listLoading ? (
          <div className="flex min-h-64 items-center justify-center rounded-xl border border-slate-200 bg-white">
            <div className="h-7 w-7 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
          </div>
        ) : listError ? (
          <section className="rounded-xl border border-rose-200 bg-white p-8 text-center">
            <h3 className="font-semibold text-slate-900">Could not load main products</h3>
            <p className="mt-2 text-sm text-rose-700">{listError}</p>
            <button
              onClick={loadGroups}
              className="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800"
            >
              Retry
            </button>
          </section>
        ) : filteredAndSortedGroups.length === 0 ? (
          <section className="rounded-xl border border-slate-200 bg-white px-6 py-16 text-center">
            <h3 className="font-semibold text-slate-900">
              {activeEffectiveRun?.status === "failed"
                ? "Planning Run Failed"
                : "No matching product groups found"}
            </h3>
            <p className="mt-2 text-sm text-slate-500">
              {activeEffectiveRun?.is_pruned
                ? "This planning run's snapshot records have been pruned by retention policy."
                : activeEffectiveRun?.status === "failed"
                ? `This planning run failed during execution (${sanitizeErrorMessage(activeEffectiveRun.error_message)}). No group intelligence snapshots were generated.`
                : "Try adjusting your search query or filter criteria."}
            </p>
          </section>
        ) : (
          <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-2xs">
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead className="bg-slate-50 text-left text-slate-500 font-semibold border-b border-slate-200">
                  <tr>
                    <th className="px-5 py-3">Product Group</th>
                    <th className="px-3 py-3">Decision</th>
                    <th className="px-3 py-3 text-right">1M Forecast</th>
                    <th className="px-3 py-3 text-right">Usable Stock</th>
                    <th className="px-3 py-3 text-right">Target Stock</th>
                    <th className="px-4 py-3 text-right">Suggested Purchase</th>
                    <th className="px-3 py-3 text-center">Priority</th>
                    <th className="px-4 py-3 text-right">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {paginatedGroups.map((group) => {
                    const rowInsufficient =
                      group.forecast_status?.includes("insufficient") ||
                      (group.group_next_month_forecast === null && group.action === "review");
                    const hasPurchase = group.group_suggested_purchase_qty > 0;
                    const usableVal = group.group_usable_qty ?? group.group_current_stock ?? 0;
                    const cutVal = group.group_cut_piece_qty ?? 0;

                    return (
                      <tr
                        key={group.main_product_template_id}
                        onClick={() => void openDetail(group.main_product_template_id)}
                        className="hover:bg-slate-50/80 cursor-pointer transition-colors group"
                      >
                        <td className="px-5 py-3">
                          <div className="font-semibold text-slate-900 group-hover:text-blue-700 transition-colors">
                            {group.main_product_name}
                          </div>
                          <div className="flex items-center gap-1.5 mt-0.5 text-[11px] text-slate-400">
                            <span className="font-mono">ID {group.main_product_template_id}</span>
                            <span>·</span>
                            <span>{group.group_size} member{group.group_size === 1 ? "" : "s"}</span>
                          </div>
                        </td>

                        <td className="px-3 py-3">
                          <span
                            className={`inline-flex px-2 py-0.5 rounded text-[11px] font-bold border ${actionBadge(
                              group.action
                            )}`}
                          >
                            {actionLabel(group.action)}
                          </span>
                        </td>

                        {/* 1M Forecast: Correctly displays 'Not calculated' for insufficient history */}
                        <td className="px-3 py-3 text-right font-semibold">
                          {rowInsufficient ? (
                            <span
                              className="text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded text-[10px] font-semibold border border-amber-200"
                              title="Insufficient sales history (<6 months); operational forecast not calculated"
                            >
                              Not calculated
                            </span>
                          ) : (
                            <span className="text-slate-900">
                              {formatNumber(group.group_next_month_forecast)} units
                            </span>
                          )}
                        </td>

                        <td className="px-3 py-3 text-right font-medium text-slate-800">
                          <div>{formatNumber(usableVal)} units</div>
                          {cutVal > 0 && (
                            <div className="text-[10px] text-slate-400 font-normal">
                              +{formatNumber(cutVal)} cut
                            </div>
                          )}
                        </td>

                        {/* Target Stock: Displays 'Not calculated' for insufficient history */}
                        <td className="px-3 py-3 text-right text-slate-700 font-medium">
                          {rowInsufficient || group.group_buffered_target_stock === null ? (
                            <span className="text-slate-400 text-[11px]">Not calculated</span>
                          ) : (
                            `${formatNumber(group.group_buffered_target_stock)} units`
                          )}
                        </td>

                        {/* Suggested Purchase: Shows safety hold indicator */}
                        <td className="px-4 py-3 text-right font-bold">
                          {hasPurchase ? (
                            <span className="text-blue-700 font-extrabold text-sm">
                              {formatNumber(group.group_suggested_purchase_qty)} units
                            </span>
                          ) : rowInsufficient ? (
                            <div>
                              <span className="text-slate-500 font-medium">0 units</span>
                              <div className="text-[10px] text-amber-700 font-semibold">Safety Hold</div>
                            </div>
                          ) : (
                            <span className="text-slate-400 font-normal">0 units</span>
                          )}
                        </td>

                        <td className="px-3 py-3 text-center">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${
                              group.priority === "high"
                                ? "bg-rose-50 text-rose-700 border border-rose-200"
                                : group.priority === "medium"
                                ? "bg-amber-50 text-amber-700 border border-amber-200"
                                : "bg-slate-100 text-slate-600 border border-slate-200"
                            }`}
                          >
                            {group.priority}
                          </span>
                        </td>

                        <td className="px-4 py-3 text-right">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              void openDetail(group.main_product_template_id);
                            }}
                            className="rounded-lg px-2.5 py-1 text-xs font-semibold text-blue-700 hover:bg-blue-50 border border-blue-200 transition-colors shadow-2xs"
                          >
                            Inspect →
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Group Detail Modal: Decision-First Plain Language Structure */}
        {selectedTemplateId !== null && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-slate-900/50 backdrop-blur-xs overflow-y-auto"
            onClick={closeDetail}
          >
            <div
              className="relative w-full max-w-3xl max-h-[92vh] bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Modal Header */}
              <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 bg-slate-50 shrink-0">
                <div className="min-w-0 flex-1 pr-4">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs px-2 py-0.5 rounded bg-blue-100 text-blue-800 font-bold border border-blue-200">
                      Template ID {selectedTemplateId}
                    </span>
                    <span className="text-xs text-slate-500">
                      {detail?.group.members.length || 0} Products in Group Pool
                    </span>
                  </div>
                  <h2 className="text-base font-bold text-slate-900 truncate mt-1">
                    {detail?.main_product.name || "Loading product group..."}
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={closeDetail}
                  className="rounded-lg p-2 text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition-colors shrink-0"
                  aria-label="Close modal"
                >
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              {/* Modal Body */}
              <div className="overflow-y-auto p-6 space-y-6 flex-1">
                {detailLoading ? (
                  <div className="flex min-h-48 items-center justify-center">
                    <div className="h-7 w-7 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
                  </div>
                ) : detailError ? (
                  <div className="p-4 rounded-xl bg-rose-50 text-rose-700 text-sm border border-rose-200">
                    {detailError}
                  </div>
                ) : detail ? (
                  <>
                    {/* Cold-Start / Insufficient History Advisory Banner */}
                    {isColdStart && (
                      <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-xs text-amber-900 space-y-1">
                        <div className="flex items-center gap-2 font-bold text-sm text-amber-950">
                          <span className="rounded bg-amber-200 px-2 py-0.5 text-[11px] uppercase tracking-wider font-extrabold text-amber-900 border border-amber-300">
                            Advisory only
                          </span>
                          <span>Insufficient History / Cold-Start Safety Safeguard</span>
                        </div>
                        <p className="leading-relaxed">
                          This product group has fewer than 6 usable months of sales history ({detail.forecast.months_available ?? 0} months recorded). Operational demand forecast, horizon demand, and target buffer are <strong>not calculated</strong>. Analogue information is provided solely for advisory guidance. Automated purchase is held at <strong>0 units</strong> as a protective safety restriction pending manual review—not proof that current inventory satisfies unknown future demand.
                        </p>
                      </div>
                    )}

                    {/* Section 1: Demand Forecast */}
                    <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
                      <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900">
                          1. Demand Forecast &amp; Planning Horizon
                        </h3>
                        <span className="text-xs text-slate-500 font-medium">
                          {isInsufficientHistory
                            ? "Horizon demand not calculated (insufficient history)"
                            : `${horizonMonths} Months Operational Horizon (3.0M Lead Time + 1.0M Review)`}
                        </span>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                        <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                          <span className="text-slate-400 text-[10px] block">Next-Month Forecast</span>
                          <span className="font-bold text-slate-900 text-sm">
                            {isInsufficientHistory || detail.recommendation.group_next_month_forecast === null
                              ? "Not calculated — insufficient history"
                              : `${formatNumber(detail.recommendation.group_next_month_forecast)} units`}
                          </span>
                        </div>
                        <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                          <span className="text-slate-400 text-[10px] block">Lead Time Demand (3M)</span>
                          <span className="font-semibold text-slate-900">
                            {isInsufficientHistory || leadTimeDemand === null
                              ? "Not calculated — insufficient history"
                              : `${formatNumber(leadTimeDemand)} units`}
                          </span>
                        </div>
                        <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                          <span className="text-slate-400 text-[10px] block">Review Period Demand (1M)</span>
                          <span className="font-semibold text-slate-900">
                            {isInsufficientHistory || reviewPeriodDemand === null
                              ? "Not calculated — insufficient history"
                              : `${formatNumber(reviewPeriodDemand)} units`}
                          </span>
                        </div>
                        <div className="p-2.5 rounded-lg bg-blue-50/60 border border-blue-200">
                          <span className="text-blue-600 text-[10px] block font-medium">Total Horizon Demand</span>
                          <span className="font-bold text-blue-700 text-sm">
                            {isInsufficientHistory || forecastedHorizonDemand === null
                              ? "Not calculated — insufficient history"
                              : `${formatNumber(forecastedHorizonDemand)} units`}
                          </span>
                        </div>
                      </div>

                      {!isInsufficientHistory && cb?.forecast_breakdown?.monthly_forecasts && (
                        <div className="flex items-center gap-2 pt-1 text-[11px] text-slate-500">
                          <span className="font-medium">Monthly Horizon Steps:</span>
                          <div className="flex items-center gap-1.5 font-mono">
                            {cb.forecast_breakdown.monthly_forecasts.map((f, i) => (
                              <span key={i} className="px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200">
                                M{i + 1}: {formatNumber(f)}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Section 2: Stock Composition Visualization (Stacked Bar + Signals) */}
                    <StockCompositionBar
                      totalPhysicalStock={totalPhysicalStock}
                      usableStock={usableStock}
                      cutPiecesExcluded={cutPiecesExcluded}
                      incomingStock={incomingStock}
                      committedStock={committedStock}
                      netPosition={netInventoryPosition}
                      unit="units"
                    />

                    {/* Section 3: Suggested Replenishment Calculation */}
                    <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
                      <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900">
                          3. Suggested Replenishment Calculation
                        </h3>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${actionBadge(detail.recommendation.action)}`}>
                          {actionLabel(detail.recommendation.action)}
                        </span>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                        <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                          <span className="text-slate-400 text-[10px] block">Target Stock Buffer</span>
                          <span className="font-bold text-slate-900 text-sm">
                            {isInsufficientHistory || targetStock === null || targetStock === undefined
                              ? "Not calculated — insufficient history"
                              : `${formatNumber(targetStock)} units`}
                          </span>
                          {!isInsufficientHistory && (
                            <span className="text-[10px] text-slate-500 mt-0.5 block">
                              Horizon ({formatNumber(forecastedHorizonDemand)}) + SS ({formatNumber(cb?.safety_stock_breakdown?.safety_stock || 0)})
                            </span>
                          )}
                        </div>
                        <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                          <span className="text-slate-400 text-[10px] block">Net Inventory Position</span>
                          <span className="font-semibold text-slate-900">
                            {formatNumber(netInventoryPosition)} units
                          </span>
                          <span className="text-[10px] text-slate-400 mt-0.5 block">(Usable + In) - Out</span>
                        </div>
                        <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                          <span className="text-slate-400 text-[10px] block">Stock Deficit (Gap)</span>
                          <span className="font-bold text-slate-900 text-sm">
                            {isInsufficientHistory || stockGap === null || stockGap === undefined
                              ? "Not calculated — insufficient history"
                              : `${formatNumber(stockGap)} units`}
                          </span>
                        </div>
                        <div className="p-2.5 rounded-lg bg-blue-50/80 border border-blue-300">
                          <span className="text-blue-700 text-[10px] font-bold block">Suggested Purchase</span>
                          <span className="font-extrabold text-blue-800 text-base">
                            {formatNumber(detail.recommendation.group_suggested_purchase_qty)} units
                          </span>
                          {isInsufficientHistory && (
                            <span className="text-[10px] text-amber-700 font-semibold mt-0.5 block">
                              Safety Hold: 0 units pending review
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Section 4: Why this action was recommended */}
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-2 text-xs">
                      <h3 className="font-bold uppercase tracking-wider text-slate-900 text-[11px]">
                        4. Recommendation Rationale
                      </h3>
                      <p className="text-slate-700 leading-relaxed">
                        {isInsufficientHistory ? (
                          `Advisory only: Short sales history (${detail.forecast.months_available ?? 0} usable months). Operational forecast, horizon demand, and target buffer cannot be reliably calculated. Suggested purchase is restricted to 0 units as a protective safety restriction pending human planner review, not evidence that current inventory satisfies unknown future demand.`
                        ) : cb?.zero_purchase_explanation ? (
                          cb.zero_purchase_explanation
                        ) : detail.recommendation.action === "purchase" ? (
                          `Net inventory position (${formatNumber(netInventoryPosition)}) is below the target buffer (${formatNumber(targetStock)}), creating a stock gap of ${formatNumber(stockGap)} units across the operational horizon.`
                        ) : (
                          `Net inventory position (${formatNumber(netInventoryPosition)}) covers the target stock (${formatNumber(targetStock)}). No immediate purchase is required.`
                        )}
                      </p>
                    </div>

                    {/* Section 5: Technical Details (Collapsed by default) */}
                    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
                      <button
                        type="button"
                        onClick={() => setTechDetailsExpanded(!techDetailsExpanded)}
                        className="w-full flex items-center justify-between px-4 py-3 bg-slate-50 hover:bg-slate-100 transition-colors text-left border-b border-slate-200"
                      >
                        <span className="text-xs font-bold text-slate-700">
                          5. Technical Calculation Details &amp; Formula Parameters
                        </span>
                        <span className="text-xs text-blue-700 font-medium">
                          {techDetailsExpanded ? "Hide Details ↑" : "Show Details ↓"}
                        </span>
                      </button>

                      {techDetailsExpanded && (
                        <div className="p-4 space-y-4 text-xs bg-slate-50/30">
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                            <div className="p-2 rounded bg-white border border-slate-200">
                              <span className="text-slate-400 text-[10px] block">Champion Model</span>
                              <span className="font-mono font-bold text-blue-700">
                                {detail.recommendation.best_model || (isInsufficientHistory ? "analogue_cold_start" : "trimmed_mean_3")}
                              </span>
                            </div>
                            <div className="p-2 rounded bg-white border border-slate-200">
                              <span className="text-slate-400 text-[10px] block">Model Confidence</span>
                              <span className="font-semibold text-slate-900 capitalize">
                                {detail.recommendation.confidence || (isInsufficientHistory ? "Low (Advisory Only)" : "Normal")}
                              </span>
                            </div>
                            <div className="p-2 rounded bg-white border border-slate-200">
                              <span className="text-slate-400 text-[10px] block">Service Level (Z-Score)</span>
                              <span className="font-semibold text-slate-900">
                                {cb?.safety_stock_breakdown?.service_level !== undefined && cb?.safety_stock_breakdown?.service_level !== null
                                  ? `${(cb.safety_stock_breakdown.service_level * 100).toFixed(0)}% (Z=${cb.safety_stock_breakdown.z_score})`
                                  : "—"}
                              </span>
                            </div>
                            <div className="p-2 rounded bg-white border border-slate-200">
                              <span className="text-slate-400 text-[10px] block">Forecast Error Sigma</span>
                              <span className="font-semibold text-slate-900">
                                σ = {cb?.safety_stock_breakdown?.sigma_error_1m !== undefined ? formatNumber(cb.safety_stock_breakdown.sigma_error_1m, 2) : "—"}
                              </span>
                            </div>
                            <div className="p-2 rounded bg-white border border-slate-200">
                              <span className="text-slate-400 text-[10px] block">Horizon Scale Factor</span>
                              <span className="font-semibold text-slate-900">
                                √({horizonMonths}M) = {cb?.safety_stock_breakdown?.horizon_scale_factor || 2.0}×
                              </span>
                            </div>
                            <div className="p-2 rounded bg-white border border-slate-200">
                              <span className="text-slate-400 text-[10px] block">Outlier Safety Cap</span>
                              <span className="font-semibold text-slate-900">
                                {cb?.safety_stock_breakdown?.cap_applied ? `Capped at ${cb.safety_stock_breakdown.cap_value}` : "Uncapped"}
                              </span>
                            </div>
                            <div className="p-2 rounded bg-white border border-slate-200">
                              <span className="text-slate-400 text-[10px] block">Safety Stock Method</span>
                              <span className="font-semibold text-slate-900 capitalize">
                                {cb?.safety_stock_breakdown?.safety_stock_method || "Dynamic Horizon"}
                              </span>
                            </div>
                            <div className="p-2 rounded bg-white border border-slate-200">
                              <span className="text-slate-400 text-[10px] block">Unbuffered Baseline</span>
                              <span className="font-semibold text-slate-900">
                                {formatNumber(detail.recommendation.group_reorder_point)}
                              </span>
                            </div>
                          </div>

                          {detail.recommendation.reason_codes && detail.recommendation.reason_codes.length > 0 && (
                            <div>
                              <span className="text-[10px] text-slate-400 block mb-1">Reason Codes</span>
                              <div className="flex flex-wrap gap-1 font-mono text-[10px]">
                                {detail.recommendation.reason_codes.map((code) => (
                                  <span key={code} className="px-1.5 py-0.5 rounded bg-slate-200 text-slate-700">
                                    {code}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Section 6: Responsive Vertical Bar Demand History Chart */}
                    <MonthlyDemandChart
                      history={groupHistory}
                      loading={groupHistoryLoading}
                      effectiveRunId={effectiveRunId}
                      unit="units"
                    />

                    {/* Section 7: Group Members Table */}
                    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-2xs">
                      <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
                        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900">
                          7. Group Product Members ({detail.group.members.length} Products)
                        </h3>
                        <span className="text-[11px] text-slate-500">Shared Stock Pool</span>
                      </div>

                      <div className="overflow-x-auto">
                        <table className="min-w-full text-xs">
                          <thead className="bg-slate-50 text-left text-slate-500 font-semibold border-b border-slate-200">
                            <tr>
                              <th className="px-4 py-2.5">Product ID &amp; Name</th>
                              <th className="px-3 py-2.5 text-right">Physical Stock</th>
                              <th className="px-3 py-2.5 text-right">Usable Qty</th>
                              <th className="px-3 py-2.5 text-right">Cut Pieces</th>
                              <th className="px-3 py-2.5 text-right">Incoming</th>
                              <th className="px-3 py-2.5 text-right">Committed</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {detail.group.members.map((m) => (
                              <tr key={m.product_id} className="hover:bg-slate-50 transition-colors">
                                <td className="px-4 py-2.5">
                                  <div className="font-semibold text-slate-900">{m.name || "Product"}</div>
                                  <span className="text-[10px] text-slate-400 font-mono">Product ID: {m.product_id}</span>
                                </td>
                                <td className="px-3 py-2.5 text-right font-bold text-slate-900">
                                  {formatNumber(m.current_stock)}
                                </td>
                                <td className="px-3 py-2.5 text-right font-medium text-emerald-700">
                                  {formatNumber(m.usable_qty)}
                                </td>
                                <td className="px-3 py-2.5 text-right text-rose-700">
                                  {formatNumber(m.cut_piece_qty)}
                                </td>
                                <td className="px-3 py-2.5 text-right text-slate-700">
                                  {formatNumber(m.incoming_qty)}
                                </td>
                                <td className="px-3 py-2.5 text-right text-slate-700">
                                  {formatNumber(m.outgoing_qty)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </>
                ) : null}
              </div>

              {/* Modal Footer */}
              <div className="flex items-center justify-end px-6 py-3 border-t border-slate-200 bg-slate-50 shrink-0">
                <button
                  type="button"
                  onClick={closeDetail}
                  className="px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs transition-colors shadow-2xs"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}