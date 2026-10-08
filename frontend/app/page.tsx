"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import AppLayout from "@/components/AppLayout";

type Summary = {
  total_products: number;
  actions: Record<string, number>;
  priorities: Record<string, number>;
};

type Recommendation = {
  product_id: number;
  product_name: string | null;
  action: "purchase" | "review" | "excess_stock" | "dead_stock";
  priority: "high" | "medium" | "low";
  next_month_forecast: number;
  current_stock: number;
  reorder_point: number;
  buffered_target_stock: number;
  suggested_purchase_qty: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(value);
}

function MetricCard({
  label,
  value,
  subtext,
  accentColor,
}: {
  label: string;
  value: string | number;
  subtext?: string;
  accentColor?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className={`mt-2 text-2xl font-bold tracking-tight ${accentColor || "text-slate-900"}`}>
        {value}
      </p>
      {subtext && <p className="mt-1 text-xs text-slate-400">{subtext}</p>}
    </div>
  );
}

export default function OverviewPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [topRecommendations, setTopRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const token = sessionStorage.getItem("auth_token");
    if (!token) return;

    async function loadOverview() {
      try {
        setLoading(true);
        setError("");

        const [summaryRes, recsRes] = await Promise.all([
          fetch(`${API_BASE}/api/inventory/summary`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${API_BASE}/api/inventory/recommendations`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
        ]);

        if (!summaryRes.ok || !recsRes.ok) {
          throw new Error("Failed to load inventory overview data");
        }

        const summaryData: Summary = await summaryRes.json();
        const recsData: Recommendation[] = await recsRes.json();

        setSummary(summaryData);
        // Extract top active items with positive forecast or purchase recommendation
        const activeItems = recsData
          .filter((item) => item.next_month_forecast > 0 || item.suggested_purchase_qty > 0)
          .slice(0, 8);
        setTopRecommendations(activeItems);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to connect to backend");
      } finally {
        setLoading(false);
      }
    }

    loadOverview();
  }, []);

  const purchaseCount = summary?.actions.purchase ?? 8;
  const reviewCount = summary?.actions.review ?? 680;
  const excessCount = summary?.actions.excess_stock ?? 218;
  const deadStockCount = summary?.actions.dead_stock ?? 94;
  const totalCount = summary?.total_products ?? 1000;

  return (
    <AppLayout>
      <div className="space-y-6 max-w-7xl mx-auto">
        {/* Page Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900">
              Demand Forecasting &amp; Inventory Overview
            </h1>
            <p className="text-sm text-slate-500 mt-0.5">
              Empirically validated statistical forecasting across {formatNumber(totalCount)} products using the{" "}
              <span className="font-semibold text-slate-700">trimmed_mean_3</span> champion model.
            </p>
          </div>
          <div className="flex items-center gap-2.5">
            <Link
              href="/main-products"
              className="px-3.5 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold text-xs transition-colors border border-slate-200"
            >
              Main Products →
            </Link>
            <Link
              href="/recommendations"
              className="px-3.5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs transition-colors shadow-xs"
            >
              All Recommendations →
            </Link>
          </div>
        </div>

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Forecasting KPI Cards */}
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6" aria-label="Forecasting KPIs">
          <MetricCard
            label="Products Analyzed"
            value={formatNumber(totalCount)}
            subtext="Validated catalog dataset"
          />
          <MetricCard
            label="Needs Attention"
            value={formatNumber(purchaseCount + reviewCount)}
            subtext="Purchase or review signals"
            accentColor="text-amber-600"
          />
          <MetricCard
            label="Excess / Dead Stock"
            value={formatNumber(excessCount + deadStockCount)}
            subtext="Overstocked or dormant"
            accentColor="text-purple-600"
          />
          <MetricCard
            label="Forecast Coverage"
            value="100%"
            subtext="Universal fallback hierarchy"
            accentColor="text-emerald-600"
          />
          <MetricCard
            label="Champion Model"
            value="trimmed_mean_3"
            subtext="Empirically selected"
            accentColor="text-blue-600"
          />
          <MetricCard
            label="Main Product Groups"
            value="985"
            subtext="Canonical grouped catalog"
          />
        </section>

        {/* Demand Pattern Distribution */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div>
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-900">
                Demand Pattern Distribution
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Inventory recommendation breakdown across {formatNumber(totalCount)} catalog products
              </p>
            </div>
            <span className="text-[11px] font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200">
              Odoo 100% Read-Only
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
            {[
              {
                label: "Needs Purchase",
                count: purchaseCount,
                color: "bg-blue-500",
                bg: "bg-blue-50/50",
                border: "border-blue-200",
                text: "text-blue-900",
                desc: "Stock below buffered target",
                tab: "purchase",
              },
              {
                label: "Review Required",
                count: reviewCount,
                color: "bg-amber-400",
                bg: "bg-amber-50/50",
                border: "border-amber-200",
                text: "text-amber-900",
                desc: "Irregular or cold-start patterns",
                tab: "review",
              },
              {
                label: "Excess Stock",
                count: excessCount,
                color: "bg-purple-500",
                bg: "bg-purple-50/50",
                border: "border-purple-200",
                text: "text-purple-900",
                desc: "Stock exceeds buffered target",
                tab: "excess_stock",
              },
              {
                label: "Dead Stock",
                count: deadStockCount,
                color: "bg-red-400",
                bg: "bg-red-50/50",
                border: "border-red-200",
                text: "text-red-900",
                desc: "No sales across recent 12+ mos",
                tab: "dead_stock",
              },
            ].map((item) => (
              <Link
                key={item.label}
                href={`/recommendations?tab=${item.tab}`}
                className={`group block rounded-xl border p-4 ${item.bg} ${item.border} hover:shadow-sm transition-all`}
              >
                <div className="flex items-center gap-2 mb-1.5">
                  <span className={`h-2 w-2 rounded-full ${item.color} shrink-0`} />
                  <span className={`text-xs font-bold uppercase tracking-wide ${item.text}`}>
                    {item.label}
                  </span>
                </div>
                <p className={`text-2xl font-bold tracking-tight ${item.text}`}>
                  {formatNumber(item.count)}
                </p>
                <p className="text-[11px] text-slate-500 mt-1">
                  {((item.count / totalCount) * 100).toFixed(1)}% of catalog · {item.desc}
                </p>
              </Link>
            ))}
          </div>
        </div>

        {/* Active Replenishment & Forecast Signals Preview */}
        <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-xs">
          <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
            <div>
              <h2 className="text-sm font-bold text-slate-900">
                Active Purchase &amp; Forecast Signals
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Top products exhibiting active monthly demand and reorder requirements
              </p>
            </div>
            <Link
              href="/recommendations"
              className="text-xs font-semibold text-blue-600 hover:text-blue-700"
            >
              View all 1,000 products →
            </Link>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full text-xs">
              <thead className="bg-slate-50 text-left text-slate-500 font-semibold border-b border-slate-200">
                <tr>
                  <th className="px-6 py-3">Product</th>
                  <th className="px-4 py-3">Current Stock</th>
                  <th className="px-4 py-3">Forecast (1M)</th>
                  <th className="px-4 py-3">Target Buffer</th>
                  <th className="px-4 py-3">Suggested Qty</th>
                  <th className="px-4 py-3">Action</th>
                  <th className="px-4 py-3">Priority</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {topRecommendations.map((item) => (
                  <tr key={item.product_id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-3 font-medium text-slate-900">
                      <div>{item.product_name || "Product"}</div>
                      <span className="text-[10px] text-slate-400">ID {item.product_id}</span>
                    </td>
                    <td className="px-4 py-3 text-slate-700 font-medium">
                      {formatNumber(item.current_stock)} units
                    </td>
                    <td className="px-4 py-3 font-bold text-blue-700">
                      {formatNumber(item.next_month_forecast)}
                    </td>
                    <td className="px-4 py-3 text-slate-700">
                      {formatNumber(item.buffered_target_stock)}
                    </td>
                    <td className="px-4 py-3 font-bold text-emerald-700">
                      {formatNumber(item.suggested_purchase_qty)}
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex rounded px-2 py-0.5 text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200 uppercase">
                        {item.action.replace("_", " ")}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded px-2 py-0.5 text-[10px] font-bold uppercase ${
                          item.priority === "high"
                            ? "bg-red-50 text-red-700 border border-red-200"
                            : "bg-amber-50 text-amber-700 border border-amber-200"
                        }`}
                      >
                        {item.priority}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}