"use client";

import { useEffect, useState, useCallback, ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  PlanningRunProvider,
  usePlanningRun,
  PlanningRun,
} from "./PlanningRunContext";

export type User = {
  id: number;
  name: string;
  email: string;
};

export interface AppLayoutProps {
  children: ReactNode;
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

export function sanitizeErrorMessage(rawMsg: string | null | undefined): string {
  if (!rawMsg) return "Planning cycle encountered an unspecified failure.";
  const lower = rawMsg.toLowerCase();

  // Strip database connection strings, credentials, and SQL statements
  if (
    lower.includes("password") ||
    lower.includes("psycopg") ||
    lower.includes("sqlalchemy") ||
    lower.includes("connection refused") ||
    lower.includes("operationalerror") ||
    lower.includes("pg_") ||
    lower.includes("host=") ||
    lower.includes("port=") ||
    lower.includes("user=") ||
    lower.includes("select ") ||
    lower.includes("update ") ||
    lower.includes("insert ") ||
    lower.includes("from planning_runs") ||
    lower.includes("traceback")
  ) {
    if (lower.includes("timeout") || lower.includes("timed out")) {
      return "Database connection timed out during execution.";
    }
    if (
      lower.includes("active planning run is currently in progress") ||
      lower.includes("concurrency") ||
      lower.includes("uq_single_running")
    ) {
      return "Cycle conflict: An active planning run is already in progress.";
    }
    if (lower.includes("interrupted") || lower.includes("terminated")) {
      return "Execution interrupted: Planning process was terminated unexpectedly.";
    }
    return "Database query error occurred during planning run execution.";
  }

  if (rawMsg.length > 120) {
    return rawMsg.substring(0, 117) + "...";
  }
  return rawMsg;
}

function PlanningRunSelector() {
  const {
    runs,
    selectedRunId,
    latestRun,
    activeEffectiveRun,
    setSelectedRunId,
    refreshRuns,
    isLoading,
  } = usePlanningRun();

  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="relative">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 hover:border-slate-300 transition-all shadow-2xs"
          title="Switch active planning run snapshot"
        >
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] uppercase font-bold text-slate-400">
              Run:
            </span>
            {activeEffectiveRun ? (
              <span className="font-mono font-semibold text-slate-900 truncate max-w-[140px] sm:max-w-[200px]">
                {activeEffectiveRun.run_id}
              </span>
            ) : (
              <span className="text-slate-500">Loading...</span>
            )}
          </div>

          {activeEffectiveRun && (
            <div className="flex items-center gap-1">
              {activeEffectiveRun.is_pruned ? (
                <span className="rounded bg-amber-100 px-1.5 py-0.2 text-[10px] font-bold text-amber-800 border border-amber-200">
                  Pruned
                </span>
              ) : activeEffectiveRun.status === "completed" ? (
                <span className="rounded bg-emerald-100 px-1.5 py-0.2 text-[10px] font-bold text-emerald-800 border border-emerald-200">
                  {selectedRunId ? "Historical" : "Latest"}
                </span>
              ) : activeEffectiveRun.status === "running" ? (
                <span className="rounded bg-blue-100 px-1.5 py-0.2 text-[10px] font-bold text-blue-800 border border-blue-200 animate-pulse">
                  Running
                </span>
              ) : (
                <span className="rounded bg-red-100 px-1.5 py-0.2 text-[10px] font-bold text-red-800 border border-red-200">
                  Failed
                </span>
              )}
            </div>
          )}

          <svg
            className={`h-3.5 w-3.5 text-slate-500 transition-transform ${
              isOpen ? "rotate-180" : ""
            }`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 9l-7 7-7-7"
            />
          </svg>
        </button>

        <button
          onClick={() => refreshRuns()}
          disabled={isLoading}
          className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100 transition-colors disabled:opacity-50"
          title="Refresh planning runs and catalog data"
          aria-label="Refresh planning runs and catalog data"
        >
          <svg
            className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </button>
      </div>

      {/* Dropdown Menu */}
      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute right-0 top-full mt-1.5 z-50 w-80 sm:w-96 rounded-xl border border-slate-200 bg-white p-2 shadow-xl">
            <div className="flex items-center justify-between px-3 py-2 border-b border-slate-100">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-700">
                Planning Runs History
              </span>
              <span className="text-[11px] text-slate-400">
                {runs.length} retained runs
              </span>
            </div>

            <div className="max-h-72 overflow-y-auto divide-y divide-slate-100 py-1">
              {/* Default Latest Option */}
              {latestRun && (
                <button
                  type="button"
                  onClick={() => {
                    setSelectedRunId(null);
                    setIsOpen(false);
                  }}
                  className={`w-full text-left p-2.5 rounded-lg transition-colors flex items-center justify-between ${
                    selectedRunId === null
                      ? "bg-blue-50/80 border border-blue-200"
                      : "hover:bg-slate-50"
                  }`}
                >
                  <div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-bold text-slate-900">
                        Latest Completed Run
                      </span>
                      <span className="rounded bg-emerald-100 text-emerald-800 text-[9px] font-bold px-1.5 py-0.2 border border-emerald-200">
                        Default
                      </span>
                    </div>
                    <p className="font-mono text-[11px] text-slate-500 mt-0.5 truncate max-w-[200px]">
                      {latestRun.run_id}
                    </p>
                    <p className="text-[10px] text-slate-400 mt-0.5">
                      {formatDate(latestRun.completed_at)} · {latestRun.num_groups} groups
                    </p>
                  </div>
                  {selectedRunId === null && (
                    <svg
                      className="h-4 w-4 text-blue-600 shrink-0"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                  )}
                </button>
              )}

              {/* Historical Runs List (deduplicated against latestRun) */}
              {runs
                .filter((r) => !latestRun || r.run_id !== latestRun.run_id)
                .map((r) => {
                  const isSelected = selectedRunId === r.run_id;
                return (
                  <button
                    key={r.run_id}
                    type="button"
                    onClick={() => {
                      setSelectedRunId(r.run_id);
                      setIsOpen(false);
                    }}
                    className={`w-full text-left p-2.5 rounded-lg transition-colors flex items-center justify-between ${
                      isSelected
                        ? "bg-blue-50/80 border border-blue-200"
                        : "hover:bg-slate-50"
                    }`}
                  >
                    <div className="min-w-0 flex-1 pr-2">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-xs font-bold text-slate-900 truncate">
                          {r.run_id}
                        </span>
                        {r.is_pruned ? (
                          <span className="rounded bg-amber-100 text-amber-800 text-[9px] font-bold px-1.5 py-0.2 border border-amber-200 shrink-0">
                            Pruned
                          </span>
                        ) : r.status === "completed" ? (
                          <span className="rounded bg-slate-100 text-slate-700 text-[9px] font-medium px-1.5 py-0.2 border border-slate-200 shrink-0">
                            Completed
                          </span>
                        ) : r.status === "running" ? (
                          <span className="rounded bg-blue-100 text-blue-800 text-[9px] font-bold px-1.5 py-0.2 border border-blue-200 shrink-0">
                            Running
                          </span>
                        ) : (
                          <span className="rounded bg-red-100 text-red-800 text-[9px] font-bold px-1.5 py-0.2 border border-red-200 shrink-0">
                            Failed
                          </span>
                        )}
                      </div>
                      <p className="text-[10px] text-slate-400 mt-0.5">
                        Started: {formatDate(r.started_at)}
                        {r.completed_at && ` · Finished: ${formatDate(r.completed_at)}`}
                      </p>
                      <p className="text-[10px] text-slate-500 mt-0.5">
                        {r.num_groups} groups · {r.num_products} products
                      </p>
                      {r.error_message && (
                        <p className="text-[10px] text-red-600 truncate mt-0.5" title={sanitizeErrorMessage(r.error_message)}>
                          Error: {sanitizeErrorMessage(r.error_message)}
                        </p>
                      )}
                    </div>
                    {isSelected && (
                      <svg
                        className="h-4 w-4 text-blue-600 shrink-0"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function GlobalPlanningRunStatusBanner() {
  const { activeEffectiveRun } = usePlanningRun();
  if (!activeEffectiveRun) return null;

  if (activeEffectiveRun.is_pruned) {
    return (
      <div className="bg-amber-50 border-b border-amber-200 px-6 py-2 text-xs text-amber-900 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <svg className="h-4 w-4 text-amber-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span>
            <strong>Historical Snapshot Pruned:</strong> Planning run <code className="font-mono font-bold">{activeEffectiveRun.run_id}</code> was pruned by retention policy. High-level run metadata is preserved, but detailed product forecast rows have been pruned.
          </span>
        </div>
      </div>
    );
  }

  if (activeEffectiveRun.status === "failed") {
    return (
      <div className="bg-red-50 border-b border-red-200 px-6 py-2 text-xs text-red-900 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <svg className="h-4 w-4 text-red-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>
            <strong>Failed Planning Run:</strong> Run <code className="font-mono font-bold">{activeEffectiveRun.run_id}</code> terminated with error: <em>{activeEffectiveRun.error_message || "Unknown computation error"}</em>.
          </span>
        </div>
      </div>
    );
  }

  if (activeEffectiveRun.status === "running") {
    return (
      <div className="bg-blue-50 border-b border-blue-200 px-6 py-2 text-xs text-blue-900 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-blue-600 animate-ping shrink-0" />
          <span>
            <strong>Planning Run in Progress:</strong> Run <code className="font-mono font-bold">{activeEffectiveRun.run_id}</code> is currently executing. Completed snapshots will be available upon cycle completion.
          </span>
        </div>
      </div>
    );
  }

  return null;
}

function LayoutInner({ children }: AppLayoutProps) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    const storedToken = sessionStorage.getItem("auth_token");
    const storedUser = sessionStorage.getItem("user");

    if (!storedToken || !storedUser) {
      router.push("/login");
      return;
    }

    setToken(storedToken);
    try {
      setUser(JSON.parse(storedUser));
    } catch {
      router.push("/login");
      return;
    }
    setAuthChecked(true);
  }, [router]);

  const handleLogout = useCallback(() => {
    sessionStorage.removeItem("auth_token");
    sessionStorage.removeItem("user");
    sessionStorage.removeItem("selected_run_id");
    router.push("/login");
  }, [router]);

  if (!authChecked || !token || !user) {
    return (
      <main className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600"></div>
      </main>
    );
  }

  const navItems = [
    {
      label: "Overview",
      href: "/",
      icon: (
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
        </svg>
      ),
      isActive: pathname === "/",
    },
    {
      label: "Main Products",
      href: "/main-products",
      icon: (
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7h18M5 7v13h14V7M8 7V4h8v3m-8 5h8m-8 4h5" />
        </svg>
      ),
      isActive: pathname === "/main-products",
    },
    {
      label: "Recommendations",
      href: "/recommendations",
      icon: (
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
      ),
      isActive: pathname === "/recommendations",
    },
    {
      label: "Account",
      href: "/account",
      icon: (
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
        </svg>
      ),
      isActive: pathname === "/account",
    },
  ];

  return (
    <div className="flex h-screen bg-slate-50 text-slate-900 overflow-hidden font-sans">
      {/* Mobile sidebar backdrop */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-slate-900/50 lg:hidden"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-64 flex-col justify-between border-r border-slate-200 bg-white transition-transform lg:static lg:translate-x-0 ${
          isSidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div>
          <div className="flex h-16 items-center px-6 border-b border-slate-200">
            <span className="text-lg font-bold tracking-tight text-slate-900">
              Inventory Intelligence
            </span>
          </div>
          <nav className="p-4 space-y-1">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setIsSidebarOpen(false)}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  item.isActive
                    ? "bg-blue-50 text-blue-700 font-semibold"
                    : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                }`}
              >
                {item.icon}
                {item.label}
              </Link>
            ))}
          </nav>
        </div>

        <div className="border-t border-slate-200 p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-sm font-bold text-slate-600">
              {user.name ? user.name.charAt(0).toUpperCase() : "U"}
            </div>
            <div className="flex flex-col flex-1 truncate">
              <span className="truncate text-sm font-medium text-slate-900">{user.name}</span>
              <span className="truncate text-xs text-slate-500">{user.email}</span>
            </div>
            <button
              onClick={handleLogout}
              className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100 transition-colors"
              title="Logout"
              aria-label="Logout"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top Header */}
        <header className="flex h-14 items-center justify-between border-b border-slate-200 bg-white px-6 shrink-0 gap-4">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsSidebarOpen(true)}
              className="lg:hidden text-slate-500 hover:text-slate-700"
              aria-label="Open sidebar"
            >
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <div className="flex items-center gap-2">
              <span className="text-xs font-black tracking-wider text-slate-900 uppercase">
                INVENTORY INTELLIGENCE
              </span>
              <span className="text-[10px] uppercase px-2 py-0.5 rounded-full font-bold bg-emerald-100 text-emerald-800 border border-emerald-200 hidden sm:inline">
                PLANNING CYCLES
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <PlanningRunSelector />
            <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200 hidden md:inline">
              ERP Read-Only Mode (Safeguarded)
            </span>
          </div>
        </header>

        {/* Global Status Banner for Special Run States */}
        <GlobalPlanningRunStatusBanner />

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto p-6 lg:p-8">
          {children}
        </main>
      </div>
    </div>
  );
}

export default function AppLayout({ children }: AppLayoutProps) {
  return <LayoutInner>{children}</LayoutInner>;
}
