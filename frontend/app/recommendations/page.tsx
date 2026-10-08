"use client";

import { useEffect, useState, useMemo, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import AppLayout from "@/components/AppLayout";

type SimilarProductItem = {
  product_id: number;
  product_code: string;
  product_name: string;
  relationship: string;
};

type Recommendation = {
  scenario: string;
  product_id: number;
  product_name: string | null;
  action: "purchase" | "review" | "excess_stock" | "dead_stock";
  priority: "high" | "medium" | "low";
  next_month_forecast: number;
  current_stock: number;
  reorder_point: number;
  buffered_target_stock: number;
  stock_gap: number;
  coverage_ratio: number | null;
  suggested_purchase_qty: number;
  reason_codes: string[];
  trend?: string;
  confidence?: string;
  best_model?: string;
  months_available?: number | null;
  forecast_status?: string | null;
  months_since_last_sale?: number | null;
  dead_stock?: boolean | null;
  dead_stock_reason?: string | null;
  usable_qty?: number | null;
  cut_piece_qty?: number | null;
  analogue_count?: number | null;
  analogue_products?: string[] | string | null;
  analogue_details?: any;
  similar_products?: SimilarProductItem[] | null;
};

type HistoryPoint = {
  month: string;
  actual: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

function formatNumber(value: number | null | undefined, decimals = 1) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: decimals }).format(value);
}

function actionClasses(action: Recommendation["action"]) {
  switch (action) {
    case "purchase":
      return "bg-blue-50 text-blue-700 border-blue-200";
    case "review":
      return "bg-amber-50 text-amber-700 border-amber-200";
    case "excess_stock":
      return "bg-purple-50 text-purple-700 border-purple-200";
    case "dead_stock":
      return "bg-red-50 text-red-700 border-red-200";
    default:
      return "bg-slate-50 text-slate-700 border-slate-200";
  }
}

function priorityClasses(priority: Recommendation["priority"]) {
  switch (priority) {
    case "high":
      return "bg-red-50 text-red-700 border-red-200";
    case "medium":
      return "bg-amber-50 text-amber-700 border-amber-200";
    default:
      return "bg-slate-50 text-slate-600 border-slate-200";
  }
}

function RecommendationsContent() {
  const searchParams = useSearchParams();
  const initialTab = searchParams.get("tab") as any;

  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [activeTab, setActiveTab] = useState<"all" | "purchase" | "review" | "excess_stock" | "dead_stock">(
    initialTab && ["all", "purchase", "review", "excess_stock", "dead_stock"].includes(initialTab)
      ? initialTab
      : "all"
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 50;

  // Modal State
  const [selectedProduct, setSelectedProduct] = useState<Recommendation | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [isModalOpen, setIsModalOpen] = useState(false);

  useEffect(() => {
    const token = sessionStorage.getItem("auth_token");
    if (!token) return;

    async function loadRecommendations() {
      try {
        setLoading(true);
        setError("");

        const res = await fetch(`${API_BASE}/api/inventory/recommendations`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (!res.ok) throw new Error("Failed to load inventory recommendations");
        const data: Recommendation[] = await res.json();
        setRecommendations(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load recommendations");
      } finally {
        setLoading(false);
      }
    }

    loadRecommendations();
  }, []);

  // Filtered recommendations
  const filteredRecommendations = useMemo(() => {
    return recommendations.filter((item) => {
      if (activeTab !== "all" && item.action !== activeTab) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase().trim();
        const matchName = item.product_name?.toLowerCase().includes(q);
        const matchId = item.product_id.toString().includes(q);
        if (!matchName && !matchId) return false;
      }
      return true;
    });
  }, [recommendations, activeTab, searchQuery]);

  // Paginated recommendations
  const totalPages = Math.max(1, Math.ceil(filteredRecommendations.length / pageSize));
  const paginatedRecommendations = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredRecommendations.slice(start, start + pageSize);
  }, [filteredRecommendations, currentPage, pageSize]);

  // Open product detail modal
  const handleOpenDetail = useCallback(async (item: Recommendation) => {
    setSelectedProduct(item);
    setIsModalOpen(true);
    setHistory([]);
    setHistoryLoading(true);
    setHistoryError("");

    const token = sessionStorage.getItem("auth_token");
    if (!token) return;

    try {
      const res = await fetch(`${API_BASE}/api/forecast/product/${item.product_id}/history`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const histData: HistoryPoint[] = await res.json();
        setHistory(histData);
      } else {
        setHistoryError("Historical sales data unavailable");
      }
    } catch {
      setHistoryError("Error loading historical sales");
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const handleCloseModal = useCallback(() => {
    setIsModalOpen(false);
    setSelectedProduct(null);
    setHistory([]);
  }, []);

  return (
    <AppLayout>
      <div className="space-y-6 max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900">
              Product Recommendations &amp; Demand Forecasts
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">
              Statistical demand forecasting and safety stock calibration for {formatNumber(recommendations.length || 1000)} catalog products.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold px-3 py-1.5 rounded-lg bg-slate-100 text-slate-700 border border-slate-200">
              Champion Model: <span className="text-blue-700">trimmed_mean_3</span>
            </span>
          </div>
        </div>

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Search & Filter Tabs & Pagination */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            {/* Search Input */}
            <div className="relative flex-1 max-w-md">
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
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setCurrentPage(1);
                }}
                className="block w-full rounded-lg border border-slate-300 pl-9 pr-3 py-2 text-sm text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white"
              />
            </div>

            {/* Pagination Controls */}
            <div className="flex items-center justify-between sm:justify-end gap-3 text-xs text-slate-600 shrink-0">
              <span className="font-medium">
                {filteredRecommendations.length === 0
                  ? "0 products"
                  : `${(currentPage - 1) * pageSize + 1}–${Math.min(currentPage * pageSize, filteredRecommendations.length)} of ${filteredRecommendations.length}`}
              </span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="px-2.5 py-1 rounded-md border border-slate-300 bg-white font-medium hover:bg-slate-50 disabled:opacity-40 disabled:pointer-events-none"
                  aria-label="Previous page"
                >
                  ← Prev
                </button>
                <span className="px-2 font-bold text-slate-900">
                  {currentPage} / {totalPages}
                </span>
                <button
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage >= totalPages}
                  className="px-2.5 py-1 rounded-md border border-slate-300 bg-white font-medium hover:bg-slate-50 disabled:opacity-40 disabled:pointer-events-none"
                  aria-label="Next page"
                >
                  Next →
                </button>
              </div>
            </div>
          </div>

          {/* Filter Tabs */}
          <div className="flex items-center gap-1.5 overflow-x-auto pt-2 border-t border-slate-100">
            {[
              { id: "all", label: "All Products", count: recommendations.length },
              { id: "purchase", label: "Needs Purchase", count: recommendations.filter((r) => r.action === "purchase").length },
              { id: "review", label: "Review Required", count: recommendations.filter((r) => r.action === "review").length },
              { id: "excess_stock", label: "Excess Stock", count: recommendations.filter((r) => r.action === "excess_stock").length },
              { id: "dead_stock", label: "Dead Stock", count: recommendations.filter((r) => r.action === "dead_stock").length },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id as any);
                  setCurrentPage(1);
                }}
                className={`whitespace-nowrap px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  activeTab === tab.id
                    ? "bg-blue-600 text-white shadow-xs"
                    : "bg-white text-slate-600 hover:bg-slate-100 border border-slate-200"
                }`}
              >
                {tab.label} ({tab.count})
              </button>
            ))}
          </div>
        </div>

        {/* Recommendations Table */}
        <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-xs">
          {loading ? (
            <div className="flex min-h-64 items-center justify-center">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
            </div>
          ) : filteredRecommendations.length === 0 ? (
            <div className="px-6 py-16 text-center">
              <p className="text-base font-semibold text-slate-900">No matching products found</p>
              <p className="text-xs text-slate-500 mt-1">Try clearing your search query or selecting a different filter tab.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead className="bg-slate-50 text-left text-slate-500 font-semibold border-b border-slate-200">
                  <tr>
                    <th className="px-6 py-3.5">Product</th>
                    <th className="px-4 py-3.5">Pattern</th>
                    <th className="px-4 py-3.5">Current Stock</th>
                    <th className="px-4 py-3.5">Forecast (1M)</th>
                    <th className="px-4 py-3.5">Target Buffer</th>
                    <th className="px-4 py-3.5">Suggested Qty</th>
                    <th className="px-4 py-3.5">Priority</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {paginatedRecommendations.map((item) => (
                    <tr
                      key={item.product_id}
                      onClick={() => handleOpenDetail(item)}
                      className="hover:bg-blue-50/40 cursor-pointer transition-colors group"
                      title="Click to view forecast detail & history"
                    >
                      {/* Product Name & ID */}
                      <td className="px-6 py-3.5 font-medium text-slate-900">
                        <div className="group-hover:text-blue-700 font-semibold text-sm">
                          {item.product_name || "Unnamed product"}
                        </div>
                        <div className="flex items-center gap-2 mt-0.5 text-[11px] text-slate-400">
                          <span>ID {item.product_id}</span>
                          {item.best_model && (
                            <span className="font-mono text-[10px] text-slate-500">
                              · {item.best_model}
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Pattern / Action */}
                      <td className="px-4 py-3.5">
                        <span
                          className={`inline-flex rounded-md border px-2.5 py-1 text-[11px] font-bold uppercase ${actionClasses(
                            item.action
                          )}`}
                        >
                          {item.action.replace("_", " ")}
                        </span>
                      </td>

                      {/* Current Stock */}
                      <td className="px-4 py-3.5 text-slate-900 font-medium">
                        <div>{formatNumber(item.current_stock)} units</div>
                        {(item.usable_qty !== null && item.usable_qty !== undefined) && (
                          <div className="text-[10px] text-slate-500 mt-0.5">
                            Usable: {formatNumber(item.usable_qty)} · Cut: {formatNumber(item.cut_piece_qty)}
                          </div>
                        )}
                      </td>

                      {/* Forecast (1M) */}
                      <td className="px-4 py-3.5 font-bold text-slate-900">
                        <span className={item.next_month_forecast > 0 ? "text-blue-700 text-sm font-bold" : "text-slate-400"}>
                          {formatNumber(item.next_month_forecast)}
                        </span>
                      </td>

                      {/* Target Buffer */}
                      <td className="px-4 py-3.5 text-slate-700 font-medium">
                        {formatNumber(item.buffered_target_stock)}
                      </td>

                      {/* Suggested Qty */}
                      <td className="px-4 py-3.5 font-bold">
                        <span className={item.suggested_purchase_qty > 0 ? "text-emerald-700 text-sm font-bold" : "text-slate-400"}>
                          {formatNumber(item.suggested_purchase_qty)}
                        </span>
                      </td>

                      {/* Priority */}
                      <td className="px-4 py-3.5">
                        <span
                          className={`inline-flex rounded border px-2 py-0.5 text-[10px] font-bold uppercase ${priorityClasses(
                            item.priority
                          )}`}
                        >
                          {item.priority}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Bottom Pagination Info */}
        {!loading && filteredRecommendations.length > pageSize && (
          <div className="flex items-center justify-between text-xs text-slate-500 px-2">
            <span>
              Showing page {currentPage} of {totalPages} ({filteredRecommendations.length} products total)
            </span>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setCurrentPage(1)}
                disabled={currentPage === 1}
                className="px-2.5 py-1 rounded border border-slate-300 bg-white font-medium hover:bg-slate-50 disabled:opacity-40"
              >
                First
              </button>
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="px-2.5 py-1 rounded border border-slate-300 bg-white font-medium hover:bg-slate-50 disabled:opacity-40"
              >
                Prev
              </button>
              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage >= totalPages}
                className="px-2.5 py-1 rounded border border-slate-300 bg-white font-medium hover:bg-slate-50 disabled:opacity-40"
              >
                Next
              </button>
              <button
                onClick={() => setCurrentPage(totalPages)}
                disabled={currentPage >= totalPages}
                className="px-2.5 py-1 rounded border border-slate-300 bg-white font-medium hover:bg-slate-50 disabled:opacity-40"
              >
                Last
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Product Detail Modal */}
      {isModalOpen && selectedProduct && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs overflow-y-auto"
          onClick={handleCloseModal}
        >
          <div
            className="relative w-full max-w-3xl max-h-[90vh] bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 bg-slate-50/80 shrink-0">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-100 text-blue-800 font-bold text-sm">
                  {selectedProduct.product_name ? selectedProduct.product_name.charAt(0).toUpperCase() : "P"}
                </div>
                <div>
                  <h2 className="text-base font-bold text-slate-900">
                    {selectedProduct.product_name || "Product"}
                  </h2>
                  <p className="text-xs text-slate-500">
                    Product ID: {selectedProduct.product_id} · Model: {selectedProduct.best_model || "trimmed_mean_3"}
                  </p>
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

            {/* Modal Content */}
            <div className="overflow-y-auto p-6 space-y-6">
              {/* Key Metrics Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3 rounded-xl border border-slate-200 bg-slate-50">
                  <p className="text-[11px] font-medium text-slate-500">1M Forecast</p>
                  <p className="text-lg font-bold text-blue-700 mt-1">
                    {formatNumber(selectedProduct.next_month_forecast)} units
                  </p>
                </div>
                <div className="p-3 rounded-xl border border-slate-200 bg-slate-50">
                  <p className="text-[11px] font-medium text-slate-500">Target Stock</p>
                  <p className="text-lg font-bold text-slate-900 mt-1">
                    {formatNumber(selectedProduct.buffered_target_stock)} units
                  </p>
                </div>
                <div className="p-3 rounded-xl border border-slate-200 bg-slate-50">
                  <p className="text-[11px] font-medium text-slate-500">Current Stock</p>
                  <p className="text-lg font-bold text-slate-900 mt-1">
                    {formatNumber(selectedProduct.current_stock)} units
                  </p>
                </div>
                <div className="p-3 rounded-xl border border-slate-200 bg-slate-50">
                  <p className="text-[11px] font-medium text-slate-500">Suggested Purchase</p>
                  <p className="text-lg font-bold text-emerald-700 mt-1">
                    {formatNumber(selectedProduct.suggested_purchase_qty)} units
                  </p>
                </div>
              </div>

              {/* Status & Diagnostic Details */}
              <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900">
                  Forecasting Diagnostic Information
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  <div>
                    <span className="text-slate-500">Recommendation Action:</span>{" "}
                    <span className="font-bold capitalize text-slate-900">{selectedProduct.action.replace("_", " ")}</span>
                  </div>
                  <div>
                    <span className="text-slate-500">Priority Level:</span>{" "}
                    <span className="font-bold capitalize text-slate-900">{selectedProduct.priority}</span>
                  </div>
                  <div>
                    <span className="text-slate-500">History Available:</span>{" "}
                    <span className="font-semibold text-slate-900">
                      {selectedProduct.months_available ? `${selectedProduct.months_available} months` : "Full history"}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500">Confidence:</span>{" "}
                    <span className="font-semibold capitalize text-slate-900">{selectedProduct.confidence || "Normal"}</span>
                  </div>
                </div>
              </div>

              {/* Historical Demand Table / Chart */}
              <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900">
                  Historical Sales Actuals (Monthly Demand)
                </h3>
                {historyLoading ? (
                  <div className="flex h-32 items-center justify-center">
                    <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
                  </div>
                ) : historyError ? (
                  <p className="text-xs text-slate-500 py-4 text-center">{historyError}</p>
                ) : history.length === 0 ? (
                  <p className="text-xs text-slate-500 py-4 text-center">No monthly historical sales recorded.</p>
                ) : (
                  <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                    {history.slice(-12).map((h) => (
                      <div key={h.month} className="p-2 rounded-lg border border-slate-200 bg-slate-50 text-center">
                        <p className="text-[10px] text-slate-500 font-mono">{h.month}</p>
                        <p className="text-xs font-bold text-slate-900 mt-0.5">{formatNumber(h.actual)}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-end px-6 py-3 border-t border-slate-200 bg-slate-50 shrink-0">
              <button
                onClick={handleCloseModal}
                className="px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs transition-colors"
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
