"use client";

import React from "react";

interface StockCompositionBarProps {
  totalPhysicalStock: number | null | undefined;
  usableStock: number | null | undefined;
  cutPiecesExcluded: number | null | undefined;
  incomingStock?: number | null | undefined;
  committedStock?: number | null | undefined;
  netPosition?: number | null | undefined;
  unit?: string;
}

function formatNumber(value: number | null | undefined, maxFrac = 1) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: maxFrac }).format(value);
}

export default function StockCompositionBar({
  totalPhysicalStock = 0,
  usableStock = 0,
  cutPiecesExcluded = 0,
  incomingStock = 0,
  committedStock = 0,
  netPosition = 0,
  unit = "m",
}: StockCompositionBarProps) {
  const total = Number(totalPhysicalStock) || 0;
  const usable = Number(usableStock) || 0;
  const cut = Number(cutPiecesExcluded) || 0;
  const incoming = Number(incomingStock) || 0;
  const committed = Number(committedStock) || 0;
  const net = Number(netPosition) || (usable + incoming - committed);

  // Compute percentages for the stacked bar
  const usablePct = total > 0 ? Math.min(100, Math.max(0, (usable / total) * 100)) : 0;
  const cutPct = total > 0 ? Math.min(100, Math.max(0, (cut / total) * 100)) : 0;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 border-b border-slate-100 pb-2">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900">
            Stock Composition &amp; Inventory Position
          </h3>
          <p className="text-[11px] text-slate-500">
            Physical stock allocation between usable full rolls (≥5m) and excluded remnants (&lt;5m).
          </p>
        </div>
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 bg-slate-50 px-2.5 py-1 rounded-md border border-slate-200 self-start sm:self-auto">
          <span>Total Physical:</span>
          <span className="font-bold text-slate-900">{formatNumber(total)} {unit}</span>
        </div>
      </div>

      {/* Visual Horizontal Stacked Bar */}
      {total > 0 ? (
        <div className="space-y-2">
          {/* Progress Bar Container */}
          <div className="relative h-5 w-full rounded-lg bg-slate-100 overflow-hidden flex border border-slate-200 shadow-inner">
            {usablePct > 0 && (
              <div
                style={{ width: `${usablePct}%` }}
                className="bg-emerald-500 h-full transition-all flex items-center justify-center text-[10px] text-white font-bold"
                title={`Usable Stock: ${formatNumber(usable)} ${unit} (${usablePct.toFixed(1)}%)`}
              >
                {usablePct > 15 ? `${usablePct.toFixed(0)}%` : ""}
              </div>
            )}
            {cutPct > 0 && (
              <div
                style={{ width: `${cutPct}%` }}
                className="bg-rose-400 h-full transition-all flex items-center justify-center text-[10px] text-white font-bold"
                title={`Cut Remnants (<5m): ${formatNumber(cut)} ${unit} (${cutPct.toFixed(1)}%)`}
              >
                {cutPct > 15 ? `${cutPct.toFixed(0)}%` : ""}
              </div>
            )}
          </div>

          {/* Bar Legend & Exact Values */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs pt-0.5">
            <div className="flex items-start gap-2 p-2 rounded-lg bg-emerald-50/70 border border-emerald-200">
              <span className="h-3 w-3 rounded-full bg-emerald-500 shrink-0 mt-0.5" />
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="font-bold text-emerald-900">Usable Stock (≥5m Full Rolls)</span>
                  <span className="text-[10px] font-semibold text-emerald-700">({usablePct.toFixed(1)}%)</span>
                </div>
                <div className="text-base font-extrabold text-emerald-800 mt-0.5">
                  {formatNumber(usable)} {unit}
                </div>
                <span className="text-[10px] text-emerald-700 font-medium block mt-0.5">
                  Included in replenishment inventory position
                </span>
              </div>
            </div>

            <div className="flex items-start gap-2 p-2 rounded-lg bg-rose-50/70 border border-rose-200">
              <span className="h-3 w-3 rounded-full bg-rose-400 shrink-0 mt-0.5" />
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="font-bold text-rose-900">Cut Pieces (&lt;5m Remnants)</span>
                  <span className="text-[10px] font-semibold text-rose-700">({cutPct.toFixed(1)}%)</span>
                </div>
                <div className="text-base font-extrabold text-rose-800 mt-0.5">
                  {formatNumber(cut)} {unit}
                </div>
                <span className="text-[10px] text-rose-700 font-medium block mt-0.5">
                  Strictly excluded from replenishment calculation
                </span>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-lg bg-slate-50 p-3 text-center text-xs text-slate-500">
          No physical stock on hand.
        </div>
      )}

      {/* Auxiliary Stock Signals: Incoming, Committed, and Resulting Net Position */}
      <div className="grid grid-cols-3 gap-2 text-xs pt-1 border-t border-slate-100">
        <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
          <span className="text-slate-500 text-[10px] block font-medium">Incoming Shipments</span>
          <span className="font-bold text-slate-800 text-sm mt-0.5 block">
            +{formatNumber(incoming)} {unit}
          </span>
          <span className="text-[10px] text-slate-400 block mt-0.5">Confirmed POs</span>
        </div>

        <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
          <span className="text-slate-500 text-[10px] block font-medium">Committed Customer Demand</span>
          <span className="font-bold text-slate-800 text-sm mt-0.5 block">
            -{formatNumber(committed)} {unit}
          </span>
          <span className="text-[10px] text-slate-400 block mt-0.5">Reserved Orders</span>
        </div>

        <div className="p-2.5 rounded-lg bg-blue-50/80 border border-blue-200">
          <span className="text-blue-700 text-[10px] block font-bold">Net Inventory Position</span>
          <span className="font-extrabold text-blue-800 text-sm mt-0.5 block">
            {formatNumber(net)} {unit}
          </span>
          <span className="text-[10px] text-blue-600 block mt-0.5">(Usable + In) - Out</span>
        </div>
      </div>
    </div>
  );
}
