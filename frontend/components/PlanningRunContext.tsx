"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  ReactNode,
} from "react";

export interface PlanningRun {
  run_id: string;
  started_at: string;
  completed_at: string | null;
  status: "running" | "completed" | "failed" | string;
  error_message: string | null;
  num_groups: number;
  num_products: number;
  config_metadata: Record<string, any>;
  execution_summary: Record<string, any>;
  is_pruned: boolean;
  created_at: string;
}

interface PlanningRunContextType {
  runs: PlanningRun[];
  latestRun: PlanningRun | null;
  selectedRunId: string | null;
  selectedRun: PlanningRun | null;
  effectiveRunId: string | null;
  activeEffectiveRun: PlanningRun | null;
  isLoading: boolean;
  error: string | null;
  setSelectedRunId: (runId: string | null) => void;
  refreshRuns: () => Promise<void>;
}

const PlanningRunContext = createContext<PlanningRunContextType | undefined>(
  undefined
);

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export function PlanningRunProvider({ children }: { children: ReactNode }) {
  const [runs, setRuns] = useState<PlanningRun[]>([]);
  const [latestRun, setLatestRun] = useState<PlanningRun | null>(null);
  const [selectedRunId, setSelectedRunIdState] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRuns = useCallback(async () => {
    const token =
      typeof window !== "undefined"
        ? sessionStorage.getItem("auth_token")
        : null;
    if (!token) {
      setIsLoading(false);
      return;
    }

    try {
      setIsLoading(true);
      setError(null);

      const [runsRes, latestRes] = await Promise.all([
        fetch(`${API_BASE}/api/planning-runs?limit=50`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch(`${API_BASE}/api/planning-runs/latest`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);

      let runsData: PlanningRun[] = [];
      if (runsRes.ok) {
        runsData = await runsRes.json();
        setRuns(runsData);
      }

      let latestData: PlanningRun | null = null;
      if (latestRes.ok) {
        latestData = await latestRes.json();
        setLatestRun(latestData);
      } else if (runsData.length > 0) {
        // Fallback: first completed run in list
        const fallbackLatest =
          runsData.find((r) => r.status === "completed") || runsData[0];
        setLatestRun(fallbackLatest);
        latestData = fallbackLatest;
      }

      // Check stored preference in sessionStorage
      const storedRunId = sessionStorage.getItem("selected_run_id");
      if (storedRunId) {
        const found = runsData.find((r) => r.run_id === storedRunId);
        if (found) {
          setSelectedRunIdState(storedRunId);
        } else {
          // If not in first 50 runs, check whether it exists on server
          try {
            const singleRes = await fetch(`${API_BASE}/api/planning-runs/${encodeURIComponent(storedRunId)}`, {
              headers: { Authorization: `Bearer ${token}` },
            });
            if (singleRes.ok) {
              const singleRun: PlanningRun = await singleRes.json();
              runsData = [singleRun, ...runsData];
              setRuns(runsData);
              setSelectedRunIdState(storedRunId);
            } else if (singleRes.status === 404) {
              // Only clear if confirmed 404 from backend
              sessionStorage.removeItem("selected_run_id");
              setSelectedRunIdState(null);
            } else {
              // Network/temporary error: preserve selection
              setSelectedRunIdState(storedRunId);
            }
          } catch {
            setSelectedRunIdState(storedRunId);
          }
        }
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load planning runs"
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  const setSelectedRunId = useCallback(
    (runId: string | null) => {
      setSelectedRunIdState(runId);
      if (runId) {
        sessionStorage.setItem("selected_run_id", runId);
      } else {
        sessionStorage.removeItem("selected_run_id");
      }
    },
    []
  );

  const selectedRun = runs.find((r) => r.run_id === selectedRunId) || null;
  // If an explicit run is selected, never silently substitute latestRun
  const activeEffectiveRun = selectedRunId
    ? selectedRun || {
        run_id: selectedRunId,
        started_at: "",
        completed_at: null,
        status: "missing",
        error_message: `Explicitly requested planning run '${selectedRunId}' was not found.`,
        num_groups: 0,
        num_products: 0,
        config_metadata: {},
        execution_summary: {},
        is_pruned: false,
        created_at: "",
      }
    : latestRun;
  const effectiveRunId = selectedRunId || latestRun?.run_id || null;

  return (
    <PlanningRunContext.Provider
      value={{
        runs,
        latestRun,
        selectedRunId,
        selectedRun,
        effectiveRunId,
        activeEffectiveRun,
        isLoading,
        error,
        setSelectedRunId,
        refreshRuns: fetchRuns,
      }}
    >
      {children}
    </PlanningRunContext.Provider>
  );
}

export function usePlanningRun() {
  const context = useContext(PlanningRunContext);
  if (!context) {
    return {
      runs: [],
      latestRun: null,
      selectedRunId: null,
      selectedRun: null,
      effectiveRunId: null,
      activeEffectiveRun: null,
      isLoading: false,
      error: null,
      setSelectedRunId: () => {},
      refreshRuns: async () => {},
    };
  }
  return context;
}
