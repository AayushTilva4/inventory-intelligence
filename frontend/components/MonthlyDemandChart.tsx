"use client";

import React, { useState } from "react";

export type GroupHistoryPoint = {
  month: string;
  actual: number;
};

interface MonthlyDemandChartProps {
  history: GroupHistoryPoint[];
  loading?: boolean;
  effectiveRunId?: string | null;
  unit?: string;
}

function formatNumber(value: number | null | undefined, maxFrac = 1) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: maxFrac }).format(value);
}

// Compute nice upper bound for Y-axis
function getNiceMax(maxVal: number): number {
  if (maxVal <= 0) return 10;
  const magnitude = Math.pow(10, Math.floor(Math.log10(maxVal)));
  const normalized = maxVal / magnitude;
  let niceNorm: number;
  if (normalized <= 1.2) niceNorm = 1.2;
  else if (normalized <= 2) niceNorm = 2;
  else if (normalized <= 3) niceNorm = 3;
  else if (normalized <= 5) niceNorm = 5;
  else if (normalized <= 7.5) niceNorm = 7.5;
  else niceNorm = 10;
  return niceNorm * magnitude;
}

export default function MonthlyDemandChart({
  history,
  loading = false,
  effectiveRunId,
  unit = "units",
}: MonthlyDemandChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [showTable, setShowTable] = useState(false);

  if (loading) {
    return (
      <div className="flex h-44 items-center justify-center rounded-xl border border-slate-200 bg-white">
        <div className="flex flex-col items-center gap-2">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
          <span className="text-xs text-slate-500">Loading historical sales from Odoo...</span>
        </div>
      </div>
    );
  }

  // If no monthly history exists: clean empty state per requirement
  if (!history || history.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-6 text-center">
        <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-slate-400 mb-2">
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        </div>
        <p className="text-xs font-bold text-slate-700">No monthly sales history available</p>
        <p className="text-[11px] text-slate-500 mt-1 max-w-md mx-auto leading-relaxed">
          This product group has no recorded sales transactions in the live Odoo ERP ledger. Zero observations are recorded, and no demand is assumed.
        </p>
      </div>
    );
  }

  // We display the actual recorded history points without interpolation or alteration
  const points = history;
  const maxActual = Math.max(...points.map((p) => Number(p.actual) || 0), 0);
  const niceMax = getNiceMax(maxActual);

  // SVG Chart dimensions
  const svgWidth = 640;
  const svgHeight = 220;
  const padLeft = 45;
  const padRight = 20;
  const padTop = 25;
  const padBottom = 45;

  const plotWidth = svgWidth - padLeft - padRight;
  const plotHeight = svgHeight - padTop - padBottom;

  const numPoints = points.length;
  const barSlot = plotWidth / numPoints;
  const barWidth = Math.min(36, Math.max(10, barSlot * 0.65));

  // Y-axis ticks
  const yTicks = [
    { val: 0, y: padTop + plotHeight },
    { val: niceMax * 0.33, y: padTop + plotHeight * 0.67 },
    { val: niceMax * 0.67, y: padTop + plotHeight * 0.33 },
    { val: niceMax, y: padTop },
  ];

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
      {/* Header with explicit live Odoo notice and run separation */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 border-b border-slate-100 pb-2">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900">
              Monthly Demand History
            </h3>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-50 text-emerald-800 border border-emerald-200 font-semibold">
              Live Odoo Data
            </span>
          </div>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Aggregated sales actuals directly from Odoo. Forecast &amp; replenishment snapshots belong to planning run{" "}
            <span className="font-mono font-semibold text-slate-700">{effectiveRunId || "latest"}</span>.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setShowTable(!showTable)}
          className="text-[11px] font-semibold text-blue-700 hover:text-blue-800 transition-colors self-start sm:self-auto shrink-0"
        >
          {showTable ? "Show Chart ↑" : `View Exact Values (${points.length} Mo) ↓`}
        </button>
      </div>

      {!showTable ? (
        /* Vertical Bar Chart */
        <div className="relative">
          <div className="w-full overflow-x-auto">
            <svg
              viewBox={`0 0 ${svgWidth} ${svgHeight}`}
              className="w-full h-auto min-w-[500px] select-none"
              style={{ maxHeight: "240px" }}
            >
              {/* Grid Lines & Y-Axis Labels */}
              {yTicks.map((tick, idx) => (
                <g key={idx}>
                  <line
                    x1={padLeft}
                    y1={tick.y}
                    x2={svgWidth - padRight}
                    y2={tick.y}
                    stroke="#f1f5f9"
                    strokeWidth="1"
                    strokeDasharray={idx === 0 ? "none" : "3 3"}
                  />
                  <text
                    x={padLeft - 8}
                    y={tick.y + 3}
                    textAnchor="end"
                    className="fill-slate-400 font-mono text-[9px]"
                  >
                    {formatNumber(tick.val, 0)}
                  </text>
                </g>
              ))}

              {/* Baseline axis */}
              <line
                x1={padLeft}
                y1={padTop + plotHeight}
                x2={svgWidth - padRight}
                y2={padTop + plotHeight}
                stroke="#cbd5e1"
                strokeWidth="1"
              />

              {/* Data Bars */}
              {points.map((p, i) => {
                const actual = Number(p.actual) || 0;
                const isZero = actual === 0;
                const barHeight = niceMax > 0 ? (actual / niceMax) * plotHeight : 0;
                const xCenter = padLeft + (i + 0.5) * barSlot;
                const x = xCenter - barWidth / 2;
                const y = padTop + plotHeight - barHeight;
                const isHovered = hoveredIndex === i;

                return (
                  <g
                    key={p.month}
                    className="cursor-pointer transition-all"
                    onMouseEnter={() => setHoveredIndex(i)}
                    onMouseLeave={() => setHoveredIndex(null)}
                  >
                    {/* Invisible hover trigger area for easy selection */}
                    <rect
                      x={xCenter - barSlot / 2}
                      y={padTop}
                      width={barSlot}
                      height={plotHeight}
                      fill="transparent"
                    />

                    {isZero ? (
                      /* Distinct presentation for observed zero-demand months */
                      <g>
                        <circle
                          cx={xCenter}
                          cy={padTop + plotHeight}
                          r={3}
                          className="fill-slate-300 stroke-white stroke-2"
                        />
                        <line
                          x1={x}
                          y1={padTop + plotHeight}
                          x2={x + barWidth}
                          y2={padTop + plotHeight}
                          stroke="#94a3b8"
                          strokeWidth="2"
                        />
                      </g>
                    ) : (
                      /* Actual demand bar */
                      <rect
                        x={x}
                        y={y}
                        width={barWidth}
                        height={Math.max(2, barHeight)}
                        rx={2.5}
                        className={`transition-colors ${
                          isHovered
                            ? "fill-blue-700"
                            : "fill-blue-600 hover:fill-blue-700"
                        }`}
                      />
                    )}

                    {/* Month Label on X-Axis */}
                    <text
                      x={xCenter}
                      y={padTop + plotHeight + 16}
                      textAnchor="middle"
                      className={`text-[9px] font-mono transition-colors ${
                        isHovered ? "fill-blue-700 font-bold" : "fill-slate-500"
                      }`}
                    >
                      {p.month.length > 5 ? p.month.slice(2) : p.month}
                    </text>
                  </g>
                );
              })}

              {/* Tooltip on active bar */}
              {hoveredIndex !== null && points[hoveredIndex] && (
                (() => {
                  const p = points[hoveredIndex];
                  const actual = Number(p.actual) || 0;
                  const isZero = actual === 0;
                  const xCenter = padLeft + (hoveredIndex + 0.5) * barSlot;
                  const barHeight = niceMax > 0 ? (actual / niceMax) * plotHeight : 0;
                  const y = isZero ? padTop + plotHeight - 10 : padTop + plotHeight - barHeight - 10;
                  const tooltipText = isZero
                    ? `${p.month}: 0 ${unit} (Observed zero demand)`
                    : `${p.month}: ${formatNumber(actual)} ${unit}`;
                  const boxWidth = tooltipText.length * 6.5 + 16;
                  const boxX = Math.max(
                    padLeft,
                    Math.min(svgWidth - padRight - boxWidth, xCenter - boxWidth / 2)
                  );

                  return (
                    <g pointerEvents="none">
                      <rect
                        x={boxX}
                        y={Math.max(4, y - 24)}
                        width={boxWidth}
                        height={20}
                        rx={4}
                        className="fill-slate-900 shadow-md"
                      />
                      <text
                        x={boxX + boxWidth / 2}
                        y={Math.max(4, y - 24) + 14}
                        textAnchor="middle"
                        className="fill-white font-mono text-[10px] font-medium"
                      >
                        {tooltipText}
                      </text>
                    </g>
                  );
                })()
              )}
            </svg>
          </div>

          <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-slate-50">
            <span>Hover bars for exact monthly sales quantities</span>
            <span>Recorded observations: <strong>{points.length} months</strong></span>
          </div>
        </div>
      ) : (
        /* Accessible Compact Table of Exact Values */
        <div className="border border-slate-200 rounded-lg overflow-hidden">
          <div className="max-h-48 overflow-y-auto">
            <table className="min-w-full text-xs">
              <thead className="bg-slate-50 text-left text-slate-500 font-semibold border-b border-slate-200 sticky top-0">
                <tr>
                  <th className="px-4 py-2">Month Period</th>
                  <th className="px-4 py-2 text-right">Recorded Sales Demand ({unit})</th>
                  <th className="px-4 py-2 text-right">Observation Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white font-mono text-[11px]">
                {points.map((p) => {
                  const actual = Number(p.actual) || 0;
                  return (
                    <tr key={p.month} className="hover:bg-slate-50">
                      <td className="px-4 py-1.5 font-semibold text-slate-800">{p.month}</td>
                      <td className="px-4 py-1.5 text-right font-bold text-slate-900">
                        {formatNumber(actual)} {unit}
                      </td>
                      <td className="px-4 py-1.5 text-right text-[10px]">
                        {actual === 0 ? (
                          <span className="text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
                            Observed Zero Demand
                          </span>
                        ) : (
                          <span className="text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
                            Active Sales
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
