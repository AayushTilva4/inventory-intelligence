"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import AppLayout, { User } from "@/components/AppLayout";
import { usePlanningRun } from "@/components/PlanningRunContext";

function formatDate(dateStr: string | null | undefined) {
  if (!dateStr) return "—";
  try {
    const d = new Date(dateStr);
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  } catch {
    return dateStr;
  }
}

export default function AccountPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const { activeEffectiveRun, runs } = usePlanningRun();

  useEffect(() => {
    const storedUser = sessionStorage.getItem("user");
    if (storedUser) {
      try {
        setUser(JSON.parse(storedUser));
      } catch {
        // ignore
      }
    }
  }, []);

  const handleLogout = () => {
    sessionStorage.removeItem("auth_token");
    sessionStorage.removeItem("user");
    sessionStorage.removeItem("selected_run_id");
    router.push("/login");
  };

  return (
    <AppLayout>
      <div className="space-y-6 max-w-3xl mx-auto">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">
            Account &amp; System Configuration
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Planner credentials, planning cycle execution status, and enterprise system parameters.
          </p>
        </div>

        {/* User Profile Card */}
        <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-xs">
          <div className="border-b border-slate-200 px-6 py-4 bg-slate-50 flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-900">Authenticated Planner Profile</h2>
            <span className="rounded bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800 border border-emerald-200">
              Active Session
            </span>
          </div>
          <div className="p-6 space-y-4 text-sm">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-1">
              <span className="text-slate-500 font-medium">Planner Name</span>
              <span className="sm:col-span-2 font-semibold text-slate-900">
                {user?.name || "Inventory Administrator"}
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-1">
              <span className="text-slate-500 font-medium">Email Address</span>
              <span className="sm:col-span-2 font-mono font-medium text-slate-900">
                {user?.email || "admin@example.com"}
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-1">
              <span className="text-slate-500 font-medium">Security Role</span>
              <span className="sm:col-span-2 font-semibold text-slate-900">
                Inventory Intelligence Planner (Read-Only Forecasting &amp; Replenishment)
              </span>
            </div>
          </div>
        </div>

        {/* Planning Run System Status Card */}
        <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-xs">
          <div className="border-b border-slate-200 px-6 py-4 bg-slate-50 flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-900">Planning Run Architecture Status</h2>
            <span className="rounded bg-blue-100 px-2 py-0.5 text-[10px] font-bold text-blue-800 border border-blue-200">
              {runs.length} Retained Cycles
            </span>
          </div>
          <div className="p-6 space-y-4 text-sm">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-1">
              <span className="text-slate-500 font-medium">Active Planning Run</span>
              <span className="sm:col-span-2 font-mono font-bold text-blue-700">
                {activeEffectiveRun?.run_id || "None"}
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-1">
              <span className="text-slate-500 font-medium">Cycle Status</span>
              <span className="sm:col-span-2 font-bold text-slate-900 capitalize">
                {activeEffectiveRun?.status || "—"} {activeEffectiveRun?.is_pruned && "(Pruned)"}
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-1">
              <span className="text-slate-500 font-medium">Completion Timestamp</span>
              <span className="sm:col-span-2 font-medium text-slate-900">
                {formatDate(activeEffectiveRun?.completed_at)}
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-1">
              <span className="text-slate-500 font-medium">Retention Policy</span>
              <span className="sm:col-span-2 font-semibold text-slate-900">
                30 Completed Planning Runs (Automatic Cascade Pruning)
              </span>
            </div>
          </div>
        </div>

        {/* System Configuration Card */}
        <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-xs">
          <div className="border-b border-slate-200 px-6 py-4 bg-slate-50">
            <h2 className="text-sm font-bold text-slate-900">POC System Configuration &amp; ERP Boundaries</h2>
          </div>
          <div className="p-6 space-y-4 text-sm">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-1">
              <span className="text-slate-500 font-medium">Champion Forecasting Model</span>
              <span className="sm:col-span-2 font-mono font-bold text-blue-700">
                trimmed_mean_3 (Empirically Calibrated)
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-1">
              <span className="text-slate-500 font-medium">Replenishment Logic</span>
              <span className="sm:col-span-2 font-semibold text-slate-900">
                Task 11 Deterministic Calculation Breakdown &amp; Shared Stock Absorption
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-1">
              <span className="text-slate-500 font-medium">ERP Connection Mode</span>
              <span className="sm:col-span-2 font-semibold text-slate-800">
                ERP Read-Only Mode (Safeguarded — all transactional write operations disabled)
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-1">
              <span className="text-slate-500 font-medium">Procurement Workflow</span>
              <span className="sm:col-span-2 text-slate-600 font-medium">
                Disabled in Read-Only POC (Zero Purchase Order writeback permissions)
              </span>
            </div>
          </div>
        </div>

        {/* Sign Out Action */}
        <div className="flex justify-end pt-2">
          <button
            onClick={handleLogout}
            className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white font-semibold text-xs transition-colors shadow-2xs"
          >
            Sign Out
          </button>
        </div>
      </div>
    </AppLayout>
  );
}
