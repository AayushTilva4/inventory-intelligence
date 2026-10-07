"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import Link from "next/link";

type ApprovalItem = {
  approval_id: string;
  snapshot_id: string;
  product_id: number;
  product_name: string;
  pattern: string;
  forecast_1m: number;
  forecast_h3: number;
  safety_buffer: number;
  service_level: number;
  target_stock: number;
  current_stock: number;
  suggested_purchase: number;
  legacy_target: number | null;
  target_delta: number | null;
  exception_category: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "EDITED" | "CANCELLED";
  planner_comment: string | null;
  edited_target_stock: number | null;
  edited_purchase_qty: number | null;
  planner_id: string | null;
  created_at: string;
  reviewed_at: string | null;
  audit_metadata?: any;
};

type ApprovalSummary = {
  total_items: number;
  status_counts: Record<string, number>;
  exception_counts: Record<string, number>;
  disclaimer: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

function formatNumber(val: number | null | undefined): string {
  if (val === null || val === undefined) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(val);
}

function statusBadge(status: string) {
  switch (status) {
    case "APPROVED":
      return "bg-emerald-100 text-emerald-800 border-emerald-300 font-bold";
    case "REJECTED":
      return "bg-rose-100 text-rose-800 border-rose-300 font-bold";
    case "EDITED":
      return "bg-blue-100 text-blue-800 border-blue-300 font-bold";
    case "PENDING":
      return "bg-amber-100 text-amber-800 border-amber-300 font-medium";
    default:
      return "bg-slate-100 text-slate-700 border-slate-300";
  }
}

function patternBadge(pattern: string) {
  switch (pattern) {
    case "fast_moving":
      return "bg-emerald-50 text-emerald-700 border-emerald-200";
    case "stable/normal":
      return "bg-blue-50 text-blue-700 border-blue-200";
    case "rising":
      return "bg-indigo-50 text-indigo-700 border-indigo-200";
    case "falling":
      return "bg-amber-50 text-amber-700 border-amber-200";
    case "intermittent":
      return "bg-purple-50 text-purple-700 border-purple-200";
    case "dead_stock":
      return "bg-rose-50 text-rose-700 border-rose-200";
    default:
      return "bg-slate-50 text-slate-700 border-slate-200";
  }
}

export default function CanaryShadowPlannerPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [summary, setSummary] = useState<ApprovalSummary | null>(null);
  const [items, setItems] = useState<ApprovalItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);

  // Filter States
  const [activeTab, setActiveTab] = useState<string>("PENDING");
  const [selectedPattern, setSelectedPattern] = useState<string>("all");
  const [searchTerm, setSearchTerm] = useState<string>("");

  // Modal / Drawer Action States
  const [selectedItem, setSelectedItem] = useState<ApprovalItem | null>(null);
  const [actionType, setActionType] = useState<"approve" | "reject" | "edit" | "detail" | null>(null);
  const [plannerComment, setPlannerComment] = useState("");
  const [overrideTarget, setOverrideTarget] = useState<string>("");
  const [overridePurchase, setOverridePurchase] = useState<string>("");
  const [actionError, setActionError] = useState("");
  const [actionSubmitting, setActionSubmitting] = useState(false);
  const [warningAck, setWarningAck] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const sumRes = await fetch(`${API_BASE}/api/approvals/summary`);
      if (sumRes.ok) {
        const sumData = await sumRes.json();
        setSummary(sumData);
      }

      const params = new URLSearchParams();
      if (["PENDING", "APPROVED", "REJECTED", "EDITED"].includes(activeTab)) {
        params.set("status", activeTab);
      } else if (activeTab !== "ALL") {
        params.set("exception_category", activeTab);
      }

      if (selectedPattern !== "all") params.set("pattern", selectedPattern);
      if (searchTerm.trim()) params.set("search", searchTerm.trim());
      params.set("limit", "150");

      const listRes = await fetch(`${API_BASE}/api/approvals?${params.toString()}`);
      if (!listRes.ok) throw new Error("Failed to load approval items from server");
      const listData = await listRes.json();
      setItems(listData.items || []);
      setTotalCount(listData.total || 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error connecting to approvals API");
    } finally {
      setLoading(false);
    }
  }, [activeTab, selectedPattern, searchTerm]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Open modal handlers
  const handleOpenAction = (item: ApprovalItem, type: "approve" | "reject" | "edit" | "detail") => {
    setSelectedItem(item);
    setActionType(type);
    setActionError("");
    setWarningAck(false);
    setPlannerComment("");
    setOverrideTarget(item.edited_target_stock !== null ? String(item.edited_target_stock) : String(item.target_stock));
    setOverridePurchase(item.edited_purchase_qty !== null ? String(item.edited_purchase_qty) : String(item.suggested_purchase));
  };

  const handleCloseModal = () => {
    setSelectedItem(null);
    setActionType(null);
    setActionError("");
    setActionSubmitting(false);
  };

  // Submit Approval Decision
  const handleSubmitDecision = async () => {
    if (!selectedItem || !actionType) return;
    setActionSubmitting(true);
    setActionError("");

    try {
      const apprId = selectedItem.approval_id;
      let url = "";
      let body: any = {};

      if (actionType === "approve") {
        url = `${API_BASE}/api/approvals/${apprId}/approve`;
        body = {
          planner_id: "lead_planner_ui",
          comment: plannerComment || "Approved via planner UI.",
          warning_acknowledged: warningAck,
        };
      } else if (actionType === "reject") {
        if (!plannerComment || plannerComment.trim().length < 3) {
          throw new Error("Rejection requires an explicit reason (minimum 3 characters).");
        }
        url = `${API_BASE}/api/approvals/${apprId}/reject`;
        body = {
          planner_id: "lead_planner_ui",
          reason: plannerComment.trim(),
        };
      } else if (actionType === "edit") {
        if (!plannerComment || plannerComment.trim().length < 3) {
          throw new Error("Override requires an explanatory note (minimum 3 characters).");
        }
        const tgtVal = parseFloat(overrideTarget);
        const buyVal = parseFloat(overridePurchase);
        if (isNaN(tgtVal) || tgtVal < 0 || isNaN(buyVal) || buyVal < 0) {
          throw new Error("Target and purchase quantities must be valid non-negative numbers.");
        }
        url = `${API_BASE}/api/approvals/${apprId}/edit`;
        body = {
          planner_id: "lead_planner_ui",
          edited_target_stock: tgtVal,
          edited_purchase_qty: buyVal,
          reason: plannerComment.trim(),
        };
      }

      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || "Action failed on server");
      }

      handleCloseModal();
      loadData();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to submit decision");
    } finally {
      setActionSubmitting(false);
    }
  };

  return (
    <div className="flex h-screen bg-slate-50 text-slate-900 overflow-hidden font-sans">
      {/* Sidebar Navigation */}
      <aside className="hidden lg:flex w-64 flex-col justify-between border-r border-slate-200 bg-white">
        <div>
          <div className="flex h-16 items-center px-6 border-b border-slate-200">
            <span className="text-lg font-bold tracking-tight text-slate-900">Inventory Intelligence</span>
          </div>
          <nav className="p-4 space-y-1">
            <Link href="/" className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" /></svg>
              Overview
            </Link>
            <Link href="/main-products" className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7h18M5 7v13h14V7M8 7V4h8v3m-8 5h8m-8 4h5" /></svg>
              Main Products
            </Link>
            <Link href="/recommendations" className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
              Recommendations
            </Link>
            <Link href="/procurement" className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
              Procurement
            </Link>
            <Link href="/procurement/purchase-orders" className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" /></svg>
              Draft POs
            </Link>
            <Link href="/account" className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
              Account
            </Link>
          </nav>
        </div>
        <div className="border-t border-slate-200 p-4">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block">Governance Mode</span>
          <span className="text-sm font-medium text-blue-700 flex items-center gap-1.5 mt-0.5">
            <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse"></span> Human-in-the-Loop Active
          </span>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Prominent Mandatory Safety Header */}
        <header className="border-b border-amber-300 bg-amber-50 px-6 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center rounded-md bg-amber-200 px-3 py-1 text-xs font-extrabold text-amber-950 uppercase tracking-wider shadow-xs">
              AI RECOMMENDATION — REQUIRES PLANNER APPROVAL
            </span>
            <span className="text-xs text-amber-900 font-medium hidden md:inline">
              Approval records human planner governance decisions. <strong>Strict Safety Rule: Approval does NOT create Odoo purchase orders or RFQs.</strong>
            </span>
          </div>
          <span className="text-xs font-semibold text-slate-600 bg-white/80 border border-slate-200 rounded px-2.5 py-1">
            Total Items: {formatNumber(summary?.total_items || items.length)}
          </span>
        </header>

        {/* Scrollable Main Body */}
        <main className="flex-1 overflow-y-auto p-6 lg:p-8 space-y-6">
          {/* Status KPI Summary Cards */}
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
              <span className="text-xs font-medium text-slate-500">Pending Review</span>
              <div className="mt-2 text-2xl font-bold text-amber-600">{formatNumber(summary?.status_counts["PENDING"] || 0)}</div>
              <span className="text-xs text-slate-400 mt-1 block">Awaiting Human Planner Action</span>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
              <span className="text-xs font-medium text-slate-500">Approved</span>
              <div className="mt-2 text-2xl font-bold text-emerald-600">{formatNumber(summary?.status_counts["APPROVED"] || 0)}</div>
              <span className="text-xs text-slate-400 mt-1 block">Preserved Original AI Targets</span>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
              <span className="text-xs font-medium text-slate-500">Edited / Overridden</span>
              <div className="mt-2 text-2xl font-bold text-blue-600">{formatNumber(summary?.status_counts["EDITED"] || 0)}</div>
              <span className="text-xs text-slate-400 mt-1 block">Planner Adjusted with Rationale</span>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
              <span className="text-xs font-medium text-slate-500">Rejected</span>
              <div className="mt-2 text-2xl font-bold text-rose-600">{formatNumber(summary?.status_counts["REJECTED"] || 0)}</div>
              <span className="text-xs text-slate-400 mt-1 block">Curtailed / Discontinued Items</span>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
              <span className="text-xs font-medium text-slate-500">Procurement Isolation</span>
              <div className="mt-2 text-2xl font-bold text-slate-900">0 POs Created</div>
              <span className="text-xs text-emerald-600 font-medium mt-1 block">100% Odoo DB Safe</span>
            </div>
          </section>

          {/* Queue Navigation Tabs */}
          <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs space-y-3">
            <div className="flex flex-wrap items-center gap-1.5 border-b border-slate-100 pb-3">
              <span className="text-xs font-bold text-slate-500 uppercase tracking-wider mr-2">Queues:</span>
              {[
                { id: "PENDING", label: "Pending Review", count: summary?.status_counts["PENDING"] },
                { id: "APPROVED", label: "Approved", count: summary?.status_counts["APPROVED"] },
                { id: "EDITED", label: "Edited", count: summary?.status_counts["EDITED"] },
                { id: "REJECTED", label: "Rejected", count: summary?.status_counts["REJECTED"] },
                { id: "major_target_reduction", label: "Major Reductions", count: summary?.exception_counts["major_target_reduction"] },
                { id: "major_target_increase", label: "Major Increases", count: summary?.exception_counts["major_target_increase"] },
                { id: "rising_product_risk", label: "Rising Risk", count: summary?.exception_counts["rising_product_risk"] },
                { id: "intermittent_uncertainty", label: "Intermittent", count: summary?.exception_counts["intermittent_uncertainty"] },
                { id: "zero_demand_dormant", label: "Dormant / Dead", count: summary?.exception_counts["zero_demand_dormant"] },
                { id: "unusually_large_forecast_change", label: "Large FC Delta", count: summary?.exception_counts["unusually_large_forecast_change"] },
                { id: "ALL", label: "All Catalog" },
              ].map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                    activeTab === tab.id
                      ? "bg-slate-900 text-white"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {tab.label} {tab.count !== undefined ? `(${tab.count})` : ""}
                </button>
              ))}
            </div>

            {/* Search and pattern filter */}
            <div className="flex flex-col sm:flex-row gap-3 pt-1">
              <div className="flex-1">
                <input
                  type="text"
                  placeholder="Search by Product ID or Name..."
                  value={searchTerm}
                  onChange={e => setSearchTerm(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                />
              </div>
              <div className="sm:w-56">
                <select
                  value={selectedPattern}
                  onChange={e => setSelectedPattern(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                >
                  <option value="all">All Demand Patterns</option>
                  <option value="fast_moving">Fast Moving (80% SL)</option>
                  <option value="stable/normal">Stable / Normal (80% SL)</option>
                  <option value="rising">Rising (75% SL)</option>
                  <option value="falling">Falling (75% SL)</option>
                  <option value="intermittent">Intermittent (75% SL)</option>
                  <option value="dead_stock">Dead Stock (0% SL)</option>
                </select>
              </div>
            </div>
          </section>

          {/* Side-by-Side Planner Governance Table */}
          <section className="rounded-xl border border-slate-200 bg-white shadow-xs overflow-hidden">
            <div className="border-b border-slate-200 px-6 py-4 flex items-center justify-between">
              <div>
                <h2 className="text-base font-bold text-slate-900">Planner Approval & Decision Register</h2>
                <p className="text-xs text-slate-500 mt-0.5">Showing {items.length} items (sorted by largest target difference)</p>
              </div>
              <span className="text-xs text-slate-400">Click row for full audit trail</span>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
                <thead className="bg-slate-50 font-semibold text-slate-600">
                  <tr>
                    <th className="py-3 px-4">Product</th>
                    <th className="py-3 px-3">Pattern</th>
                    <th className="py-3 px-3 bg-slate-100/70 text-slate-800">Legacy Target</th>
                    <th className="py-3 px-3 bg-slate-100/70 text-slate-800">Current Stock</th>
                    <th className="py-3 px-3 bg-blue-50/70 text-blue-900 font-bold">AI Target</th>
                    <th className="py-3 px-3 bg-blue-50/70 text-blue-900">AI Suggested Buy</th>
                    <th className="py-3 px-3">Delta</th>
                    <th className="py-3 px-3">Planner Status</th>
                    <th className="py-3 px-3">Approved / Edited Qty</th>
                    <th className="py-3 px-4 text-right">Planner Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white font-medium">
                  {loading && (
                    <tr>
                      <td colSpan={10} className="py-8 text-center text-slate-500">Loading planner approval queue...</td>
                    </tr>
                  )}
                  {!loading && items.length === 0 && (
                    <tr>
                      <td colSpan={10} className="py-8 text-center text-slate-500">No items found matching filter criteria.</td>
                    </tr>
                  )}
                  {!loading && items.map(item => {
                    const isReduction = (item.target_delta ?? 0) < 0;
                    return (
                      <tr key={item.approval_id} className="hover:bg-slate-50/80 transition-colors">
                        <td className="py-3 px-4 cursor-pointer" onClick={() => handleOpenAction(item, "detail")}>
                          <div className="font-bold text-slate-900">{item.product_name}</div>
                          <div className="text-slate-400 text-[10px]">ID: {item.product_id}</div>
                        </td>
                        <td className="py-3 px-3">
                          <span className={`inline-block rounded border px-2 py-0.5 text-[10px] font-semibold ${patternBadge(item.pattern)}`}>
                            {item.pattern}
                          </span>
                        </td>
                        <td className="py-3 px-3 bg-slate-50/50 font-bold text-slate-900">
                          {formatNumber(item.legacy_target)}m
                        </td>
                        <td className="py-3 px-3 bg-slate-50/50 text-slate-700">
                          {formatNumber(item.current_stock)}m
                        </td>
                        <td className="py-3 px-3 bg-blue-50/40 font-bold text-blue-900">
                          {formatNumber(item.target_stock)}m
                        </td>
                        <td className="py-3 px-3 bg-blue-50/40 font-semibold text-slate-900">
                          {formatNumber(item.suggested_purchase)}m
                        </td>
                        <td className="py-3 px-3">
                          <span className={`inline-block rounded font-bold px-1.5 py-0.5 text-[11px] ${
                            isReduction ? "text-cyan-700 bg-cyan-50" : "text-violet-700 bg-violet-50"
                          }`}>
                            {item.target_delta !== null && item.target_delta > 0 ? `+${formatNumber(item.target_delta)}m` : `${formatNumber(item.target_delta)}m`}
                          </span>
                        </td>
                        <td className="py-3 px-3">
                          <span className={`inline-block rounded border px-2 py-0.5 text-[10px] ${statusBadge(item.status)}`}>
                            {item.status}
                          </span>
                        </td>
                        <td className="py-3 px-3">
                          {item.status === "EDITED" ? (
                            <div>
                              <span className="font-bold text-blue-900">{formatNumber(item.edited_purchase_qty)}m</span>
                              <span className="text-[10px] text-slate-400 block">(Tgt: {formatNumber(item.edited_target_stock)}m)</span>
                            </div>
                          ) : item.status === "APPROVED" ? (
                            <span className="font-semibold text-emerald-800">{formatNumber(item.suggested_purchase)}m</span>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-right space-x-1">
                          <button
                            onClick={() => handleOpenAction(item, "approve")}
                            className="rounded bg-emerald-600 px-2 py-1 text-[11px] font-bold text-white hover:bg-emerald-700 transition-colors"
                            title="Approve Recommendation"
                          >
                            Approve
                          </button>
                          <button
                            onClick={() => handleOpenAction(item, "edit")}
                            className="rounded bg-blue-600 px-2 py-1 text-[11px] font-bold text-white hover:bg-blue-700 transition-colors"
                            title="Edit / Override Quantities"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleOpenAction(item, "reject")}
                            className="rounded bg-rose-600 px-2 py-1 text-[11px] font-bold text-white hover:bg-rose-700 transition-colors"
                            title="Reject Recommendation"
                          >
                            Reject
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </main>
      </div>

      {/* Decision Action & Audit Modal */}
      {selectedItem && actionType && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4" onClick={handleCloseModal}>
          <div className="w-full max-w-xl bg-white rounded-2xl shadow-2xl p-6 overflow-hidden space-y-5" onClick={e => e.stopPropagation()}>
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-200 pb-3">
              <div>
                <span className="text-xs uppercase font-extrabold text-blue-700 tracking-wider">
                  {actionType === "approve" && "Confirm Planner Approval"}
                  {actionType === "reject" && "Reject Recommendation"}
                  {actionType === "edit" && "Override Recommended Quantities"}
                  {actionType === "detail" && "Recommendation & Audit Trail"}
                </span>
                <h3 className="text-lg font-bold text-slate-900">{selectedItem.product_name}</h3>
                <span className="text-xs text-slate-500">Product ID: {selectedItem.product_id} | Pattern: {selectedItem.pattern}</span>
              </div>
              <button onClick={handleCloseModal} className="text-slate-400 hover:text-slate-600 rounded-lg p-1">✕</button>
            </div>

            {/* AI Recommendation Summary Box */}
            <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-4 space-y-2">
              <span className="text-xs font-bold text-blue-900 block uppercase">Original AI Recommendation (Preserved)</span>
              <div className="grid grid-cols-4 gap-2 text-xs">
                <div>
                  <span className="text-slate-500 block">Forecast (H1)</span>
                  <span className="font-bold text-slate-900">{formatNumber(selectedItem.forecast_1m)}m</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Safety Buffer</span>
                  <span className="font-bold text-slate-900">{formatNumber(selectedItem.safety_buffer)}m ({Math.round(selectedItem.service_level * 100)}%)</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Target Stock</span>
                  <span className="font-bold text-blue-900">{formatNumber(selectedItem.target_stock)}m</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Suggested Buy</span>
                  <span className="font-bold text-blue-900">{formatNumber(selectedItem.suggested_purchase)}m</span>
                </div>
              </div>
            </div>

            {/* Error banner if action failed */}
            {actionError && (
              <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800 font-semibold">
                {actionError}
              </div>
            )}

            {/* Action-Specific Inputs */}
            {actionType === "approve" && (
              <div className="space-y-3">
                <p className="text-xs text-slate-600 leading-relaxed">
                  Approving this recommendation confirms the AI target of <strong>{formatNumber(selectedItem.target_stock)}m</strong> and purchase quantity of <strong>{formatNumber(selectedItem.suggested_purchase)}m</strong>.
                </p>
                {["rising_product_risk", "intermittent_uncertainty", "major_target_reduction"].includes(selectedItem.exception_category) && (
                  <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 space-y-2">
                    <span className="font-bold block">⚠️ Exception Category Warning: {selectedItem.exception_category.replace(/_/g, " ")}</span>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={warningAck}
                        onChange={e => setWarningAck(e.target.checked)}
                        className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                      />
                      <span>I have reviewed this exception and acknowledge the risk.</span>
                    </label>
                  </div>
                )}
                <div>
                  <label className="text-xs font-bold text-slate-700 block mb-1">Approval Comment (Optional)</label>
                  <textarea
                    rows={2}
                    value={plannerComment}
                    onChange={e => setPlannerComment(e.target.value)}
                    placeholder="Enter approval notes or operational context..."
                    className="w-full rounded-lg border border-slate-200 p-2 text-xs focus:border-blue-500 focus:outline-none"
                  />
                </div>
              </div>
            )}

            {actionType === "reject" && (
              <div className="space-y-3">
                <p className="text-xs text-slate-600 leading-relaxed">
                  Rejecting will cancel purchasing intent while strictly preserving the underlying AI recommendation for reporting.
                </p>
                <div>
                  <label className="text-xs font-bold text-slate-700 block mb-1">Mandatory Rejection Reason *</label>
                  <textarea
                    rows={3}
                    value={plannerComment}
                    onChange={e => setPlannerComment(e.target.value)}
                    placeholder="Provide explicit operational reason (e.g., product discontinued, customer cancellation, excess supplier stock)..."
                    className="w-full rounded-lg border border-slate-200 p-2 text-xs focus:border-blue-500 focus:outline-none"
                    required
                  />
                </div>
              </div>
            )}

            {actionType === "edit" && (
              <div className="space-y-3">
                <p className="text-xs text-slate-600 leading-relaxed">
                  Overrides the recommended quantities. <strong>The original AI figures remain permanently stored and traceable.</strong>
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-bold text-slate-700 block mb-1">Edited Target Stock (m) *</label>
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      value={overrideTarget}
                      onChange={e => setOverrideTarget(e.target.value)}
                      className="w-full rounded-lg border border-slate-200 p-2 text-xs font-bold focus:border-blue-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-bold text-slate-700 block mb-1">Edited Purchase Qty (m) *</label>
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      value={overridePurchase}
                      onChange={e => setOverridePurchase(e.target.value)}
                      className="w-full rounded-lg border border-slate-200 p-2 text-xs font-bold focus:border-blue-500 focus:outline-none"
                    />
                  </div>
                </div>
                <div>
                  <label className="text-xs font-bold text-slate-700 block mb-1">Override Rationale / Reason *</label>
                  <textarea
                    rows={2}
                    value={plannerComment}
                    onChange={e => setPlannerComment(e.target.value)}
                    placeholder="Explain why the AI recommendation was overridden (e.g. MOQ constraint, batch roll sizing, expected promotional spike)..."
                    className="w-full rounded-lg border border-slate-200 p-2 text-xs focus:border-blue-500 focus:outline-none"
                    required
                  />
                </div>
              </div>
            )}

            {actionType === "detail" && (
              <div className="space-y-3 text-xs">
                <div>
                  <span className="font-bold text-slate-700 block">Planner Status</span>
                  <span className={`inline-block rounded border px-2 py-0.5 mt-0.5 text-xs ${statusBadge(selectedItem.status)}`}>
                    {selectedItem.status}
                  </span>
                </div>
                {selectedItem.planner_comment && (
                  <div className="rounded border border-slate-200 bg-slate-50 p-2.5">
                    <span className="font-bold text-slate-700 block mb-0.5">Planner Comment / Rationale:</span>
                    <p className="text-slate-800">{selectedItem.planner_comment}</p>
                    <span className="text-[10px] text-slate-400 mt-1 block">Reviewed by: {selectedItem.planner_id || "planner"} at {selectedItem.reviewed_at || "—"}</span>
                  </div>
                )}
              </div>
            )}

            {/* Modal Footer Controls */}
            <div className="flex items-center justify-between border-t border-slate-200 pt-4">
              <span className="text-[11px] text-slate-400">Zero Odoo writes. Safe POC DB persistence only.</span>
              <div className="space-x-2">
                <button
                  type="button"
                  onClick={handleCloseModal}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100"
                >
                  Cancel
                </button>
                {actionType !== "detail" && (
                  <button
                    type="button"
                    disabled={actionSubmitting}
                    onClick={handleSubmitDecision}
                    className={`rounded-lg px-4 py-1.5 text-xs font-bold text-white transition-colors ${
                      actionType === "approve"
                        ? "bg-emerald-600 hover:bg-emerald-700"
                        : actionType === "reject"
                        ? "bg-rose-600 hover:bg-rose-700"
                        : "bg-blue-600 hover:bg-blue-700"
                    } ${actionSubmitting ? "opacity-50 cursor-not-allowed" : ""}`}
                  >
                    {actionSubmitting ? "Submitting..." : `Confirm ${actionType.toUpperCase()}`}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
