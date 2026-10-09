"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import AppLayout, { sanitizeErrorMessage } from "@/components/AppLayout";
import { usePlanningRun } from "@/components/PlanningRunContext";

type MainProductListItem = {
  main_product_template_id: number;
  main_product_name: string;
  group_size: number;
  group_valid: boolean;
  group_current_stock: number | null;
  group_usable_qty?: number | null;
  group_cut_piece_qty?: number | null;
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
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

function formatNumber(value: number | null | undefined, maxFrac = 1) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: maxFrac }).format(value);
}

function formatDate(dateStr: string | null | undefined) {
  if (!dateStr) return "—";
  try {
    const d = new Date(dateStr);
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  } catch {
    return dateStr;
  }
}

function actionBadge(action: string) {
  switch (action) {
    case "purchase":
      return "bg-blue-50 text-blue-700 border-blue-200";
    case "review":
      return "bg-amber-50 text-amber-700 border-amber-200";
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

export default function OverviewPage() {
  const { activeEffectiveRun, effectiveRunId, selectedRunId, isLoading: isRunLoading } =
    usePlanningRun();

  const [groups, setGroups] = useState<MainProductListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const token = typeof window !== "undefined" ? sessionStorage.getItem("auth_token") : null;
    if (!token) return;

    let isMounted = true;
    const controller = new AbortController();

    async function loadOverview() {
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
            if (isMounted) {
              setGroups([]);
              setLoading(false);
            }
            return;
          }
          throw new Error(`Failed to load planning data (HTTP ${res.status})`);
        }

        const data: MainProductListItem[] = await res.json();
        if (isMounted) {
          setGroups(Array.isArray(data) ? data : []);
        }
      } catch (err: any) {
        if (err.name === "AbortError") return;
        if (isMounted) {
          setError(err instanceof Error ? err.message : "Unable to connect to backend");
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    loadOverview();

    return () => {
      isMounted = false;
      controller.abort();
    };
  }, [effectiveRunId, activeEffectiveRun?.is_pruned, activeEffectiveRun?.status]);

  // Derived action counts covering ALL 5 backend actions (100% reconciled)
  const actionCounts = useMemo(() => {
    const counts = {
      purchase: 0,
      review: 0,
      excess_stock: 0,
      dead_stock: 0,
      hold: 0,
    };
    for (const g of groups) {
      if (g.action === "purchase") counts.purchase += 1;
      else if (g.action === "review") counts.review += 1;
      else if (g.action === "excess_stock") counts.excess_stock += 1;
      else if (g.action === "dead_stock") counts.dead_stock += 1;
      else counts.hold += 1;
    }
    return counts;
  }, [groups]);

  const totalGroupsCount = groups.length;

  const totalSuggestedQty = useMemo(() => {
    return groups.reduce((acc, g) => acc + (Number(g.group_suggested_purchase_qty) || 0), 0);
  }, [groups]);

  const totalForecastDemand = useMemo(() => {
    return groups.reduce((acc, g) => acc + (Number(g.group_next_month_forecast) || 0), 0);
  }, [groups]);

  // Cold-start / short-history diagnostic items
  const coldStartWarnings = useMemo(() => {
    return groups.filter(
      (g) =>
        g.action === "review" &&
        (g.best_model?.includes("analogue") ||
          g.forecast_status?.includes("insufficient") ||
          g.forecast_status?.includes("cold_start") ||
          g.confidence === "low")
    );
  }, [groups]);

  // Top purchase and review items ranked by urgency
  const topSignals = useMemo(() => {
    return groups
      .filter((g) => g.action === "purchase" || g.action === "review")
      .slice(0, 10);
  }, [groups]);

  const isPruned = activeEffectiveRun?.is_pruned;

  return (
    <AppLayout>
      <div className="space-y-6 max-w-7xl mx-auto">
        {/* Page Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900">
              Demand Forecasting &amp; Operational Overview
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">
              Replenishment recommendations, demand signals, and stock health for selected planning run.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/main-products"
              className="px-3.5 py-2 rounded-lg bg-white hover:bg-slate-50 text-slate-700 font-semibold text-xs transition-colors border border-slate-200 shadow-2xs"
            >
              Main Products →
            </Link>
            <Link
              href="/recommendations"
              className="px-3.5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs transition-colors shadow-2xs"
            >
              Recommendations Table →
            </Link>
          </div>
        </div>

        {/* Selected Run Strip */}
        {activeEffectiveRun && (
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <div
                  className={`h-2.5 w-2.5 rounded-full shrink-0 ${
                    activeEffectiveRun.status === "completed"
                      ? "bg-emerald-500"
                      : activeEffectiveRun.status === "running"
                      ? "bg-blue-500 animate-pulse"
                      : "bg-rose-500"
                  }`}
                />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-bold text-slate-900">
                      {activeEffectiveRun.run_id}
                    </span>
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase border ${
                        activeEffectiveRun.status === "completed"
                          ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                          : activeEffectiveRun.status === "running"
                          ? "bg-blue-50 text-blue-700 border-blue-200"
                          : "bg-rose-50 text-rose-700 border-rose-200"
                      }`}
                    >
                      {activeEffectiveRun.status}
                    </span>
                    {isPruned && (
                      <span className="rounded bg-amber-50 text-amber-800 text-[10px] font-bold px-1.5 py-0.5 border border-amber-200">
                        Pruned Snapshot
                      </span>
                    )}
                    {selectedRunId && (
                      <span className="rounded bg-slate-100 text-slate-600 text-[10px] font-medium px-1.5 py-0.5 border border-slate-200">
                        Historical Selection
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    Executed {formatDate(activeEffectiveRun.completed_at || activeEffectiveRun.started_at)} · {activeEffectiveRun.num_groups} product groups evaluated
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-6 text-xs text-slate-600 sm:text-right border-t sm:border-t-0 pt-2 sm:pt-0">
                <div>
                  <span className="text-slate-400 block text-[10px]">Suggested Order Volume</span>
                  <span className="font-bold text-blue-700 text-sm">
                    {formatNumber(totalSuggestedQty)} <span className="text-xs font-normal text-slate-500">units</span>
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">Next-Month Forecast</span>
                  <span className="font-bold text-slate-900 text-sm">
                    {formatNumber(totalForecastDemand)} <span className="text-xs font-normal text-slate-500">units</span>
                  </span>
                </div>
              </div>
            </div>

            {activeEffectiveRun.status === "failed" && (
              <div className="mt-3 p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-800">
                <strong>Run Failure Diagnostic:</strong> {sanitizeErrorMessage(activeEffectiveRun.error_message)}
              </div>
            )}
            {activeEffectiveRun.status === "missing" && (
              <div className="mt-3 p-3 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-800">
                <strong>Run Not Found:</strong> The requested planning run was not found in the persistence store.
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
            {error}
          </div>
        )}

        {/* Cold-Start Diagnostic Banner (Compact & Clear) */}
        {coldStartWarnings.length > 0 && (
          <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-4">
            <div className="flex items-start gap-3">
              <svg className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold uppercase tracking-wider text-amber-900">
                    Cold-Start &amp; Short-History Notice
                  </span>
                  <span className="rounded bg-amber-200 px-1.5 py-0.2 text-[10px] font-bold text-amber-900 border border-amber-300">
                    Advisory Only
                  </span>
                </div>
                <p className="text-xs text-amber-800 mt-1">
                  <strong>{coldStartWarnings.length} product groups</strong> have fewer than 6 months of historical sales. Replenishment quantities are held at 0 units pending human review.
                </p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {coldStartWarnings.slice(0, 5).map((g) => (
                    <Link
                      key={g.main_product_template_id}
                      href={`/main-products`}
                      className="inline-flex items-center gap-1 rounded bg-white px-2 py-0.5 text-xs text-amber-900 border border-amber-300 hover:bg-amber-100 transition-colors"
                    >
                      <span>{g.main_product_name}</span>
                      <span className="text-[10px] text-amber-600 font-mono">ID {g.main_product_template_id}</span>
                    </Link>
                  ))}
                  {coldStartWarnings.length > 5 && (
                    <span className="text-xs text-amber-700 self-center font-medium">
                      +{coldStartWarnings.length - 5} more
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Visual Recommendation Action Distribution Chart (100% Reconciled) */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-2xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-3">
            <div>
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-900">
                Recommendation Action Distribution
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                All {totalGroupsCount} product groups classified by operational inventory decision
              </p>
            </div>
            <span className="text-xs font-medium text-slate-500">
              Total Catalog: <strong className="text-slate-900">{totalGroupsCount} groups</strong>
            </span>
          </div>

          {/* Segmented Distribution Bar */}
          {totalGroupsCount > 0 ? (
            <div className="space-y-2">
              <div className="flex h-3.5 w-full rounded-full overflow-hidden bg-slate-100 p-0.5">
                {actionCounts.purchase > 0 && (
                  <div
                    style={{ width: `${(actionCounts.purchase / totalGroupsCount) * 100}%` }}
                    className="bg-blue-600 rounded-l-full transition-all"
                    title={`Needs Purchase: ${actionCounts.purchase} (${((actionCounts.purchase / totalGroupsCount) * 100).toFixed(1)}%)`}
                  />
                )}
                {actionCounts.review > 0 && (
                  <div
                    style={{ width: `${(actionCounts.review / totalGroupsCount) * 100}%` }}
                    className="bg-amber-500 transition-all"
                    title={`Review Required: ${actionCounts.review} (${((actionCounts.review / totalGroupsCount) * 100).toFixed(1)}%)`}
                  />
                )}
                {actionCounts.excess_stock > 0 && (
                  <div
                    style={{ width: `${(actionCounts.excess_stock / totalGroupsCount) * 100}%` }}
                    className="bg-purple-600 transition-all"
                    title={`Excess Stock: ${actionCounts.excess_stock} (${((actionCounts.excess_stock / totalGroupsCount) * 100).toFixed(1)}%)`}
                  />
                )}
                {actionCounts.dead_stock > 0 && (
                  <div
                    style={{ width: `${(actionCounts.dead_stock / totalGroupsCount) * 100}%` }}
                    className="bg-rose-500 transition-all"
                    title={`Dead Stock: ${actionCounts.dead_stock} (${((actionCounts.dead_stock / totalGroupsCount) * 100).toFixed(1)}%)`}
                  />
                )}
                {actionCounts.hold > 0 && (
                  <div
                    style={{ width: `${(actionCounts.hold / totalGroupsCount) * 100}%` }}
                    className="bg-emerald-500 rounded-r-full transition-all"
                    title={`Stock Sufficient: ${actionCounts.hold} (${((actionCounts.hold / totalGroupsCount) * 100).toFixed(1)}%)`}
                  />
                )}
              </div>

              {/* Action Metric Cards (reconciled sum = totalGroupsCount) */}
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5 pt-2">
                {[
                  {
                    key: "purchase",
                    label: "Needs Purchase",
                    count: actionCounts.purchase,
                    color: "text-blue-700",
                    dot: "bg-blue-600",
                    desc: "Stock gap > 0",
                    filterUrl: "/main-products",
                  },
                  {
                    key: "review",
                    label: "Review Required",
                    count: actionCounts.review,
                    color: "text-amber-700",
                    dot: "bg-amber-500",
                    desc: "Cold-start / low history",
                    filterUrl: "/main-products",
                  },
                  {
                    key: "excess_stock",
                    label: "Excess Stock",
                    count: actionCounts.excess_stock,
                    color: "text-purple-700",
                    dot: "bg-purple-600",
                    desc: "Stock exceeds 2x target",
                    filterUrl: "/main-products",
                  },
                  {
                    key: "dead_stock",
                    label: "Dead Stock",
                    count: actionCounts.dead_stock,
                    color: "text-rose-700",
                    dot: "bg-rose-500",
                    desc: "0 sales in 12+ months",
                    filterUrl: "/main-products",
                  },
                  {
                    key: "hold",
                    label: "Stock Sufficient",
                    count: actionCounts.hold,
                    color: "text-emerald-700",
                    dot: "bg-emerald-500",
                    desc: "Stock covers demand",
                    filterUrl: "/main-products",
                  },
                ].map((item) => {
                  const pct = totalGroupsCount > 0 ? ((item.count / totalGroupsCount) * 100).toFixed(1) : "0";
                  return (
                    <Link
                      key={item.key}
                      href={item.filterUrl}
                      className="p-3 rounded-lg border border-slate-200 bg-slate-50/60 hover:bg-slate-100 hover:border-slate-300 transition-all text-left"
                    >
                      <div className="flex items-center gap-1.5 mb-1">
                        <span className={`h-2 w-2 rounded-full ${item.dot} shrink-0`} />
                        <span className="text-[11px] font-semibold text-slate-700 truncate">
                          {item.label}
                        </span>
                      </div>
                      <p className={`text-xl font-bold ${item.color}`}>
                        {formatNumber(item.count, 0)}
                      </p>
                      <p className="text-[10px] text-slate-500 mt-0.5">
                        {pct}% · {item.desc}
                      </p>
                    </Link>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="py-8 text-center text-xs text-slate-400">
              No product group data available for this planning run.
            </div>
          )}
        </div>

        {/* Priority Replenishment Signals Table */}
        <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-2xs">
          <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50/50">
            <div>
              <h2 className="text-sm font-bold text-slate-900">
                Priority Purchase &amp; Review Signals
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Top products requiring purchase ordering or planner review
              </p>
            </div>
            <Link
              href="/recommendations"
              className="text-xs font-semibold text-blue-700 hover:text-blue-800 transition-colors"
            >
              View All Recommendations ({groups.length}) →
            </Link>
          </div>

          {loading ? (
            <div className="flex min-h-40 items-center justify-center">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
            </div>
          ) : topSignals.length === 0 ? (
            <div className="px-6 py-12 text-center text-xs text-slate-500">
              No active purchase or review actions in this planning run snapshot.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead className="bg-slate-50 text-left text-slate-500 font-semibold border-b border-slate-200">
                  <tr>
                    <th className="px-6 py-3">Product Group</th>
                    <th className="px-4 py-3">Action</th>
                    <th className="px-4 py-3 text-right">1M Forecast</th>
                    <th className="px-4 py-3 text-right">Usable Stock</th>
                    <th className="px-4 py-3 text-right">Target Buffer</th>
                    <th className="px-4 py-3 text-right">Suggested Purchase</th>
                    <th className="px-4 py-3 text-center">Priority</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {topSignals.map((item) => (
                    <tr
                      key={item.main_product_template_id}
                      className="hover:bg-slate-50 transition-colors"
                    >
                      <td className="px-6 py-3 font-medium text-slate-900">
                        <div className="font-semibold">{item.main_product_name}</div>
                        <span className="text-[10px] text-slate-400 font-mono">
                          ID {item.main_product_template_id} · {item.group_size} products
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-semibold border ${actionBadge(item.action)}`}>
                          {actionLabel(item.action)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right font-medium text-slate-900">
                        {formatNumber(item.group_next_month_forecast)}
                      </td>
                      <td className="px-4 py-3 text-right text-slate-700">
                        {formatNumber(item.group_current_stock)}
                      </td>
                      <td className="px-4 py-3 text-right text-slate-700">
                        {formatNumber(item.group_buffered_target_stock)}
                      </td>
                      <td className="px-4 py-3 text-right font-bold text-blue-700">
                        {item.group_suggested_purchase_qty > 0 ? (
                          <span>{formatNumber(item.group_suggested_purchase_qty)} units</span>
                        ) : (
                          <span className="text-slate-400 font-normal">0</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                          item.priority === "high"
                            ? "bg-rose-50 text-rose-700"
                            : item.priority === "medium"
                            ? "bg-amber-50 text-amber-700"
                            : "bg-slate-100 text-slate-600"
                        }`}>
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
      </div>
    </AppLayout>
  );
}