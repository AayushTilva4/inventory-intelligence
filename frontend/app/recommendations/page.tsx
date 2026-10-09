"use client";

import { useEffect, useState, useMemo, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
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
  forecast_status: string;
  recommendation_scope: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

function formatNumber(value: number | null | undefined, decimals = 1) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: decimals }).format(value);
}

function actionBadge(action: string) {
  switch (action) {
    case "purchase":
      return {
        label: "Needs Purchase",
        classes: "bg-blue-50 text-blue-700 border-blue-200",
      };
    case "review":
      return {
        label: "Review Required",
        classes: "bg-amber-50 text-amber-800 border-amber-200",
      };
    case "excess_stock":
      return {
        label: "Excess Stock",
        classes: "bg-purple-50 text-purple-700 border-purple-200",
      };
    case "dead_stock":
      return {
        label: "Dead Stock",
        classes: "bg-red-50 text-red-700 border-red-200",
      };
    case "hold":
    default:
      return {
        label: "Stock Sufficient",
        classes: "bg-slate-50 text-slate-700 border-slate-200",
      };
  }
}

function humanizeReason(item: MainProductListItem, cb?: any): string {
  if (cb?.zero_purchase_explanation) {
    return cb.zero_purchase_explanation;
  }
  switch (item.action) {
    case "purchase":
      if (item.group_stock_gap && item.group_stock_gap > 0) {
        return `Net stock is ${formatNumber(item.group_stock_gap)} below target buffer. Purchase required to protect service level.`;
      }
      return "Current inventory position is below target buffer. Replenishment recommended.";
    case "review":
      if (
        item.forecast_status?.includes("cold_start") ||
        item.forecast_status?.includes("insufficient") ||
        item.best_model?.includes("analogue")
      ) {
        return "Advisory only: short sales history (<6 months). Purchase restricted to 0 pending human planner review.";
      }
      return "Forecast uncertainty or model validation requires planner review.";
    case "excess_stock":
      return "Usable stock significantly exceeds target buffer. Reorder suppressed to prevent excess holding.";
    case "dead_stock":
      return "No recent sales demand observed. Stock is inactive; reorder suppressed.";
    case "hold":
    default:
      if (item.group_suggested_purchase_qty === 0) {
        return "Current usable stock satisfies target buffer. No replenishment needed this cycle.";
      }
      return "Order held pending review.";
  }
}

function RecommendationsContent() {
  const searchParams = useSearchParams();
  const initialTab = searchParams.get("tab") as any;

  const { activeEffectiveRun, effectiveRunId } = usePlanningRun();

  const [recommendations, setRecommendations] = useState<MainProductListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [activeTab, setActiveTab] = useState<
    "all" | "purchase" | "review" | "excess_stock" | "dead_stock" | "hold"
  >(
    initialTab && ["all", "purchase", "review", "excess_stock", "dead_stock", "hold"].includes(initialTab)
      ? initialTab
      : "all"
  );

  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [sortBy, setSortBy] = useState<string>("priority");
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(50);

  // Detail Modal State
  const [selectedGroup, setSelectedGroup] = useState<MainProductListItem | null>(null);
  const [groupDetailData, setGroupDetailData] = useState<any>(null);
  const [groupDetailLoading, setGroupDetailLoading] = useState(false);
  const [history, setHistory] = useState<GroupHistoryPoint[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Debounce search input (250ms)
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedSearch(searchQuery);
      setCurrentPage(1);
    }, 250);
    return () => clearTimeout(handler);
  }, [searchQuery]);

  // Lock body scroll when modal is open
  useEffect(() => {
    if (isModalOpen) {
      const originalOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = originalOverflow;
      };
    }
  }, [isModalOpen]);

  // Data fetching with AbortController to cancel stale requests on run change
  useEffect(() => {
    const token = sessionStorage.getItem("auth_token");
    if (!token) return;

    const controller = new AbortController();

    async function loadRecommendations() {
      try {
        setLoading(true);
        setError("");

        const queryParam = effectiveRunId ? `?run_id=${encodeURIComponent(effectiveRunId)}` : "";
        const res = await fetch(`${API_BASE}/api/main-products${queryParam}`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });

        if (!res.ok) {
          if (res.status === 404 && activeEffectiveRun?.is_pruned) {
            setRecommendations([]);
            setLoading(false);
            return;
          }
          throw new Error(`Failed to load recommendations (HTTP ${res.status})`);
        }

        const data: MainProductListItem[] = await res.json();
        setRecommendations(Array.isArray(data) ? data : []);
      } catch (err: any) {
        if (err.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "Unable to load recommendations");
      } finally {
        setLoading(false);
      }
    }

    loadRecommendations();

    return () => {
      controller.abort();
    };
  }, [effectiveRunId, activeEffectiveRun]);

  // Filtered & sorted recommendations
  const filteredAndSorted = useMemo(() => {
    let result = recommendations.filter((item) => {
      if (activeTab !== "all" && item.action !== activeTab) return false;
      if (debouncedSearch) {
        const q = debouncedSearch.toLowerCase().trim();
        const matchName = item.main_product_name?.toLowerCase().includes(q);
        const matchId = item.main_product_template_id.toString().includes(q);
        if (!matchName && !matchId) return false;
      }
      return true;
    });

    result.sort((a, b) => {
      if (sortBy === "priority") {
        const pRank: Record<string, number> = { high: 1, medium: 2, low: 3 };
        const pDiff = (pRank[a.priority] || 4) - (pRank[b.priority] || 4);
        if (pDiff !== 0) return pDiff;
        return (b.group_suggested_purchase_qty || 0) - (a.group_suggested_purchase_qty || 0);
      }
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
        return (b.group_usable_qty ?? b.group_current_stock ?? 0) - (a.group_usable_qty ?? a.group_current_stock ?? 0);
      }
      if (sortBy === "name") {
        return (a.main_product_name || "").localeCompare(b.main_product_name || "");
      }
      if (sortBy === "template_id") {
        return a.main_product_template_id - b.main_product_template_id;
      }
      return 0;
    });

    return result;
  }, [recommendations, activeTab, debouncedSearch, sortBy]);

  // Paginated recommendations
  const totalPages = Math.max(1, Math.ceil(filteredAndSorted.length / pageSize));
  const paginatedItems = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredAndSorted.slice(start, start + pageSize);
  }, [filteredAndSorted, currentPage, pageSize]);

  // Open product detail modal
  const handleOpenDetail = useCallback(
    async (item: MainProductListItem) => {
      setSelectedGroup(item);
      setIsModalOpen(true);
      setGroupDetailData(null);
      setGroupDetailLoading(true);
      setHistory([]);
      setHistoryLoading(true);

      const token = sessionStorage.getItem("auth_token");
      if (!token) return;

      const queryParam = effectiveRunId ? `?run_id=${encodeURIComponent(effectiveRunId)}` : "";

      // 1. Fetch group detail & calculation breakdown
      fetch(`${API_BASE}/api/main-products/${item.main_product_template_id}${queryParam}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(async (res) => {
          if (res.ok) {
            const d = await res.json();
            setGroupDetailData(d);
          }
        })
        .catch(() => {})
        .finally(() => {
          setGroupDetailLoading(false);
        });

      // 2. Fetch history
      fetch(`${API_BASE}/api/products/${item.main_product_template_id}/group/history`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(async (res) => {
          if (res.ok) {
            const histData = await res.json();
            const points: GroupHistoryPoint[] = Array.isArray(histData)
              ? histData
              : Array.isArray(histData?.months)
              ? histData.months
              : [];
            setHistory(points);
          }
        })
        .catch(() => {})
        .finally(() => {
          setHistoryLoading(false);
        });
    },
    [effectiveRunId]
  );

  const handleCloseModal = useCallback(() => {
    setIsModalOpen(false);
    setSelectedGroup(null);
    setGroupDetailData(null);
    setHistory([]);
  }, []);

  const cb = groupDetailData?.recommendation?.calculation_breakdown;
  const forecastData = groupDetailData?.forecast;

  // Determine insufficient history status (<6 months)
  const isInsufficientHistory = useMemo(() => {
    if (selectedGroup?.forecast_status?.includes("insufficient")) return true;
    if (forecastData?.months_available !== null && forecastData?.months_available !== undefined && forecastData.months_available < 6) return true;
    if (forecastData?.forecast_status?.includes("insufficient")) return true;
    return false;
  }, [selectedGroup, forecastData]);

  const isColdStart =
    isInsufficientHistory ||
    (selectedGroup?.action === "review" &&
      (selectedGroup.best_model?.includes("analogue") ||
        selectedGroup.forecast_status?.includes("cold_start")));

  // Calculation parameters for plain-language modal
  const leadTimeDemand =
    cb?.target_and_purchase_breakdown?.lead_time_demand ??
    (selectedGroup?.group_next_month_forecast !== null && selectedGroup?.group_next_month_forecast !== undefined
      ? selectedGroup.group_next_month_forecast * 3.0
      : null);
  const reviewPeriodDemand =
    cb?.target_and_purchase_breakdown?.review_period_demand ??
    (selectedGroup?.group_next_month_forecast !== null && selectedGroup?.group_next_month_forecast !== undefined
      ? selectedGroup.group_next_month_forecast * 1.0
      : null);
  const forecastedHorizonDemand =
    cb?.target_and_purchase_breakdown?.forecasted_horizon_demand ??
    (leadTimeDemand !== null && reviewPeriodDemand !== null ? leadTimeDemand + reviewPeriodDemand : null);
  const horizonMonths =
    cb?.safety_stock_breakdown?.operational_horizon_months ??
    cb?.forecast_breakdown?.forecast_horizon_months ??
    4.0;

  const totalPhysicalStock =
    cb?.inventory_position_breakdown?.stock_on_hand ??
    selectedGroup?.group_current_stock ??
    0;
  const usableStock =
    cb?.inventory_position_breakdown?.usable_stock ??
    selectedGroup?.group_usable_qty ??
    totalPhysicalStock;
  const cutPiecesExcluded =
    cb?.inventory_position_breakdown?.cut_piece_stock_excluded ??
    cb?.inventory_position_breakdown?.cut_piece_stock ??
    selectedGroup?.group_cut_piece_qty ??
    0;
  const incomingStock = cb?.inventory_position_breakdown?.incoming_stock ?? 0;
  const committedStock = cb?.inventory_position_breakdown?.committed_stock ?? 0;
  const inventoryPosition =
    cb?.inventory_position_breakdown?.inventory_position ??
    (usableStock + incomingStock - committedStock);

  const targetBufferedStock =
    cb?.target_and_purchase_breakdown?.buffered_target_stock ??
    cb?.target_and_purchase_breakdown?.target_stock ??
    selectedGroup?.group_buffered_target_stock;
  const stockGap =
    cb?.target_and_purchase_breakdown?.stock_gap ??
    selectedGroup?.group_stock_gap;
  const suggestedPurchase =
    cb?.target_and_purchase_breakdown?.suggested_purchase_qty ??
    selectedGroup?.group_suggested_purchase_qty ??
    0;

  return (
    <AppLayout>
      <div className="space-y-5 max-w-7xl mx-auto">
        {/* Header Bar */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900">
              Replenishment Recommendations
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">
              Actionable replenishment signals, target buffers, and plain-language rationales for {formatNumber(recommendations.length, 0)} product groups.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-slate-100 text-slate-700 border border-slate-200">
              Planning Run: <span className="font-mono text-blue-700 font-bold">{effectiveRunId || "latest"}</span>
            </span>
          </div>
        </div>

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Improved Responsive Toolbar (Wrapping filter chips, no scrollbar, whitespace-nowrap pagination) */}
        <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-3 border-y border-slate-200 py-3 bg-white px-3.5 rounded-xl shadow-2xs">
          {/* Action Filter Chips */}
          <div className="flex flex-wrap items-center gap-1.5">
            {[
              { id: "all", label: "All Groups", count: recommendations.length },
              {
                id: "purchase",
                label: "Needs Purchase",
                count: recommendations.filter((r) => r.action === "purchase").length,
              },
              {
                id: "review",
                label: "Review Required",
                count: recommendations.filter((r) => r.action === "review").length,
              },
              {
                id: "excess_stock",
                label: "Excess Stock",
                count: recommendations.filter((r) => r.action === "excess_stock").length,
              },
              {
                id: "dead_stock",
                label: "Dead Stock",
                count: recommendations.filter((r) => r.action === "dead_stock").length,
              },
              {
                id: "hold",
                label: "Stock Sufficient",
                count: recommendations.filter((r) => r.action === "hold").length,
              },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id as any);
                  setCurrentPage(1);
                }}
                className={`whitespace-nowrap px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  activeTab === tab.id
                    ? "bg-slate-900 text-white shadow-2xs"
                    : "bg-slate-50 text-slate-600 hover:bg-slate-100 border border-slate-200"
                }`}
              >
                {tab.label} ({tab.count})
              </button>
            ))}
          </div>

          {/* Search, Sort & Aligned Pagination */}
          <div className="flex flex-wrap items-center justify-between xl:justify-end gap-3 text-xs text-slate-600">
            {/* Search Input */}
            <div className="relative w-full sm:w-52">
              <svg
                className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input
                type="text"
                placeholder="Search name or ID..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="block w-full rounded-lg border border-slate-300 pl-8 pr-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white"
              />
            </div>

            <div className="flex items-center gap-1.5">
              <span className="text-slate-400">Sort:</span>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 font-medium focus:outline-none"
              >
                <option value="priority">Priority Order</option>
                <option value="suggested_qty">Suggested Purchase (High → Low)</option>
                <option value="stock_gap">Stock Gap (High → Low)</option>
                <option value="forecast">1M Forecast (High → Low)</option>
                <option value="stock">Usable Stock (High → Low)</option>
                <option value="name">Product Name (A → Z)</option>
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

            {/* Pagination Controls */}
            <div className="flex items-center gap-1.5 whitespace-nowrap">
              <span className="font-medium text-slate-500 whitespace-nowrap">
                {filteredAndSorted.length === 0
                  ? "0 groups"
                  : `${(currentPage - 1) * pageSize + 1}–${Math.min(
                      currentPage * pageSize,
                      filteredAndSorted.length
                    )} of ${filteredAndSorted.length}`}
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

        {/* Primary Recommendations Table */}
        <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-2xs">
          {loading ? (
            <div className="flex min-h-64 items-center justify-center">
              <div className="h-7 w-7 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
            </div>
          ) : filteredAndSorted.length === 0 ? (
            <div className="px-6 py-16 text-center">
              <p className="text-base font-semibold text-slate-900">
                {activeEffectiveRun?.status === "failed"
                  ? "Planning Run Failed"
                  : "No matching recommendations found"}
              </p>
              <p className="text-xs text-slate-500 mt-1">
                {activeEffectiveRun?.is_pruned
                  ? "This run's detailed snapshots were pruned by retention policy."
                  : activeEffectiveRun?.status === "failed"
                  ? `This planning run failed during execution (${sanitizeErrorMessage(activeEffectiveRun.error_message)}). No recommendation records were generated.`
                  : "Try clearing your search query or selecting a different filter tab."}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead className="bg-slate-50 text-left text-slate-500 font-semibold border-b border-slate-200">
                  <tr>
                    <th className="px-5 py-3">Product Group</th>
                    <th className="px-3 py-3">Action</th>
                    <th className="px-3 py-3 text-right">Usable Stock</th>
                    <th className="px-3 py-3 text-right">Target Buffer</th>
                    <th className="px-4 py-3 text-right">Suggested Purchase</th>
                    <th className="px-4 py-3">Business Rationale</th>
                    <th className="px-4 py-3 text-right">Breakdown</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {paginatedItems.map((item) => {
                    const badge = actionBadge(item.action);
                    const itemUsable = item.group_usable_qty ?? item.group_current_stock ?? 0;
                    const itemCut = item.group_cut_piece_qty ?? 0;
                    const rowInsufficient =
                      item.forecast_status?.includes("insufficient") ||
                      (item.group_next_month_forecast === null && item.action === "review");

                    return (
                      <tr
                        key={item.main_product_template_id}
                        onClick={() => handleOpenDetail(item)}
                        className="hover:bg-slate-50/80 cursor-pointer transition-colors group"
                      >
                        {/* Product Group & ID */}
                        <td className="px-5 py-3">
                          <div className="font-semibold text-slate-900 group-hover:text-blue-700 transition-colors">
                            {item.main_product_name}
                          </div>
                          <div className="flex items-center gap-1.5 mt-0.5 text-[11px] text-slate-400">
                            <span className="font-mono">ID {item.main_product_template_id}</span>
                            <span>·</span>
                            <span>{item.group_size} member{item.group_size === 1 ? "" : "s"}</span>
                          </div>
                        </td>

                        {/* Action Badge */}
                        <td className="px-3 py-3">
                          <span className={`inline-flex rounded-md border px-2 py-0.5 text-[11px] font-bold ${badge.classes}`}>
                            {badge.label}
                          </span>
                        </td>

                        {/* Usable Stock */}
                        <td className="px-3 py-3 text-right font-medium text-slate-800">
                          <div>{formatNumber(itemUsable)} m</div>
                          {itemCut > 0 && (
                            <div className="text-[10px] text-slate-400 font-normal">
                              +{formatNumber(itemCut)} cut
                            </div>
                          )}
                        </td>

                        {/* Target Stock */}
                        <td className="px-3 py-3 text-right text-slate-700 font-medium">
                          {rowInsufficient || item.group_buffered_target_stock === null ? (
                            <span className="text-slate-400 text-[11px]">Not calculated</span>
                          ) : (
                            <>
                              <div>{formatNumber(item.group_buffered_target_stock)} m</div>
                              {item.group_stock_gap && item.group_stock_gap > 0 ? (
                                <div className="text-[10px] text-blue-700 font-semibold">
                                  Deficit: {formatNumber(item.group_stock_gap)}
                                </div>
                              ) : null}
                            </>
                          )}
                        </td>

                        {/* Suggested Purchase */}
                        <td className="px-4 py-3 text-right font-bold">
                          {item.group_suggested_purchase_qty > 0 ? (
                            <span className="text-emerald-700 font-extrabold text-sm">
                              {formatNumber(item.group_suggested_purchase_qty)} m
                            </span>
                          ) : rowInsufficient ? (
                            <div>
                              <span className="text-slate-500 font-medium">0 m</span>
                              <div className="text-[10px] text-amber-700 font-semibold">Safety Hold</div>
                            </div>
                          ) : (
                            <span className="text-slate-400 font-normal">0 m</span>
                          )}
                        </td>

                        {/* Business Rationale */}
                        <td className="px-4 py-3 text-slate-600 max-w-xs text-[11px] leading-relaxed">
                          {humanizeReason(item)}
                        </td>

                        {/* Action / Inspect Button */}
                        <td className="px-4 py-3 text-right">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleOpenDetail(item);
                            }}
                            className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-100 transition-colors shadow-2xs"
                          >
                            Inspect
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Structured Group Detail Modal */}
      {isModalOpen && selectedGroup && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs"
          onClick={handleCloseModal}
        >
          <div
            className="relative w-full max-w-4xl max-h-[90vh] bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 bg-slate-50 shrink-0">
              <div>
                <h2 className="text-base font-bold text-slate-900">
                  {selectedGroup.main_product_name}
                </h2>
                <div className="flex items-center gap-2 mt-0.5 text-xs text-slate-500">
                  <span className="font-mono">Template ID {selectedGroup.main_product_template_id}</span>
                  <span>·</span>
                  <span>{selectedGroup.group_size} group members</span>
                  <span>·</span>
                  <span>Planning Run: <strong className="font-mono text-slate-700">{effectiveRunId || "latest"}</strong></span>
                </div>
              </div>
              <button
                onClick={handleCloseModal}
                className="rounded-lg p-2 text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition-colors"
                aria-label="Close modal"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Modal Body */}
            <div className="overflow-y-auto p-6 space-y-6">
              {groupDetailLoading ? (
                <div className="flex min-h-64 items-center justify-center">
                  <div className="h-7 w-7 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
                </div>
              ) : (
                <>
                  {/* Cold-Start / Insufficient History Advisory Banner */}
                  {isColdStart && (
                    <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-xs text-amber-900 flex items-start gap-3">
                      <span className="rounded bg-amber-200 px-2 py-0.5 text-[10px] uppercase font-extrabold tracking-wider text-amber-900 shrink-0 border border-amber-300">
                        Advisory Only
                      </span>
                      <div className="leading-relaxed">
                        <strong>Insufficient Sales History Safeguard:</strong> This product group has fewer than 6 usable months of historical demand ({forecastData?.months_available ?? 0} months recorded). Operational demand forecast, horizon demand, and target stock buffer are <strong>not calculated</strong>. Suggested purchase quantity is restricted to <strong>0 units</strong> as a protective safety boundary pending human planner review—not proof that current inventory satisfies unknown future demand.
                      </div>
                    </div>
                  )}

                  {/* Top Level Summary Cards */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="p-3 rounded-xl border border-slate-200 bg-slate-50/80">
                      <p className="text-[11px] font-medium text-slate-500">Decision Signal</p>
                      <p className="mt-1">
                        <span className={`inline-flex rounded border px-2 py-0.5 text-xs font-bold ${actionBadge(selectedGroup.action).classes}`}>
                          {actionBadge(selectedGroup.action).label}
                        </span>
                      </p>
                    </div>
                    <div className="p-3 rounded-xl border border-slate-200 bg-slate-50/80">
                      <p className="text-[11px] font-medium text-slate-500">Usable Stock</p>
                      <p className="text-base font-bold text-slate-900 mt-1">
                        {formatNumber(usableStock)} m
                      </p>
                    </div>
                    <div className="p-3 rounded-xl border border-slate-200 bg-slate-50/80">
                      <p className="text-[11px] font-medium text-slate-500">Target Stock Buffer</p>
                      <p className="text-base font-bold text-slate-900 mt-1">
                        {isInsufficientHistory || targetBufferedStock === null || targetBufferedStock === undefined
                          ? "Not calculated"
                          : `${formatNumber(targetBufferedStock)} m`}
                      </p>
                    </div>
                    <div className="p-3 rounded-xl border border-slate-200 bg-slate-50/80">
                      <p className="text-[11px] font-medium text-slate-500">Suggested Purchase</p>
                      <p className="text-base font-bold text-emerald-700 mt-1">
                        {formatNumber(suggestedPurchase)} m
                      </p>
                    </div>
                  </div>

                  {/* Section 1: Demand Forecast */}
                  <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                      1. Demand Forecast Overview
                    </h3>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                      <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                        <span className="text-slate-500 text-[11px] block">Next Month Demand</span>
                        <span className="font-bold text-slate-900 text-sm">
                          {isInsufficientHistory || selectedGroup.group_next_month_forecast === null
                            ? "Not calculated — insufficient history"
                            : `${formatNumber(selectedGroup.group_next_month_forecast)} m`}
                        </span>
                      </div>
                      <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                        <span className="text-slate-500 text-[11px] block">Lead Time Demand (3M)</span>
                        <span className="font-semibold text-slate-900">
                          {isInsufficientHistory || leadTimeDemand === null
                            ? "Not calculated — insufficient history"
                            : `${formatNumber(leadTimeDemand)} m`}
                        </span>
                      </div>
                      <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                        <span className="text-slate-500 text-[11px] block">Review Period Demand (1M)</span>
                        <span className="font-semibold text-slate-900">
                          {isInsufficientHistory || reviewPeriodDemand === null
                            ? "Not calculated — insufficient history"
                            : `${formatNumber(reviewPeriodDemand)} m`}
                        </span>
                      </div>
                      <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                        <span className="text-slate-500 text-[11px] block">Horizon Demand ({horizonMonths}M)</span>
                        <span className="font-bold text-slate-900">
                          {isInsufficientHistory || forecastedHorizonDemand === null
                            ? "Not calculated — insufficient history"
                            : `${formatNumber(forecastedHorizonDemand)} m`}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Section 2: Stock Composition Visualization (Stacked Bar + Signals) */}
                  <StockCompositionBar
                    totalPhysicalStock={totalPhysicalStock}
                    usableStock={usableStock}
                    cutPiecesExcluded={cutPiecesExcluded}
                    incomingStock={incomingStock}
                    committedStock={committedStock}
                    netPosition={inventoryPosition}
                    unit="m"
                  />

                  {/* Section 3: Suggested Replenishment Calculation */}
                  <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                      3. Replenishment Target &amp; Purchase Calculation
                    </h3>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                      <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                        <span className="text-slate-500 text-[11px] block">Target Stock Buffer</span>
                        <span className="font-bold text-slate-900">
                          {isInsufficientHistory || targetBufferedStock === null || targetBufferedStock === undefined
                            ? "Not calculated — insufficient history"
                            : `${formatNumber(targetBufferedStock)} m`}
                        </span>
                      </div>
                      <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                        <span className="text-slate-500 text-[11px] block">Net Inventory Position</span>
                        <span className="font-semibold text-slate-900">
                          {formatNumber(inventoryPosition)} m
                        </span>
                      </div>
                      <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                        <span className="text-slate-500 text-[11px] block">Stock Gap (Deficit)</span>
                        <span className="font-bold text-slate-900">
                          {isInsufficientHistory || stockGap === null || stockGap === undefined
                            ? "Not calculated — insufficient history"
                            : `${formatNumber(stockGap)} m`}
                        </span>
                      </div>
                      <div className="p-2.5 rounded-lg bg-blue-50/80 border border-blue-200">
                        <span className="text-blue-700 text-[11px] block font-bold">Suggested Purchase</span>
                        <span className="font-extrabold text-emerald-700 text-sm">
                          {formatNumber(suggestedPurchase)} m
                        </span>
                        {isInsufficientHistory && (
                          <span className="text-[10px] text-amber-700 font-semibold mt-0.5 block">
                            Safety Hold: 0 m pending review
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Section 4: Why this action was recommended */}
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-2">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                      4. Replenishment Recommendation Rationale
                    </h3>
                    <p className="text-xs text-slate-700 leading-relaxed">
                      {isInsufficientHistory ? (
                        `Advisory only: Short sales history (${forecastData?.months_available ?? 0} usable months). Operational forecast, horizon demand, and target buffer cannot be reliably calculated. Suggested purchase is restricted to 0 m as a protective safety restriction pending human planner review, not evidence that current inventory satisfies unknown future demand.`
                      ) : (
                        humanizeReason(selectedGroup, cb)
                      )}
                    </p>
                  </div>

                  {/* Section 5: Technical Details (Collapsed by default) */}
                  <details className="rounded-xl border border-slate-200 bg-slate-50/50 p-4 group">
                    <summary className="text-xs font-bold uppercase tracking-wider text-slate-600 cursor-pointer select-none flex items-center justify-between">
                      <span>5. Technical Calculation Details</span>
                      <span className="text-[11px] font-normal text-slate-400 group-open:hidden">Click to expand</span>
                    </summary>
                    <div className="mt-4 space-y-3 pt-3 border-t border-slate-200 text-xs">
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <div className="p-2.5 rounded-lg bg-white border border-slate-200">
                          <span className="text-slate-400 text-[10px] block">Champion Model</span>
                          <span className="font-mono font-semibold text-slate-800">
                            {cb?.forecast_breakdown?.best_model || selectedGroup.best_model || (isInsufficientHistory ? "analogue_cold_start" : "trimmed_mean_3")}
                          </span>
                        </div>
                        <div className="p-2.5 rounded-lg bg-white border border-slate-200">
                          <span className="text-slate-400 text-[10px] block">Confidence Level</span>
                          <span className="font-semibold capitalize text-slate-800">
                            {selectedGroup.confidence || (isInsufficientHistory ? "Low (Advisory Only)" : "Normal")}
                          </span>
                        </div>
                        <div className="p-2.5 rounded-lg bg-white border border-slate-200">
                          <span className="text-slate-400 text-[10px] block">Service Level (Z-Score)</span>
                          <span className="font-semibold text-slate-800">
                            {cb?.safety_stock_breakdown?.service_level !== undefined && cb?.safety_stock_breakdown?.service_level !== null
                              ? `${(cb.safety_stock_breakdown.service_level * 100).toFixed(0)}% (Z=${cb.safety_stock_breakdown.z_score ?? 0})`
                              : "—"}
                          </span>
                        </div>
                        <div className="p-2.5 rounded-lg bg-white border border-slate-200">
                          <span className="text-slate-400 text-[10px] block">Forecast Error Sigma</span>
                          <span className="font-semibold text-slate-800">
                            σ = {cb?.safety_stock_breakdown?.sigma_error_1m !== undefined ? formatNumber(cb.safety_stock_breakdown.sigma_error_1m, 2) : "—"}
                          </span>
                        </div>
                      </div>
                    </div>
                  </details>

                  {/* Section 6: Responsive Vertical Bar Demand History Chart */}
                  <MonthlyDemandChart
                    history={history}
                    loading={historyLoading}
                    effectiveRunId={effectiveRunId}
                    unit="m"
                  />
                </>
              )}
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-end px-6 py-3 border-t border-slate-200 bg-slate-50 shrink-0">
              <button
                type="button"
                onClick={handleCloseModal}
                className="px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs transition-colors shadow-2xs"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </AppLayout>
  );
}

export default function RecommendationsPage() {
  return (
    <Suspense
      fallback={
        <AppLayout>
          <div className="flex min-h-64 items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
          </div>
        </AppLayout>
      }
    >
      <RecommendationsContent />
    </Suspense>
  );
}
