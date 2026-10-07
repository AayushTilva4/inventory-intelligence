"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import Link from "next/link";

type RecommendationItem = {
  approval_id: string;
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
  constrained_purchase_qty: number;
  constraint_multiplier: number;
  constraint_source: string;
  standard_roll_length: number;
  moq: number;
  purchase_uom: string;
  has_draft_po: boolean;
  draft_po_id: string | null;
  is_high_risk: boolean;
};

type ProcurementKPIs = {
  total_catalog_products?: number;
  products_requiring_replenishment: number;
  total_ai_recommended_quantity: number;
  total_constrained_quantity: number;
  pending_planner_review: number;
  approved_count?: number;
  high_risk_exceptions: number;
  inbound_conflict_products: number;
  missing_supplier_products: number;
  large_constraint_multipliers: number;
  portal_draft_pos: number;
  portal_draft_po_lines_created: number;
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
      return "bg-emerald-100 text-emerald-800 border-emerald-300 font-semibold";
    case "REJECTED":
      return "bg-rose-100 text-rose-800 border-rose-300 font-semibold";
    case "EDITED":
      return "bg-blue-100 text-blue-800 border-blue-300 font-semibold";
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

function constraintSourceBadge(source: string) {
  switch (source) {
    case "ODOO_VENDOR_DATA":
      return "bg-emerald-50 text-emerald-700 border-emerald-300";
    case "PORTAL_CONFIGURED":
      return "bg-blue-50 text-blue-700 border-blue-300";
    case "DEFAULT_ASSUMPTION":
      return "bg-amber-50 text-amber-700 border-amber-300";
    default:
      return "bg-rose-50 text-rose-700 border-rose-300";
  }
}

export default function ProcurementConsolePage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [kpis, setKpis] = useState<ProcurementKPIs | null>(null);
  const [items, setItems] = useState<RecommendationItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);

  // Filter States
  const [activeTab, setActiveTab] = useState<string>("PENDING");
  const [selectedPattern, setSelectedPattern] = useState<string>("all");
  const [selectedException, setSelectedException] = useState<string>("all");
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [page, setPage] = useState<number>(0);
  const pageSize = 50;

  // Selection & Bulk Actions
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bulkActionMsg, setBulkActionMsg] = useState("");

  // Drawer / Modals
  const [selectedProductDetails, setSelectedProductDetails] = useState<any | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [activeActionItem, setActiveActionItem] = useState<RecommendationItem | null>(null);
  const [actionModalType, setActionModalType] = useState<"approve" | "reject" | "edit" | "create_po" | null>(null);
  const [plannerComment, setPlannerComment] = useState("");
  const [overrideTarget, setOverrideTarget] = useState("");
  const [overridePurchase, setOverridePurchase] = useState("");
  const [warningAck, setWarningAck] = useState(false);
  const [actionSubmitting, setActionSubmitting] = useState(false);
  const [actionError, setActionError] = useState("");

  // Fetch KPIs
  const fetchKPIs = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/procurement/kpis`);
      if (res.ok) {
        const data = await res.json();
        setKpis(data);
      }
    } catch (e) {
      console.error("Failed to load KPIs:", e);
    }
  }, []);

  // Fetch Recommendations
  const fetchRecommendations = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({
        status: activeTab,
        pattern: selectedPattern,
        exception_category: selectedException,
        limit: pageSize.toString(),
        offset: (page * pageSize).toString(),
      });
      if (searchTerm.trim()) {
        params.append("search", searchTerm.trim());
      }
      const res = await fetch(`${API_BASE}/api/procurement/recommendations?${params.toString()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to load recommendations`);
      const data = await res.json();
      setItems(data.items || []);
      setTotalCount(data.total || 0);
    } catch (err: any) {
      setError(err.message || "Failed to load procurement recommendations.");
    } finally {
      setLoading(false);
    }
  }, [activeTab, selectedPattern, selectedException, searchTerm, page]);

  useEffect(() => {
    fetchKPIs();
  }, [fetchKPIs]);

  useEffect(() => {
    fetchRecommendations();
  }, [fetchRecommendations]);

  // Open Product Details Drawer
  const openProductDetails = async (productId: number) => {
    setDrawerLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/procurement/product/${productId}/details`);
      if (res.ok) {
        const data = await res.json();
        setSelectedProductDetails(data);
      }
    } catch (e) {
      console.error("Error fetching product details:", e);
    } finally {
      setDrawerLoading(false);
    }
  };

  // Selection Checkbox Handler
  const toggleSelectAll = () => {
    if (selectedIds.length === items.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(items.map((i) => i.approval_id));
    }
  };

  const toggleSelectOne = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  // Bulk Approval Handler
  const handleBulkApprove = async () => {
    if (selectedIds.length === 0) return;
    setBulkActionMsg("");
    setActionSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/procurement/bulk-approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approval_ids: selectedIds,
          planner_id: "senior_inventory_planner",
          comment: "Bulk approved via Procurement Console",
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Bulk approval failed.");

      let msg = `Approved ${data.approved_count} low-risk items.`;
      if (data.blocked_count > 0) {
        msg += ` Blocked ${data.blocked_count} high-risk items requiring individual review.`;
      }
      setBulkActionMsg(msg);
      setSelectedIds([]);
      fetchKPIs();
      fetchRecommendations();
    } catch (err: any) {
      setBulkActionMsg(`Error: ${err.message}`);
    } finally {
      setActionSubmitting(false);
    }
  };

  // Bulk Draft PO Creation Handler
  const handleBulkCreatePO = async () => {
    if (selectedIds.length === 0) return;
    setActionSubmitting(true);
    setBulkActionMsg("");
    try {
      const res = await fetch(`${API_BASE}/api/procurement/purchase-orders/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approval_ids: selectedIds,
          planner_id: "senior_inventory_planner",
          notes: "Bulk Draft PO created from Procurement Console",
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "PO creation failed.");
      setBulkActionMsg(`Portal Draft PO ${data.po_reference} created successfully for ${selectedIds.length} items.`);
      setSelectedIds([]);
      fetchKPIs();
      fetchRecommendations();
    } catch (err: any) {
      setBulkActionMsg(`PO Creation Error: ${err.message}`);
    } finally {
      setActionSubmitting(false);
    }
  };

  // Single Action Submit
  const handleSingleActionSubmit = async () => {
    if (!activeActionItem) return;
    setActionError("");
    setActionSubmitting(true);

    try {
      let endpoint = "";
      let body: any = {};

      if (actionModalType === "approve") {
        endpoint = `${API_BASE}/api/procurement/approve`;
        body = {
          approval_id: activeActionItem.approval_id,
          planner_id: "senior_inventory_planner",
          comment: plannerComment || "Approved via Procurement Console",
          warning_acknowledged: warningAck,
        };
      } else if (actionModalType === "reject") {
        endpoint = `${API_BASE}/api/procurement/reject`;
        body = {
          approval_id: activeActionItem.approval_id,
          planner_id: "senior_inventory_planner",
          reason: plannerComment,
        };
      } else if (actionModalType === "edit") {
        endpoint = `${API_BASE}/api/procurement/edit`;
        body = {
          approval_id: activeActionItem.approval_id,
          planner_id: "senior_inventory_planner",
          edited_target_stock: parseFloat(overrideTarget),
          edited_purchase_qty: parseFloat(overridePurchase),
          reason: plannerComment,
        };
      } else if (actionModalType === "create_po") {
        endpoint = `${API_BASE}/api/procurement/purchase-orders/create`;
        body = {
          approval_ids: [activeActionItem.approval_id],
          planner_id: "senior_inventory_planner",
          notes: plannerComment || "Single Draft PO created via Procurement Console",
        };
      }

      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Action failed.");

      setActionModalType(null);
      setActiveActionItem(null);
      fetchKPIs();
      fetchRecommendations();
    } catch (err: any) {
      setActionError(err.message || "Action failed.");
    } finally {
      setActionSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 pb-12">
      {/* Top Banner */}
      <div className="bg-slate-900 text-white border-b border-slate-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-black tracking-tight text-white">
                  INVENTORY INTELLIGENCE
                </h1>
                <span className="text-xs uppercase px-2.5 py-0.5 rounded-full font-bold bg-amber-500 text-slate-950">
                  DEMO / PORTAL PROCUREMENT MODE
                </span>
              </div>
              <p className="text-xs text-slate-300 mt-1 font-medium">
                AI recommendations are advisory. Planner approval is required. Odoo is read-only. Portal POs are not synchronized to Odoo.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <Link
                href="/procurement/purchase-orders"
                className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition-colors shadow-sm"
              >
                Draft POs ({kpis?.portal_draft_pos || 0}) →
              </Link>
            </div>
          </div>
          <div className="flex items-center gap-2 mt-4 pt-3 border-t border-slate-800/80 text-xs">
            <Link href="/" className="px-3 py-1.5 rounded-md text-slate-300 hover:text-white hover:bg-slate-800 font-medium transition-colors">Overview</Link>
            <Link href="/main-products" className="px-3 py-1.5 rounded-md text-slate-300 hover:text-white hover:bg-slate-800 font-medium transition-colors">Main Products</Link>
            <Link href="/recommendations" className="px-3 py-1.5 rounded-md text-slate-300 hover:text-white hover:bg-slate-800 font-medium transition-colors">Recommendations</Link>
            <span className="px-3 py-1.5 rounded-md text-white bg-slate-800 font-bold border border-slate-700">Procurement</span>
            <Link href="/procurement/purchase-orders" className="px-3 py-1.5 rounded-md text-slate-300 hover:text-white hover:bg-slate-800 font-medium transition-colors">Draft POs ({kpis?.portal_draft_pos || 0})</Link>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6">
        {/* KPI Cards (10 Canonical Metrics) */}
        {kpis && (
          <div className="space-y-3 mb-6">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
              <div className="bg-white rounded-xl p-3.5 border border-slate-200 shadow-sm">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Total Products</div>
                <div className="text-2xl font-black text-slate-900 mt-1">{formatNumber(kpis.total_catalog_products || 1000)}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">Physical catalog scope</div>
              </div>
              <div className="bg-white rounded-xl p-3.5 border border-slate-200 shadow-sm">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Replenishment Count</div>
                <div className="text-2xl font-black text-slate-900 mt-1">{formatNumber(kpis.products_requiring_replenishment)}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">Products with AI buy &gt; 0</div>
              </div>
              <div className="bg-white rounded-xl p-3.5 border border-slate-200 shadow-sm">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">AI Recommended Qty</div>
                <div className="text-2xl font-black text-blue-600 mt-1">{formatNumber(kpis.total_ai_recommended_quantity)} m</div>
                <div className="text-[11px] text-slate-500 mt-0.5">Statistical forecast need</div>
              </div>
              <div className="bg-white rounded-xl p-3.5 border border-slate-200 shadow-sm">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Supplier Constrained</div>
                <div className="text-2xl font-black text-purple-600 mt-1">{formatNumber(kpis.total_constrained_quantity)} m</div>
                <div className="text-[11px] text-slate-500 mt-0.5">Roll &amp; MOQ rounded</div>
              </div>
              <div className="bg-white rounded-xl p-3.5 border border-slate-200 shadow-sm">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Pending Approvals</div>
                <div className="text-2xl font-black text-amber-600 mt-1">{formatNumber(kpis.pending_planner_review)}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">Awaiting planner action</div>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
              <div className="bg-white rounded-xl p-3.5 border border-slate-200 shadow-sm">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">High-Risk Exceptions</div>
                <div className="text-2xl font-black text-rose-600 mt-1">{formatNumber(kpis.high_risk_exceptions)}</div>
                <div className="text-[11px] text-rose-700 font-medium mt-0.5">Individual review required</div>
              </div>
              <div className="bg-white rounded-xl p-3.5 border border-slate-200 shadow-sm">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Inbound Conflicts</div>
                <div className="text-2xl font-black text-amber-600 mt-1">{formatNumber(kpis.inbound_conflict_products)}</div>
                <div className="text-[11px] text-amber-700 font-medium mt-0.5">Pending PO in Odoo</div>
              </div>
              <div className="bg-white rounded-xl p-3.5 border border-slate-200 shadow-sm">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Missing Suppliers</div>
                <div className="text-2xl font-black text-slate-700 mt-1">{formatNumber(kpis.missing_supplier_products)}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">Vendor info unassigned</div>
              </div>
              <div className="bg-white rounded-xl p-3.5 border border-slate-200 shadow-sm">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Multipliers &gt; 3x</div>
                <div className="text-2xl font-black text-rose-600 mt-1">{formatNumber(kpis.large_constraint_multipliers)}</div>
                <div className="text-[11px] text-rose-700 font-medium mt-0.5">Packaging inflation check</div>
              </div>
              <div className="bg-white rounded-xl p-3.5 border border-slate-200 shadow-sm">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Portal Draft POs</div>
                <div className="text-2xl font-black text-emerald-600 mt-1">{formatNumber(kpis.portal_draft_pos)}</div>
                <div className="text-[11px] text-emerald-700 font-medium mt-0.5">POC PostgreSQL records</div>
              </div>
            </div>
          </div>
        )}

        {/* Filter Toolbar */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 mb-4">
          <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-4">
            {/* Status Tabs */}
            <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg">
              {["PENDING", "APPROVED", "EDITED", "REJECTED", "all"].map((tab) => (
                <button
                  key={tab}
                  onClick={() => {
                    setActiveTab(tab);
                    setPage(0);
                  }}
                  className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all ${
                    activeTab === tab
                      ? "bg-white text-slate-900 shadow-sm"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {tab === "all" ? "ALL DECISIONS" : tab}
                </button>
              ))}
            </div>

            {/* Dropdown Filters & Search */}
            <div className="flex flex-wrap items-center gap-3">
              <select
                value={selectedPattern}
                onChange={(e) => {
                  setSelectedPattern(e.target.value);
                  setPage(0);
                }}
                className="text-xs bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 font-medium text-slate-700"
              >
                <option value="all">All Demand Patterns</option>
                <option value="fast_moving">Fast Moving (80% SL)</option>
                <option value="stable/normal">Stable / Normal (80% SL)</option>
                <option value="rising">Rising (75% SL)</option>
                <option value="falling">Falling (75% SL)</option>
                <option value="intermittent">Intermittent (75% SL)</option>
                <option value="dead_stock">Dead Stock (0% SL)</option>
              </select>

              <select
                value={selectedException}
                onChange={(e) => {
                  setSelectedException(e.target.value);
                  setPage(0);
                }}
                className="text-xs bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1.5 font-medium text-slate-700"
              >
                <option value="all">All Exception Types</option>
                <option value="constraint_multiplier_gt_3x">Multiplier &gt;3x Alert</option>
                <option value="possible_inbound_stock_conflict">Inbound Stock Conflict</option>
                <option value="missing_supplier">Missing Supplier</option>
                <option value="group_stock_available_elsewhere">Group Stock Available</option>
                <option value="uncertain_group_substitutability">Uncertain Substitutability</option>
                <option value="stockout_suppressed_risk">Stockout Risk</option>
              </select>

              <input
                type="text"
                placeholder="Search SKU or Name..."
                value={searchTerm}
                onChange={(e) => {
                  setSearchTerm(e.target.value);
                  setPage(0);
                }}
                className="text-xs bg-slate-50 border border-slate-300 rounded-lg px-3 py-1.5 w-48 text-slate-900"
              />
            </div>
          </div>

          {/* Bulk Action Bar */}
          {selectedIds.length > 0 && (
            <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between bg-slate-50 px-3 py-2 rounded-lg">
              <div className="text-xs font-semibold text-slate-700">
                <span className="text-blue-600 font-bold">{selectedIds.length}</span> items selected
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleBulkApprove}
                  disabled={actionSubmitting}
                  className="px-3 py-1 text-xs font-bold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white transition-colors"
                >
                  Approve Selected (Low-Risk Only)
                </button>
                <button
                  onClick={handleBulkCreatePO}
                  disabled={actionSubmitting}
                  className="px-3 py-1 text-xs font-bold rounded-lg bg-blue-600 hover:bg-blue-500 text-white transition-colors"
                >
                  Create Draft PO for Selected
                </button>
              </div>
            </div>
          )}

          {bulkActionMsg && (
            <div className="mt-2 text-xs font-medium text-blue-700 bg-blue-50 p-2 rounded border border-blue-200">
              {bulkActionMsg}
            </div>
          )}
        </div>

        {/* Main Procurement Table */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-100 text-slate-700 border-b border-slate-200 font-semibold uppercase tracking-wider">
                <tr>
                  <th className="p-3 w-8">
                    <input
                      type="checkbox"
                      checked={selectedIds.length === items.length && items.length > 0}
                      onChange={toggleSelectAll}
                      className="rounded text-blue-600"
                    />
                  </th>
                  <th className="p-3">Product / SKU</th>
                  <th className="p-3">Pattern</th>
                  <th className="p-3 text-right">Current Stock</th>
                  <th className="p-3 text-right">FC 1M</th>
                  <th className="p-3 text-right">FC H3</th>
                  <th className="p-3 text-right">Target</th>
                  <th className="p-3 text-right font-bold text-blue-700">AI Recommended Quantity</th>
                  <th className="p-3 text-right font-bold text-purple-700">Supplier-Constrained Quantity</th>
                  <th className="p-3 text-center">Multiplier</th>
                  <th className="p-3">Exceptions / Warnings</th>
                  <th className="p-3 text-center">Status</th>
                  <th className="p-3 text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {loading ? (
                  <tr>
                    <td colSpan={13} className="text-center py-12 text-slate-500">
                      Loading procurement recommendations...
                    </td>
                  </tr>
                ) : items.length === 0 ? (
                  <tr>
                    <td colSpan={13} className="text-center py-12 text-slate-500">
                      No recommendations found for the selected filters.
                    </td>
                  </tr>
                ) : (
                  items.map((item) => (
                    <tr
                      key={item.approval_id}
                      className={`hover:bg-slate-50/80 transition-colors ${
                        item.is_high_risk ? "bg-amber-50/20" : ""
                      }`}
                    >
                      <td className="p-3">
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(item.approval_id)}
                          onChange={() => toggleSelectOne(item.approval_id)}
                          className="rounded text-blue-600"
                        />
                      </td>
                      <td className="p-3">
                        <button
                          onClick={() => openProductDetails(item.product_id)}
                          className="text-left font-bold text-slate-900 hover:text-blue-600 hover:underline block truncate max-w-xs"
                        >
                          {item.product_name}
                        </button>
                        <span className="text-[10px] text-slate-500 font-mono">
                          ID: {item.product_id}
                        </span>
                      </td>
                      <td className="p-3">
                        <span
                          className={`text-[10px] uppercase px-2 py-0.5 rounded-full border ${patternBadge(
                            item.pattern
                          )}`}
                        >
                          {item.pattern.replace("_", " ")}
                        </span>
                      </td>
                      <td className="p-3 text-right font-mono font-medium">
                        {formatNumber(item.current_stock)} m
                      </td>
                      <td className="p-3 text-right font-mono">{formatNumber(item.forecast_1m)} m</td>
                      <td className="p-3 text-right font-mono">{formatNumber(item.forecast_h3)} m</td>
                      <td className="p-3 text-right font-mono font-medium">
                        {formatNumber(item.target_stock)} m
                      </td>
                      <td className="p-3 text-right font-mono font-black text-blue-600">
                        {formatNumber(item.suggested_purchase)} m
                      </td>
                      <td className="p-3 text-right font-mono font-black text-purple-600">
                        {formatNumber(item.constrained_purchase_qty)} m
                      </td>
                      <td className="p-3 text-center">
                        <span
                          className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                            item.constraint_multiplier > 3.0
                              ? "bg-rose-100 text-rose-800 border border-rose-300"
                              : item.constraint_multiplier > 2.0
                              ? "bg-amber-100 text-amber-800"
                              : "text-slate-600"
                          }`}
                        >
                          {item.constraint_multiplier}x
                        </span>
                      </td>
                      <td className="p-3">
                        <div className="flex flex-wrap gap-1 max-w-xs">
                          {item.constraint_multiplier > 3.0 && (
                            <span className="text-[10px] bg-rose-50 text-rose-700 px-1.5 py-0.5 rounded border border-rose-200 font-semibold">
                              &gt;3x Inflation
                            </span>
                          )}
                          <span className="text-[10px] bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded">
                            {item.exception_category.replace(/_/g, " ")}
                          </span>
                        </div>
                      </td>
                      <td className="p-3 text-center">
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded-full border ${statusBadge(
                            item.status
                          )}`}
                        >
                          {item.status}
                        </span>
                      </td>
                      <td className="p-3 text-center">
                        <div className="flex items-center justify-center gap-1.5">
                          <button
                            onClick={() => openProductDetails(item.product_id)}
                            className="px-2 py-1 text-[11px] font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 rounded transition-colors"
                          >
                            Details
                          </button>
                          {item.status === "PENDING" && (
                            <button
                              onClick={() => {
                                setActiveActionItem(item);
                                setActionModalType("approve");
                                setWarningAck(false);
                                setActionError("");
                              }}
                              className="px-2 py-1 text-[11px] font-bold bg-emerald-600 hover:bg-emerald-500 text-white rounded transition-colors"
                            >
                              Approve
                            </button>
                          )}
                          {item.status === "APPROVED" && (
                            <button
                              onClick={() => {
                                setActiveActionItem(item);
                                setActionModalType("create_po");
                                setActionError("");
                              }}
                              className="px-2 py-1 text-[11px] font-bold bg-blue-600 hover:bg-blue-500 text-white rounded transition-colors"
                            >
                              + Draft PO
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="p-3 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs text-slate-600">
            <div>
              Showing {items.length} of {totalCount} records
            </div>
            <div className="flex items-center gap-2">
              <button
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
                className="px-2.5 py-1 border border-slate-300 rounded bg-white hover:bg-slate-50 disabled:opacity-50"
              >
                Previous
              </button>
              <span>
                Page {page + 1} of {Math.max(1, Math.ceil(totalCount / pageSize))}
              </span>
              <button
                disabled={(page + 1) * pageSize >= totalCount}
                onClick={() => setPage((p) => p + 1)}
                className="px-2.5 py-1 border border-slate-300 rounded bg-white hover:bg-slate-50 disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Product Detail Drawer */}
      {selectedProductDetails && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex justify-end">
          <div className="w-full max-w-2xl bg-white h-full shadow-2xl p-6 overflow-y-auto flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between pb-4 border-b border-slate-200">
                <div>
                  <h2 className="text-lg font-black text-slate-900">
                    {selectedProductDetails.product_name}
                  </h2>
                  <div className="text-xs text-slate-500 font-mono">
                    SKU: {selectedProductDetails.sku} | ID: {selectedProductDetails.product_id}
                  </div>
                </div>
                <button
                  onClick={() => setSelectedProductDetails(null)}
                  className="text-slate-400 hover:text-slate-600 font-black text-lg"
                >
                  ✕
                </button>
              </div>

              {/* Section A: Demand */}
              <div className="mt-4 p-4 bg-slate-50 rounded-xl border border-slate-200">
                <div className="text-xs font-bold uppercase text-slate-500 mb-2">A. Demand Velocity</div>
                <div className="grid grid-cols-4 gap-2 text-center text-xs">
                  <div className="p-2 bg-white rounded border">
                    <div className="text-slate-400 text-[10px]">Recent 1M</div>
                    <div className="font-bold text-slate-900">{formatNumber(selectedProductDetails.section_a_demand.recent_1m_demand)} m</div>
                  </div>
                  <div className="p-2 bg-white rounded border">
                    <div className="text-slate-400 text-[10px]">Recent 3M</div>
                    <div className="font-bold text-slate-900">{formatNumber(selectedProductDetails.section_a_demand.recent_3m_demand)} m</div>
                  </div>
                  <div className="p-2 bg-white rounded border">
                    <div className="text-slate-400 text-[10px]">Recent 6M</div>
                    <div className="font-bold text-slate-900">{formatNumber(selectedProductDetails.section_a_demand.recent_6m_demand)} m</div>
                  </div>
                  <div className="p-2 bg-white rounded border">
                    <div className="text-slate-400 text-[10px]">Annual (12M)</div>
                    <div className="font-bold text-slate-900">{formatNumber(selectedProductDetails.section_a_demand.recent_12m_demand)} m</div>
                  </div>
                </div>
                <div className="text-[11px] text-slate-500 mt-2 font-mono">
                  Pattern: {selectedProductDetails.section_a_demand.demand_pattern} | Model: {selectedProductDetails.section_a_demand.selected_model}
                </div>
              </div>

              {/* Section B: Forecast */}
              <div className="mt-4 p-4 bg-slate-50 rounded-xl border border-slate-200">
                <div className="text-xs font-bold uppercase text-slate-500 mb-2">B. Forecast Projections</div>
                <div className="grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="p-2 bg-white rounded border">
                    <div className="text-slate-400 text-[10px]">Forecast H1</div>
                    <div className="font-bold text-blue-700">{formatNumber(selectedProductDetails.section_b_forecast.forecast_1m)} m</div>
                  </div>
                  <div className="p-2 bg-white rounded border">
                    <div className="text-slate-400 text-[10px]">Forecast H3 (Lead-Time)</div>
                    <div className="font-bold text-blue-700">{formatNumber(selectedProductDetails.section_b_forecast.forecast_h3)} m</div>
                  </div>
                  <div className="p-2 bg-white rounded border">
                    <div className="text-slate-400 text-[10px]">Safety Buffer</div>
                    <div className="font-bold text-emerald-700">{formatNumber(selectedProductDetails.section_b_forecast.safety_buffer)} m</div>
                  </div>
                </div>
                <p className="text-[11px] text-slate-500 mt-2">
                  {selectedProductDetails.section_b_forecast.forecast_explanation}
                </p>
              </div>

              {/* Section C: Inventory & Groups */}
              <div className="mt-4 p-4 bg-slate-50 rounded-xl border border-slate-200">
                <div className="text-xs font-bold uppercase text-slate-500 mb-2">C. Inventory &amp; Group Stock</div>
                <div className="grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="p-2 bg-white rounded border">
                    <div className="text-slate-400 text-[10px]">Current Stock</div>
                    <div className="font-bold text-slate-900">{formatNumber(selectedProductDetails.section_c_inventory.current_stock)} m</div>
                  </div>
                  <div className="p-2 bg-white rounded border">
                    <div className="text-slate-400 text-[10px]">Group Total Stock</div>
                    <div className="font-bold text-indigo-700">{formatNumber(selectedProductDetails.section_c_inventory.group_stock_total)} m</div>
                  </div>
                  <div className="p-2 bg-white rounded border">
                    <div className="text-slate-400 text-[10px]">Target Stock</div>
                    <div className="font-bold text-slate-900">{formatNumber(selectedProductDetails.section_c_inventory.target_stock)} m</div>
                  </div>
                </div>
                {selectedProductDetails.section_c_inventory.inbound_warning && (
                  <div className="mt-2 p-2 bg-amber-50 border border-amber-300 rounded text-amber-800 text-xs font-semibold">
                    ⚠ Inbound Stock Conflict: {formatNumber(selectedProductDetails.section_c_inventory.inbound_pending_qty)} m already in transit in Odoo.
                  </div>
                )}
              </div>

              {/* Section D: Procurement Constraints */}
              <div className="mt-4 p-4 bg-slate-50 rounded-xl border border-slate-200">
                <div className="text-xs font-bold uppercase text-slate-500 mb-2">D. Supplier Packaging Constraints</div>
                <div className="grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="p-2 bg-white rounded border">
                    <div className="text-slate-400 text-[10px]">AI Recommended Quantity</div>
                    <div className="font-bold text-blue-700">{formatNumber(selectedProductDetails.section_d_procurement.suggested_purchase_ai)} m</div>
                  </div>
                  <div className="p-2 bg-white rounded border">
                    <div className="text-slate-400 text-[10px]">Supplier-Constrained Quantity</div>
                    <div className="font-bold text-purple-700">{formatNumber(selectedProductDetails.section_d_procurement.constrained_purchase_qty)} m</div>
                  </div>
                  <div className="p-2 bg-white rounded border">
                    <div className="text-slate-400 text-[10px]">Multiplier</div>
                    <div className="font-bold text-rose-700">{selectedProductDetails.section_d_procurement.constraint_multiplier}x</div>
                  </div>
                </div>
                <div className="mt-2 flex items-center justify-between text-xs">
                  <span className="text-slate-500">Roll: {selectedProductDetails.section_d_procurement.standard_roll_length}m | MOQ: {selectedProductDetails.section_d_procurement.moq}m</span>
                  <span className={`text-[10px] px-2 py-0.5 rounded border font-semibold ${constraintSourceBadge(selectedProductDetails.section_d_procurement.constraint_source)}`}>
                    Source: {selectedProductDetails.section_d_procurement.constraint_source}
                  </span>
                </div>
              </div>

              {/* Section E: Decision & Audit Trail */}
              <div className="mt-4 p-4 bg-slate-50 rounded-xl border border-slate-200">
                <div className="text-xs font-bold uppercase text-slate-500 mb-2">E. Decision Governance</div>
                <div className="text-xs text-slate-700">
                  <div>Status: <span className="font-bold">{selectedProductDetails.section_e_decision.status}</span></div>
                  <div>Planner Approved Quantity: <span className="font-bold">{formatNumber(selectedProductDetails.section_e_decision.approved_quantity)} m</span></div>
                  {selectedProductDetails.section_e_decision.planner_comment && (
                    <div className="mt-1 italic text-slate-600">&ldquo;{selectedProductDetails.section_e_decision.planner_comment}&rdquo;</div>
                  )}
                </div>
              </div>
            </div>

            <div className="pt-4 border-t border-slate-200">
              <button
                onClick={() => setSelectedProductDetails(null)}
                className="w-full py-2 bg-slate-900 hover:bg-slate-800 text-white font-bold rounded-lg text-xs"
              >
                Close Drawer
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Action Modals (Approve, Edit, Reject, Create PO) */}
      {actionModalType && activeActionItem && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-200">
            <h3 className="text-lg font-black text-slate-900">
              {actionModalType === "approve" && "Approve Recommendation"}
              {actionModalType === "reject" && "Reject Recommendation"}
              {actionModalType === "edit" && "Override / Edit Quantities"}
              {actionModalType === "create_po" && "Create Portal Draft PO"}
            </h3>
            <p className="text-xs text-slate-500 mt-1">
              Product: <span className="font-semibold text-slate-800">{activeActionItem.product_name}</span> (ID: {activeActionItem.product_id})
            </p>

            {actionError && (
              <div className="mt-3 p-2.5 bg-rose-50 border border-rose-200 text-rose-800 text-xs rounded-lg">
                {actionError}
              </div>
            )}

            {/* High-Risk Warning in Approve */}
            {actionModalType === "approve" && activeActionItem.is_high_risk && (
              <div className="mt-3 p-3 bg-amber-50 border border-amber-300 rounded-lg text-xs text-amber-900">
                <div className="font-bold">⚠ HIGH-RISK PROCUREMENT EXCEPTION</div>
                <div className="text-[11px] mt-0.5">
                  Packaging multiplier is {activeActionItem.constraint_multiplier}x (AI buy {activeActionItem.suggested_purchase}m vs roll {activeActionItem.constrained_purchase_qty}m).
                </div>
                <label className="flex items-center gap-2 mt-2 text-xs font-semibold">
                  <input
                    type="checkbox"
                    checked={warningAck}
                    onChange={(e) => setWarningAck(e.target.checked)}
                    className="rounded text-amber-600"
                  />
                  I acknowledge the high-risk constraint inflation
                </label>
              </div>
            )}

            {/* Edit Inputs */}
            {actionModalType === "edit" && (
              <div className="mt-3 space-y-2">
                <div>
                  <label className="text-xs font-semibold text-slate-700">Planner Overridden Target Stock (m)</label>
                  <input
                    type="number"
                    value={overrideTarget}
                    onChange={(e) => setOverrideTarget(e.target.value)}
                    placeholder={activeActionItem.target_stock.toString()}
                    className="w-full text-xs p-2 border rounded-lg mt-1"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-700">Planner Approved Quantity (m)</label>
                  <input
                    type="number"
                    value={overridePurchase}
                    onChange={(e) => setOverridePurchase(e.target.value)}
                    placeholder={activeActionItem.suggested_purchase.toString()}
                    className="w-full text-xs p-2 border rounded-lg mt-1"
                  />
                </div>
                {/* Warning for Q_approved < Q_constrained */}
                {overridePurchase !== "" && parseFloat(overridePurchase) < activeActionItem.constrained_purchase_qty && (
                  <div className="p-2.5 bg-amber-50 border border-amber-300 text-amber-900 text-xs rounded-lg font-medium">
                    ⚠️ Planner override is below supplier-constrained quantity.
                    <div className="text-[11px] text-amber-700 mt-0.5">
                      Standard constraint requires {activeActionItem.constrained_purchase_qty}m. A mandatory reason is required to record the override.
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Comment / Reason */}
            <div className="mt-3">
              <label className="text-xs font-semibold text-slate-700">
                {actionModalType === "reject" ? "Mandatory Rejection Reason" : actionModalType === "edit" ? "Mandatory Override Reason" : "Planner Comment (Optional)"}
              </label>
              <textarea
                value={plannerComment}
                onChange={(e) => setPlannerComment(e.target.value)}
                rows={3}
                placeholder="Enter justification..."
                className="w-full text-xs p-2 border rounded-lg mt-1"
              />
            </div>

            {/* Create PO Preview */}
            {actionModalType === "create_po" && (
              <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-900 space-y-1">
                <div className="font-bold">PORTAL DRAFT PO PREVIEW</div>
                <div>AI Recommended Quantity: {activeActionItem.suggested_purchase} m</div>
                <div>Planner Approved Quantity: {activeActionItem.edited_purchase_qty || activeActionItem.suggested_purchase} m</div>
                <div>Final Portal PO Quantity: <span className="font-bold">{activeActionItem.constrained_purchase_qty} m</span></div>
                <div className="text-[10px] text-blue-700 font-medium">Record will exist strictly in POC PostgreSQL. Zero Odoo writes.</div>
              </div>
            )}

            <div className="mt-5 flex items-center justify-end gap-2">
              <button
                onClick={() => setActionModalType(null)}
                className="px-3 py-1.5 text-xs text-slate-600 hover:text-slate-800 font-semibold"
              >
                Cancel
              </button>
              <button
                onClick={handleSingleActionSubmit}
                disabled={actionSubmitting || (actionModalType === "approve" && activeActionItem.is_high_risk && !warningAck)}
                className="px-4 py-1.5 text-xs font-bold rounded-lg bg-slate-900 hover:bg-slate-800 text-white disabled:opacity-50"
              >
                {actionSubmitting ? "Submitting..." : "Confirm Action"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
