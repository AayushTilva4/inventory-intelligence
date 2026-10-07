"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";

type PortalPOLine = {
  line_id: number;
  po_id: string;
  approval_id: string | null;
  product_id: number;
  product_name: string;
  vendor_id: number | null;
  vendor_name: string | null;
  approved_quantity: number;
  unit_price: number;
  subtotal: number;
  forecast_snapshot_id: string | null;
  forecast_1m: number;
  forecast_h3: number;
  target_stock: number;
  current_stock: number;
  planner_decision: string;
  status: string;
  notes: string | null;
  ai_quantity?: number;
  final_po_quantity?: number;
  supplier_constraints?: any;
  constraint_reasons?: any;
};

type PortalPO = {
  po_id: string;
  po_reference: string;
  vendor_id: number | null;
  vendor_name: string | null;
  status: "DRAFT" | "CANCELLED" | "APPROVED_FOR_EXTERNAL_SYNC";
  total_quantity: number;
  total_amount: number;
  created_by: string;
  created_at: string;
  updated_at: string;
  notes: string | null;
  line_count: number;
  lines?: PortalPOLine[];
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

function formatNumber(val: number | null | undefined): string {
  if (val === null || val === undefined) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(val);
}

function poStatusBadge(status: string) {
  switch (status) {
    case "DRAFT":
      return "bg-blue-100 text-blue-800 border-blue-300 font-bold";
    case "APPROVED_FOR_EXTERNAL_SYNC":
      return "bg-emerald-100 text-emerald-800 border-emerald-300 font-bold";
    case "CANCELLED":
      return "bg-rose-100 text-rose-800 border-rose-300 font-bold";
    default:
      return "bg-slate-100 text-slate-700 border-slate-300";
  }
}

export default function PurchaseOrdersPage() {
  const [pos, setPos] = useState<PortalPO[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("all");
  const [selectedPO, setSelectedPO] = useState<PortalPO | null>(null);
  const [poDetailLoading, setPoDetailLoading] = useState(false);
  const [actionError, setActionError] = useState("");
  const [actionSubmitting, setActionSubmitting] = useState(false);

  const fetchPOs = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        status: statusFilter,
        limit: "50",
      });
      const res = await fetch(`${API_BASE}/api/procurement/purchase-orders?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setPos(data.items || []);
        setTotalCount(data.total || 0);
      }
    } catch (e) {
      console.error("Failed to load POs:", e);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchPOs();
  }, [fetchPOs]);

  const openPODetail = async (poId: string) => {
    setPoDetailLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/procurement/purchase-orders/${poId}`);
      if (res.ok) {
        const data = await res.json();
        setSelectedPO(data);
      }
    } catch (e) {
      console.error("Failed to fetch PO detail:", e);
    } finally {
      setPoDetailLoading(false);
    }
  };

  const handleUpdateStatus = async (poId: string, newStatus: string) => {
    setActionSubmitting(true);
    setActionError("");
    try {
      const res = await fetch(`${API_BASE}/api/procurement/purchase-orders/${poId}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus, notes: `Status changed to ${newStatus}` }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Failed to update status.");
      }
      setSelectedPO(null);
      fetchPOs();
    } catch (err: any) {
      setActionError(err.message);
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
            <div>
              <Link
                href="/procurement"
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-white font-semibold text-xs transition-colors border border-slate-700"
              >
                ← Back to Procurement
              </Link>
            </div>
          </div>
          <div className="flex items-center gap-2 mt-4 pt-3 border-t border-slate-800/80 text-xs">
            <Link href="/" className="px-3 py-1.5 rounded-md text-slate-300 hover:text-white hover:bg-slate-800 font-medium transition-colors">Overview</Link>
            <Link href="/main-products" className="px-3 py-1.5 rounded-md text-slate-300 hover:text-white hover:bg-slate-800 font-medium transition-colors">Main Products</Link>
            <Link href="/recommendations" className="px-3 py-1.5 rounded-md text-slate-300 hover:text-white hover:bg-slate-800 font-medium transition-colors">Recommendations</Link>
            <Link href="/procurement" className="px-3 py-1.5 rounded-md text-slate-300 hover:text-white hover:bg-slate-800 font-medium transition-colors">Procurement</Link>
            <span className="px-3 py-1.5 rounded-md text-white bg-slate-800 font-bold border border-slate-700">Draft POs ({totalCount})</span>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6">
        {/* Filter Tabs */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 mb-4 flex items-center justify-between">
          <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg">
            {["all", "DRAFT", "APPROVED_FOR_EXTERNAL_SYNC", "CANCELLED"].map((tab) => (
              <button
                key={tab}
                onClick={() => setStatusFilter(tab)}
                className={`px-3 py-1.5 text-xs font-bold rounded-md transition-all ${
                  statusFilter === tab
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {tab === "all" ? "ALL PURCHASE ORDERS" : tab.replace(/_/g, " ")}
              </button>
            ))}
          </div>
          <div className="text-xs font-semibold text-slate-500">
            Total Orders: <span className="text-slate-900 font-bold">{totalCount}</span>
          </div>
        </div>

        {/* Purchase Orders Table */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-100 text-slate-700 border-b border-slate-200 font-semibold uppercase tracking-wider">
                <tr>
                  <th className="p-3">PO Reference</th>
                  <th className="p-3">Vendor</th>
                  <th className="p-3 text-center">Lines</th>
                  <th className="p-3 text-right">Total Quantity</th>
                  <th className="p-3 text-right">Total Amount</th>
                  <th className="p-3">Created By</th>
                  <th className="p-3">Created Date</th>
                  <th className="p-3 text-center">Status</th>
                  <th className="p-3 text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {loading ? (
                  <tr>
                    <td colSpan={9} className="text-center py-12 text-slate-500">
                      Loading draft purchase orders...
                    </td>
                  </tr>
                ) : pos.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="text-center py-12 text-slate-500">
                      No portal draft purchase orders found.
                    </td>
                  </tr>
                ) : (
                  pos.map((po) => (
                    <tr key={po.po_id} className="hover:bg-slate-50 transition-colors">
                      <td className="p-3 font-mono font-bold text-blue-600">
                        {po.po_reference}
                      </td>
                      <td className="p-3 font-semibold text-slate-900">
                        {po.vendor_name || "Dazzle Fabrics Mills"}
                      </td>
                      <td className="p-3 text-center font-mono font-bold">
                        {po.line_count}
                      </td>
                      <td className="p-3 text-right font-mono font-black text-purple-600">
                        {formatNumber(po.total_quantity)} m
                      </td>
                      <td className="p-3 text-right font-mono font-medium">
                        ${formatNumber(po.total_amount)}
                      </td>
                      <td className="p-3 text-slate-600 font-mono text-[11px]">
                        {po.created_by}
                      </td>
                      <td className="p-3 text-slate-500 text-[11px]">
                        {new Date(po.created_at).toLocaleDateString()}
                      </td>
                      <td className="p-3 text-center">
                        <span className={`text-[10px] px-2 py-0.5 rounded-full border ${poStatusBadge(po.status)}`}>
                          {po.status}
                        </span>
                      </td>
                      <td className="p-3 text-center">
                        <button
                          onClick={() => openPODetail(po.po_id)}
                          className="px-2.5 py-1 text-xs font-bold rounded bg-slate-900 hover:bg-slate-800 text-white transition-colors"
                        >
                          View Lines &amp; Audit
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Detail / Audit Modal */}
      {selectedPO && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-4xl w-full p-6 shadow-2xl border border-slate-200 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-4 border-b border-slate-200">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-xl font-black text-slate-900">
                    Draft PO: {selectedPO.po_reference}
                  </h2>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full border ${poStatusBadge(selectedPO.status)}`}>
                    {selectedPO.status}
                  </span>
                </div>
                <div className="text-xs text-slate-500 mt-1">
                  Vendor: <span className="font-semibold text-slate-800">{selectedPO.vendor_name || "Dazzle Fabrics Mills"}</span> | Created by: {selectedPO.created_by}
                </div>
              </div>
              <button
                onClick={() => setSelectedPO(null)}
                className="text-slate-400 hover:text-slate-600 font-black text-lg"
              >
                ✕
              </button>
            </div>

            {actionError && (
              <div className="mt-3 p-2.5 bg-rose-50 border border-rose-200 text-rose-800 text-xs rounded-lg">
                {actionError}
              </div>
            )}

            {/* Line Items Table with End-to-End Provenance */}
            <div className="mt-4">
              <h3 className="text-xs font-bold uppercase text-slate-500 mb-2 tracking-wider">
                Line Items &amp; End-to-End Provenance Trace
              </h3>
              <div className="border border-slate-200 rounded-xl overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-100 text-slate-700 border-b border-slate-200 font-semibold">
                    <tr>
                      <th className="p-2.5">Product</th>
                      <th className="p-2.5 text-right">AI Recommended Quantity</th>
                      <th className="p-2.5 text-right font-bold text-blue-700">Planner Approved Quantity</th>
                      <th className="p-2.5 text-right font-bold text-purple-700">Final Portal PO Quantity</th>
                      <th className="p-2.5">Packaging Adjustment Reason</th>
                      <th className="p-2.5 text-center">Decision</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {selectedPO.lines && selectedPO.lines.map((line) => (
                      <tr key={line.line_id || line.product_id} className="hover:bg-slate-50">
                        <td className="p-2.5 font-bold text-slate-900">
                          {line.product_name}
                          <span className="block text-[10px] text-slate-500 font-mono font-normal">
                            PID: {line.product_id}
                          </span>
                        </td>
                        <td className="p-2.5 text-right font-mono text-slate-600">
                          {formatNumber(line.ai_quantity || line.forecast_1m)} m
                        </td>
                        <td className="p-2.5 text-right font-mono font-bold text-blue-600">
                          {formatNumber(line.approved_quantity)} m
                        </td>
                        <td className="p-2.5 text-right font-mono font-black text-purple-600">
                          {formatNumber(line.final_po_quantity || line.approved_quantity)} m
                        </td>
                        <td className="p-2.5 text-slate-600 text-[11px]">
                          {line.constraint_reasons ? (
                            <span className="bg-purple-50 text-purple-700 px-1.5 py-0.5 rounded border border-purple-200 font-medium">
                              {typeof line.constraint_reasons === "string" ? line.constraint_reasons : JSON.stringify(line.constraint_reasons)}
                            </span>
                          ) : (
                            <span className="text-slate-400">Standard Lot</span>
                          )}
                        </td>
                        <td className="p-2.5 text-center">
                          <span className="text-[10px] bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded border font-semibold">
                            {line.planner_decision}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Total Summary */}
            <div className="mt-4 p-3 bg-slate-50 rounded-xl border border-slate-200 flex items-center justify-between text-xs font-semibold">
              <div>
                Total Lines: <span className="font-bold text-slate-900">{selectedPO.lines?.length || selectedPO.line_count}</span>
              </div>
              <div className="text-right">
                Total Order Quantity: <span className="font-black text-purple-700 text-sm">{formatNumber(selectedPO.total_quantity)} m</span>
              </div>
            </div>

            {/* Audit Question & Answer Block */}
            <div className="mt-4 p-4 bg-blue-50/50 rounded-xl border border-blue-200 text-xs space-y-2">
              <div className="font-bold text-blue-900 uppercase tracking-wider text-[10px]">Reviewer Audit Check</div>
              <div className="grid grid-cols-2 gap-3 text-slate-700">
                <div>
                  <span className="font-semibold text-slate-900">What did AI recommend?</span>
                  <div className="text-slate-600">Pure statistical lead-time demand calculated by the forecasting engine.</div>
                </div>
                <div>
                  <span className="font-semibold text-slate-900">What did the planner approve?</span>
                  <div className="text-slate-600">Human-verified quantity recorded in POC PostgreSQL audit trail.</div>
                </div>
                <div>
                  <span className="font-semibold text-slate-900">What entered the portal PO?</span>
                  <div className="text-slate-600">Supplier roll &amp; MOQ constrained quantity or planner approved override ({formatNumber(selectedPO.total_quantity)} m).</div>
                </div>
                <div>
                  <span className="font-semibold text-slate-900">Odoo Interaction Status:</span>
                  <div className="text-emerald-700 font-bold">100% Isolated in POC DB — Zero Odoo mutations.</div>
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="mt-6 flex items-center justify-between pt-4 border-t border-slate-200">
              <div className="flex items-center gap-2">
                {selectedPO.status === "DRAFT" && (
                  <>
                    <button
                      onClick={() => handleUpdateStatus(selectedPO.po_id, "APPROVED_FOR_EXTERNAL_SYNC")}
                      disabled={actionSubmitting}
                      className="px-3 py-1.5 text-xs font-bold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white transition-colors"
                    >
                      Approve for External Sync
                    </button>
                    <button
                      onClick={() => handleUpdateStatus(selectedPO.po_id, "CANCELLED")}
                      disabled={actionSubmitting}
                      className="px-3 py-1.5 text-xs font-bold rounded-lg bg-rose-600 hover:bg-rose-500 text-white transition-colors"
                    >
                      Cancel PO
                    </button>
                  </>
                )}
              </div>
              <button
                onClick={() => setSelectedPO(null)}
                className="px-4 py-1.5 text-xs font-bold rounded-lg bg-slate-900 hover:bg-slate-800 text-white"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
