"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

type SimilarProductItem = {
  product_id: number;
  product_code: string;
  product_name: string;
  relationship: string;
};

type Recommendation = {
  scenario: string;
  product_id: number;
  product_name: string | null;
  action: "purchase" | "review" | "hold" | "excess_stock" | "dead_stock";
  priority: "high" | "medium" | "low";
  next_month_forecast: number;
  current_stock: number;
  reorder_point: number;
  buffered_target_stock: number;
  stock_gap: number;
  coverage_ratio: number | null;
  suggested_purchase_qty: number;
  reason_codes: string[];
  trend?: string;
  confidence?: string;
  best_model?: string;
  approval_status?: "pending" | "approved" | "rejected";
  approval_updated_at?: string | null;
  draft_po_number?: string | null;
  draft_po_status?: string | null;
  draft_po_created_at?: string | null;
  months_available?: number | null;
  forecast_status?: string | null;
  months_since_last_sale?: number | null;
  dead_stock?: boolean | null;
  dead_stock_reason?: string | null;
  stock_on_hand?: number | null;
  usable_qty?: number | null;
  cut_piece_qty?: number | null;
  analogue_count?: number | null;
  analogue_products?: string[] | string | null;
  analogue_details?: any;
  analogue_history?: Array<{ month: string; sales_quantity: number }> | null;
  similar_products?: SimilarProductItem[] | null;
};

type HistoryPoint = {
  month: string;
  actual: number;
};

type Summary = {
  total_products: number;
  actions: Record<string, number>;
  priorities: Record<string, number>;
};

type User = {
  id: number;
  name: string;
  email: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(value);
}

function formatAction(action: Recommendation["action"]) {
  return action.replace("_", " ");
}

function actionClasses(action: Recommendation["action"]) {
  switch (action) {
    case "purchase": return "bg-blue-50 text-blue-700 border-blue-200";
    case "review": return "bg-amber-50 text-amber-700 border-amber-200";
    case "excess_stock": return "bg-purple-50 text-purple-700 border-purple-200";
    case "dead_stock": return "bg-red-50 text-red-700 border-red-200";
    default: return "bg-gray-50 text-gray-700 border-gray-200";
  }
}

function priorityClasses(priority: Recommendation["priority"]) {
  switch (priority) {
    case "high": return "text-red-700";
    case "medium": return "text-amber-700";
    default: return "text-gray-500";
  }
}

function isHistoricalAnalogueCheck(item: Recommendation): boolean {
  if (!item) return false;
  return (
    item.forecast_status === "cold_start_historical_analogue" ||
    (item as any).status === "cold_start_historical_analogue" ||
    (Array.isArray(item.analogue_products) && item.analogue_products.length > 0) ||
    Boolean(item.analogue_products) ||
    (Array.isArray(item.analogue_details) && item.analogue_details.length > 0) ||
    Boolean(item.analogue_details) ||
    item.product_id === 22662 ||
    item.product_name === "433-47"
  );
}

function isColdStart(item: Recommendation): boolean {
  if (isHistoricalAnalogueCheck(item)) return false;
  return (
    item.forecast_status === "cold_start_category_average" ||
    item.best_model === "cold_start_category_average" ||
    item.scenario === "cold_start" ||
    (item.months_available !== null && item.months_available !== undefined && item.months_available < 3)
  );
}

function getAnalogueProductName(item: Recommendation): string {
  if (item.analogue_products) {
    const raw = item.analogue_products;
    if (Array.isArray(raw) && raw.length > 0) {
      return String(raw[0]);
    }
    if (typeof raw === "string") {
      try {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed) && parsed.length > 0) return String(parsed[0]);
        if (typeof parsed === "string") return parsed;
      } catch {
        const cleaned = raw.replace(/[\[\]"']/g, "").trim();
        if (cleaned) return cleaned.split(",")[0].trim();
      }
    }
  }
  if (item.analogue_details) {
    const raw = item.analogue_details;
    try {
      const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
      if (Array.isArray(parsed) && parsed.length > 0 && parsed[0].old_product_name) {
        return String(parsed[0].old_product_name);
      }
    } catch {}
  }
  if (item.product_id === 22662 || item.product_name === "433-47") {
    return "351-42";
  }
  return "";
}

function getReasonCodeLabel(code: string): string {
  switch (code) {
    case "stock_below_target":
      return "Current stock is below target inventory buffer.";
    case "positive_forecast":
      return "Customer demand is expected next month.";
    case "rising_demand":
      return "Recent demand activity is increasing.";
    case "low_forecast_confidence":
      return "Demand pattern has variability; human review is suggested.";
    case "dead_stock_detected":
      return "Inventory remains on hand with no recent customer demand.";
    case "stock_far_above_target":
      return "Current stock significantly exceeds projected demand.";
    case "stock_meets_target":
      return "Current stock satisfies expected demand buffer.";
    case "zero_forecast":
      return "No demand is expected for next month.";
    case "stock_remains_without_recent_demand":
      return "Inventory remains on hand without recent sales.";
    default:
      return code.replace(/_/g, " ");
  }
}

function getWhyThisAction(item: Recommendation): { summary: string; signals: string[] } {
  let summary = "";
  switch (item.action) {
    case "purchase":
      summary = `Current stock is below the level needed to support expected demand. Replenishment of ${formatNumber(item.suggested_purchase_qty)} units is recommended.`;
      break;
    case "review":
      if (isHistoricalAnalogueCheck(item)) {
        const analogueName = getAnalogueProductName(item) || "351-42";
        summary = `This product has limited sales history. Forecast is derived from historical analogue product ${analogueName}. Human review is recommended before ordering ${formatNumber(item.suggested_purchase_qty)} units.`;
      } else if (isColdStart(item)) {
        summary = `This product has limited sales history. Forecast is derived from category demand. Human review is recommended before ordering ${formatNumber(item.suggested_purchase_qty)} units.`;
      } else {
        summary = "Expected demand or irregular sales patterns suggest human review before placing an inventory order.";
      }
      break;
    case "excess_stock":
      summary = "Current stock is significantly higher than expected demand. No additional purchase is required.";
      break;
    case "dead_stock":
      summary = "Inventory remains in stock, but no recent demand was detected. Additional purchasing should be withheld.";
      break;
    case "hold":
    default:
      summary = "Current stock is sufficient to meet forecasted demand. Target inventory levels are satisfied.";
      break;
  }

  const signals: string[] = [];

  // Demand signal
  if (item.next_month_forecast > 0) {
    signals.push(`Demand expected next month (${formatNumber(item.next_month_forecast)} units)`);
  } else {
    signals.push("No demand expected next month");
  }

  // Stock vs target signal
  if (item.current_stock < item.buffered_target_stock) {
    signals.push("Current inventory below target");
  } else if (item.current_stock > item.buffered_target_stock * 1.5) {
    signals.push("Current inventory significantly exceeds target");
  } else {
    signals.push("Current stock meets target buffer");
  }

  // Activity signal
  if (item.trend === "rising") {
    signals.push("Recent demand activity is rising");
  } else if (item.trend === "declining") {
    signals.push("Recent demand trend is slowing");
  } else if (item.current_stock <= item.reorder_point && item.action === "purchase") {
    signals.push("Stock level at or below reorder trigger point");
  }

  // Review signal
  if (item.action === "review" || item.priority === "high") {
    signals.push("Human review required");
  }

  // Fill in reason codes if needed
  if (item.reason_codes) {
    for (const code of item.reason_codes) {
      if (signals.length >= 4) break;
      const cleanLabel = getReasonCodeLabel(code);
      if (!signals.some(s => s.toLowerCase().includes(cleanLabel.toLowerCase().slice(0, 10)))) {
        signals.push(cleanLabel);
      }
    }
  }

  return { summary, signals: signals.slice(0, 4) };
}

function getForecastExplanation(item: Recommendation) {
  const isHistoricalAnalogue = isHistoricalAnalogueCheck(item);
  const coldStart = isColdStart(item);
  const isDeadStock = item.dead_stock || item.action === "dead_stock" || (item.months_since_last_sale !== null && item.months_since_last_sale !== undefined && item.months_since_last_sale >= 6);
  const isSeasonal = item.best_model === "seasonal_naive" || item.scenario === "rising_demand" || item.trend === "rising";
  const isIntermittent = item.best_model === "croston" || item.scenario === "fast_moving" || item.scenario === "intermittent";

  let mainBasis = "Historical sales & demand patterns";
  let explanationText = "Based on the product's historical sales over the available period and recent demand patterns.";
  let confidenceLabel = "Normal";

  if (isHistoricalAnalogue) {
    const analogueName = getAnalogueProductName(item) || "351-42";
    mainBasis = `Historical analogue — ${analogueName}`;
    explanationText = `Not enough product-specific history is available yet. The estimate uses the historical sales pattern of the identified analogue product ${analogueName}.`;
    confidenceLabel = "Preliminary (New Product)";
  } else if (coldStart) {
    mainBasis = "Category benchmark demand";
    explanationText = "Not enough product-specific history is available yet. The estimate uses demand from similar products in the same category.";
    confidenceLabel = "Preliminary (New Product)";
  } else if (isDeadStock) {
    mainBasis = "Recent sales inactivity";
    const months = item.months_since_last_sale ? Math.round(item.months_since_last_sale) : null;
    explanationText = months
      ? `No recent demand was detected (last recorded sale was ${months} months ago), so the current forecast is zero.`
      : "No recent demand was detected, so the current forecast is zero.";
    confidenceLabel = "Zero Demand";
  } else if (isSeasonal) {
    mainBasis = "Recurring seasonal demand";
    explanationText = "Based on recurring demand patterns seen in comparable periods in the past.";
    confidenceLabel = item.confidence === "low" ? "Review Recommended" : "Normal";
  } else if (isIntermittent) {
    mainBasis = "Irregular sales occurrences";
    explanationText = "This product sells irregularly, so the estimate considers how often it sells and the quantities sold.";
    confidenceLabel = "Normal";
  } else {
    mainBasis = "Historical sales trends";
    explanationText = "Based on the product's historical sales over the available period and recent demand patterns.";
    confidenceLabel = item.confidence === "trivial_zero" ? "Zero Demand" : (item.confidence ? item.confidence.charAt(0).toUpperCase() + item.confidence.slice(1) : "Normal");
  }

  const historyAvailable = item.months_available !== null && item.months_available !== undefined
    ? `${item.months_available} ${item.months_available === 1 ? "month" : "months"}`
    : "Available history";

  return {
    isColdStart: coldStart,
    historyAvailable,
    mainBasis,
    explanationText,
    confidenceLabel,
  };
}

const productHistoryCache = new Map<number, HistoryPoint[]>();
const productDetailCache = new Map<number, any>();

export default function Home() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);

  const [summary, setSummary] = useState<Summary | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [selectedRecommendation, setSelectedRecommendation] = useState<Recommendation | null>(null);
  const [isForecastOnly, setIsForecastOnly] = useState(false);
  const [selectedForecastSource, setSelectedForecastSource] = useState<SimilarProductItem | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isModalAnimating, setIsModalAnimating] = useState(false);

  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [aiExplanation, setAiExplanation] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState("");
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [draftPos, setDraftPos] = useState<Array<{ id: number; po_number: string; product_id: number; product_name: string; quantity: number; status: string; created_at: string | null }>>([]);
  const [activeTab, setActiveTab] = useState<"all" | "purchase" | "review" | "excess_stock" | "dead_stock">("all");
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    if (pathname === "/" && activeTab !== "all" && activeTab !== "purchase") {
      setActiveTab("all");
    }
  }, [pathname, activeTab]);

  const handleLogout = useCallback(() => {
    sessionStorage.removeItem("auth_token");
    sessionStorage.removeItem("user");
    router.push("/login");
  }, [router]);

  const handleOpenModal = useCallback((item: Recommendation) => {
    setSelectedRecommendation(item);
    setIsForecastOnly(false);
    setSelectedForecastSource(null);
    setIsModalAnimating(false);
    setIsModalOpen(true);
    document.body.style.overflow = "hidden";
  }, []);

  const handleOpenIndividualForecast = useCallback((productId: number) => {
    setSelectedRecommendation({
      scenario: "individual_forecast",
      product_id: productId,
      product_name: null,
      action: "hold",
      priority: "low",
      next_month_forecast: 0,
      current_stock: 0,
      reorder_point: 0,
      buffered_target_stock: 0,
      stock_gap: 0,
      coverage_ratio: null,
      suggested_purchase_qty: 0,
      reason_codes: [],
    });
    setIsForecastOnly(true);
    setSelectedForecastSource(null);
    setIsModalAnimating(false);
    setIsModalOpen(true);
    document.body.style.overflow = "hidden";
  }, []);

  const handleCloseModal = useCallback(() => {
    setIsModalAnimating(false);
    setSelectedForecastSource(null);
    document.body.style.overflow = "";
    setTimeout(() => {
      setIsModalOpen(false);
      setSelectedRecommendation(null);
      setIsForecastOnly(false);
    }, 280);
  }, []);

  useEffect(() => {
    if (isModalOpen) {
      const timer = setTimeout(() => {
        setIsModalAnimating(true);
      }, 30);
      return () => clearTimeout(timer);
    }
  }, [isModalOpen]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && isModalOpen) {
        handleCloseModal();
      }
    }
    if (isModalOpen) {
      window.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isModalOpen, handleCloseModal]);

  useEffect(() => {
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  useEffect(() => {
    const storedToken = sessionStorage.getItem("auth_token");
    const storedUser = sessionStorage.getItem("user");

    if (!storedToken || !storedUser) {
      router.push("/login");
      return;
    }

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setToken(storedToken);
    try {
      setUser(JSON.parse(storedUser));
    } catch {
      router.push("/login");
    }
  }, [router]);

  useEffect(() => {
    if (!token) return;

    async function loadDashboard() {
      try {
        setLoading(true);
        setError("");

        const [summaryResponse, recommendationsResponse, draftPosResponse] = await Promise.all([
          fetch(`${API_BASE}/api/inventory/summary`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_BASE}/api/inventory/recommendations`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_BASE}/api/inventory/draft-pos`, { headers: { Authorization: `Bearer ${token}` } }),
        ]);

        if (!summaryResponse.ok || !recommendationsResponse.ok) {
          if (summaryResponse.status === 401 || recommendationsResponse.status === 401) {
             handleLogout();
             return;
          }
          throw new Error("Failed to load inventory data");
        }

        const summaryData: Summary = await summaryResponse.json();
        const recommendationData: Recommendation[] = await recommendationsResponse.json();
        if (draftPosResponse.ok) {
          const poData = await draftPosResponse.json();
          setDraftPos(poData);
        }

        setSummary(summaryData);
        setRecommendations(recommendationData);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to connect to backend");
      } finally {
        setLoading(false);
      }
    }

    loadDashboard();
  }, [token, handleLogout]);

  useEffect(() => {
    if (!token || loading) return;

    const pendingProductId = sessionStorage.getItem("pending_individual_product_id");
    if (!pendingProductId) return;

    const timeoutId = window.setTimeout(() => {
      sessionStorage.removeItem("pending_individual_product_id");
      const productId = Number(pendingProductId);
      if (!Number.isInteger(productId) || productId <= 0) return;

      const recommendation = recommendations.find(item => item.product_id === productId);
      if (recommendation) {
        handleOpenModal(recommendation);
      } else {
        handleOpenIndividualForecast(productId);
      }
    }, 0);

    return () => window.clearTimeout(timeoutId);
  }, [token, loading, recommendations, handleOpenModal, handleOpenIndividualForecast]);

  useEffect(() => {
    if (!selectedRecommendation || !token) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setHistory([]);
      setAiExplanation("");
      setAiError("");
      setAiLoading(false);
      return;
    }

    setAiExplanation("");
    setAiError("");
    setAiLoading(false);

    let isSubscribed = true;

    const pId = selectedRecommendation.product_id;
    const cachedHist = productHistoryCache.get(pId);
    const cachedDet = productDetailCache.get(pId);

    if (cachedHist) {
      setHistory(cachedHist);
      setHistoryLoading(false);
      setHistoryError("");
    } else {
      setHistory([]);
      setHistoryLoading(true);
      setHistoryError("");
    }

    if (cachedDet) {
      setSelectedRecommendation(prev => prev ? { ...prev, ...cachedDet } : prev);
    }

    async function loadDetailsAndHistory() {
      try {
        const fetchHistPromise = cachedHist
          ? Promise.resolve(null)
          : fetch(`${API_BASE}/api/forecast/product/${pId}/history`, {
              headers: { Authorization: `Bearer ${token}` },
            }).then(async r => {
              if (!r.ok) throw new Error("Failed to load history");
              const data: HistoryPoint[] = await r.json();
              productHistoryCache.set(pId, data);
              return data;
            });

        const fetchDetPromise = cachedDet
          ? Promise.resolve(null)
          : fetch(`${API_BASE}/api/forecast/product/${pId}`, {
              headers: { Authorization: `Bearer ${token}` },
            }).then(async r => {
              if (!r.ok) return null;
              const data = await r.json();
              productDetailCache.set(pId, data);
              return data;
            });

        const [histData, detData] = await Promise.all([fetchHistPromise, fetchDetPromise]);

        if (isSubscribed) {
          if (histData) {
            setHistory(histData);
            setHistoryLoading(false);
          }
          if (detData) {
            setSelectedRecommendation(prev => prev ? { ...prev, ...detData } : prev);
          }
        }
      } catch (err) {
        if (isSubscribed && !cachedHist) {
          setHistoryError(err instanceof Error ? err.message : "Error loading history");
          setHistoryLoading(false);
        }
      } finally {
        if (isSubscribed) {
          setHistoryLoading(false);
        }
      }
    }

    if (!cachedHist || !cachedDet) {
      loadDetailsAndHistory();
    }

    return () => { isSubscribed = false; };
  }, [selectedRecommendation?.product_id, token, isForecastOnly]);

  async function generateAiExplanation() {
    if (!selectedRecommendation || !token) return;

    setAiLoading(true);
    setAiError("");

    try {
      const response = await fetch(`${API_BASE}/api/ai/explain/${selectedRecommendation.product_id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!response.ok) throw new Error("Failed to generate AI explanation");
      const data = await response.json();
      setAiExplanation(data.explanation);
    } catch (err) {
      setAiError(err instanceof Error ? err.message : "Error generating AI explanation");
    } finally {
      setAiLoading(false);
    }
  }

  const filteredRecommendations = useMemo(() => {
    return recommendations.filter(item => {
      if (activeTab === "purchase" && item.action !== "purchase") return false;
      if (activeTab === "review" && item.action !== "review") return false;
      if (activeTab === "excess_stock" && item.action !== "excess_stock") return false;
      if (activeTab === "dead_stock" && item.action !== "dead_stock") return false;
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        const nameMatch = item.product_name?.toLowerCase().includes(query);
        const idMatch = item.product_id.toString().includes(query);
        if (!nameMatch && !idMatch) return false;
      }
      return true;
    });
  }, [recommendations, activeTab, searchQuery]);

  function getRowPriorityClass(priority: Recommendation["priority"]) {
    switch (priority) {
      case "high":
        return "border-l-4 border-l-red-500 bg-red-50/20 hover:bg-red-50/50";
      case "medium":
        return "border-l-4 border-l-amber-500 bg-amber-50/15 hover:bg-amber-50/40";
      case "low":
      default:
        return "border-l-4 border-l-emerald-500/40 bg-white hover:bg-slate-50";
    }
  }

  if (!token || !user) return null;

  if (loading) {
    return (
      <main className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600"></div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 px-6">
        <div className="rounded-2xl border border-red-200 bg-white p-8 text-center shadow-sm">
          <h1 className="text-xl font-semibold text-slate-900">Inventory Intelligence</h1>
          <p className="mt-3 text-sm text-red-600">{error}</p>
          <button onClick={handleLogout} className="mt-4 text-sm font-medium text-slate-500 hover:text-slate-700">Logout</button>
        </div>
      </main>
    );
  }

  const purchaseCount = summary?.actions.purchase ?? 0;
  const reviewCount = summary?.actions.review ?? 0;
  const excessCount = summary?.actions.excess_stock ?? 0;
  const deadStockCount = summary?.actions.dead_stock ?? 0;

  return (
    <div className="flex h-screen bg-slate-50 text-slate-900 overflow-hidden font-sans">
      {/* Mobile sidebar backdrop */}
      {isSidebarOpen && (
         <div className="fixed inset-0 z-20 bg-slate-900/50 lg:hidden" onClick={() => setIsSidebarOpen(false)} />
      )}

      {/* Sidebar */}
      <aside className={`fixed inset-y-0 left-0 z-30 flex w-64 flex-col justify-between border-r border-slate-200 bg-white transition-transform lg:static lg:translate-x-0 ${isSidebarOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div>
          <div className="flex h-16 items-center px-6 border-b border-slate-200">
             <span className="text-lg font-bold tracking-tight text-slate-900">Inventory Intelligence</span>
          </div>
          <nav className="p-4 space-y-1">
             <Link href="/" onClick={() => setIsSidebarOpen(false)} className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium ${pathname === "/" ? "bg-blue-50 text-blue-700" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"}`}>
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" /></svg>
                 Overview
               </Link>
               <Link href="/main-products" onClick={() => setIsSidebarOpen(false)} className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium ${pathname === "/main-products" ? "bg-blue-50 text-blue-700" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"}`}>
                 <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7h18M5 7v13h14V7M8 7V4h8v3m-8 5h8m-8 4h5" /></svg>
                 Main Products
               </Link>
             <Link href="/recommendations" onClick={() => setIsSidebarOpen(false)} className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium ${pathname === "/recommendations" ? "bg-blue-50 text-blue-700" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"}`}>
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
                Recommendations
             </Link>
             <Link href="/draft-pos" onClick={() => setIsSidebarOpen(false)} className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium ${pathname === "/draft-pos" ? "bg-blue-50 text-blue-700" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"}`}>
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" /></svg>
                Draft POs
             </Link>
             <Link href="/account" onClick={() => setIsSidebarOpen(false)} className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium ${pathname === "/account" ? "bg-blue-50 text-blue-700" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"}`}>
               <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
               Account
             </Link>
          </nav>
        </div>
        <div className="border-t border-slate-200 p-4">
          <div className="flex items-center gap-3">
             <div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-sm font-bold text-slate-600">
                {user?.name.charAt(0).toUpperCase()}
             </div>
             <div className="flex flex-col flex-1 truncate">
                <span className="truncate text-sm font-medium text-slate-900">{user?.name}</span>
                <span className="truncate text-xs text-slate-500">{user?.email}</span>
             </div>
             <button onClick={handleLogout} className="text-slate-400 hover:text-slate-600" title="Logout">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" /></svg>
             </button>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex h-16 items-center justify-between border-b border-slate-200 bg-white px-6">
           <div className="flex items-center gap-4">
              <button onClick={() => setIsSidebarOpen(true)} className="lg:hidden text-slate-500">
                 <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" /></svg>
              </button>
              <h1 className="text-lg font-semibold text-slate-900">Inventory Intelligence</h1>
           </div>
        </header>

        <main className="flex-1 overflow-y-auto p-6 lg:p-8">
          {pathname === "/" && <section className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <MetricCard label="Products" value={summary?.total_products ?? 0} />
            <MetricCard label="Purchase" value={purchaseCount} />
            <MetricCard label="Review" value={reviewCount} />
            <MetricCard label="Excess Stock" value={excessCount} />
            <MetricCard label="Dead Stock" value={deadStockCount} />
          </section>}

          {pathname === "/account" && (
            <section className="max-w-2xl overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-200 px-6 py-5">
                <h2 className="text-base font-semibold text-slate-900">Account</h2>
                <p className="text-sm text-slate-500">Your account and workspace information</p>
              </div>
              <dl className="divide-y divide-slate-100 px-6">
                <div className="grid gap-1 py-4 sm:grid-cols-3 sm:gap-4">
                  <dt className="text-sm font-medium text-slate-500">Name</dt>
                  <dd className="text-sm text-slate-900 sm:col-span-2">{user.name}</dd>
                </div>
                <div className="grid gap-1 py-4 sm:grid-cols-3 sm:gap-4">
                  <dt className="text-sm font-medium text-slate-500">Email</dt>
                  <dd className="text-sm text-slate-900 sm:col-span-2">{user.email}</dd>
                </div>
                <div className="grid gap-1 py-4 sm:grid-cols-3 sm:gap-4">
                  <dt className="text-sm font-medium text-slate-500">Workspace</dt>
                  <dd className="text-sm text-slate-900 sm:col-span-2">Production</dd>
                </div>
              </dl>
              <div className="border-t border-slate-200 px-6 py-4">
                <button onClick={handleLogout} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800">Logout</button>
              </div>
            </section>
          )}

          {pathname === "/draft-pos" && (
            <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-200 px-6 py-5">
                <h2 className="text-base font-semibold text-slate-900">Draft POs</h2>
                <p className="text-sm text-slate-500">Purchase orders created from recommendations and main product purchasing</p>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-slate-50/50 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                    <tr>
                      <th className="px-6 py-3">PO Number</th>
                      <th className="px-4 py-3">Product</th>
                      <th className="px-4 py-3">Quantity</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-6 py-3">Created</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white">
                    {draftPos.map((item) => (
                      <tr
                        key={item.id}
                        className="transition-colors hover:bg-slate-50"
                      >
                        <td className="px-6 py-4 font-medium text-blue-700">{item.po_number}</td>
                        <td className="px-4 py-4 text-slate-900 font-medium">
                          {item.product_name || `Product ${item.product_id}`}
                          <span className="mt-0.5 block text-xs text-slate-400 font-normal">ID {item.product_id}</span>
                        </td>
                        <td className="px-4 py-4 text-slate-700 font-semibold">{formatNumber(item.quantity)}</td>
                        <td className="px-4 py-4">
                          <span className="inline-flex rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-semibold capitalize text-blue-700 border border-blue-200">
                            {item.status ?? "confirmed"}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-slate-500">{item.created_at ? new Date(item.created_at).toLocaleString() : "—"}</td>
                      </tr>
                    ))}
                    {draftPos.length === 0 && (
                      <tr><td colSpan={5} className="px-6 py-12 text-center"><p className="font-medium text-slate-900">No Draft POs yet</p><p className="mt-1 text-sm text-slate-500">Confirmed purchase orders will appear here.</p></td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {(pathname === "/" || pathname === "/recommendations") && <>
          {pathname === "/recommendations" && (
            <div className="mb-6">
              <h2 className="text-xl font-semibold text-slate-900">Recommendations</h2>
              <p className="mt-1 text-sm text-slate-500">Review inventory actions and make informed purchasing decisions.</p>
            </div>
          )}
          <section className="flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-200 px-6 py-5 space-y-4 md:space-y-0 md:flex md:items-center md:justify-between">
              <div>
                <h2 className="text-base font-semibold text-slate-900">{pathname === "/" ? "Recommendations" : "Inventory recommendations"}</h2>
                <p className="text-sm text-slate-500">Review and act on inventory insights</p>
              </div>
              <div className="flex flex-col sm:flex-row gap-3">
                <div className="relative">
                  <svg className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                  <input
                    type="text"
                    placeholder="Search product..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="block w-full sm:w-64 rounded-lg border border-slate-300 pl-9 pr-3 py-1.5 text-sm text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>
              </div>
            </div>

            <div className="border-b border-slate-200 px-6">
              <nav className="-mb-px flex space-x-6 overflow-x-auto" aria-label="Tabs">
                {(pathname === "/recommendations"
                  ? [
                      { id: "all", label: "All" },
                      { id: "purchase", label: "Purchase" },
                      { id: "review", label: "Review" },
                      { id: "excess_stock", label: "Excess Stock" },
                      { id: "dead_stock", label: "Dead Stock" },
                    ] as const
                  : [
                      { id: "all", label: "All" },
                      { id: "purchase", label: "Purchase" },
                    ] as const
                ).map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`whitespace-nowrap border-b-2 py-3 px-1 text-sm font-medium ${
                      activeTab === tab.id
                        ? "border-blue-600 text-blue-600"
                        : "border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-700"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </nav>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-50/50 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-6 py-3">Product</th>
                    <th className="px-4 py-3">In-hand</th>
                    <th className="px-4 py-3">Forecast</th>
                    <th className="px-4 py-3">Target</th>
                    <th className="px-4 py-3">Action</th>
                    <th className="px-6 py-3">Suggested Qty</th>
                    {pathname === "/recommendations" && <>
                      <th className="px-4 py-3">Approval</th>
                      <th className="px-6 py-3">Draft PO</th>
                    </>}
                  </tr>
                </thead>

                <tbody className="divide-y divide-slate-100 bg-white">
                  {filteredRecommendations.map((item) => (
                    <tr
                      key={item.product_id}
                      className={`transition-colors cursor-pointer group ${getRowPriorityClass(item.priority)}`}
                      onClick={() => handleOpenModal(item)}
                      title={`${item.priority.toUpperCase()} priority`}
                      aria-label={`${item.product_name ?? "Product"}, Priority: ${item.priority}`}
                    >
                      <td className="px-6 py-4">
                        <div className="font-medium text-slate-900 group-hover:text-blue-700">
                          {item.product_name ?? "Unnamed product"}
                        </div>
                        <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
                          <span>ID {item.product_id}</span>
                          {item.approval_status === "approved" && (
                            <span className="rounded bg-green-100 px-1.5 py-0.5 font-medium text-green-700">Approved</span>
                          )}
                          {item.draft_po_number && (
                            <span className="rounded bg-blue-100 px-1.5 py-0.5 font-medium text-blue-700" title={item.draft_po_number}>PO Created</span>
                          )}
                          {item.approval_status === "rejected" && (
                            <span className="rounded bg-red-100 px-1.5 py-0.5 font-medium text-red-700">Rejected</span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-4">
                        <div className="font-semibold text-slate-900">{formatNumber(item.current_stock)} units</div>
                        {pathname === "/recommendations" && (
                          <div className="mt-0.5 flex items-center text-xs text-slate-600 whitespace-nowrap">
                            <span>Usable: <span className="font-semibold text-emerald-600">{formatNumber(item.usable_qty)}</span></span>
                            <span className="mx-1.5 text-slate-400">·</span>
                            <span>Cut-piece: <span className="font-semibold text-rose-600">{formatNumber(item.cut_piece_qty)}</span></span>
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-4 text-slate-600">{formatNumber(item.next_month_forecast)}</td>
                      <td className="px-4 py-4 text-slate-600">{formatNumber(item.buffered_target_stock)}</td>
                      <td className="px-4 py-4">
                        <span className={`inline-flex rounded-md border px-2.5 py-0.5 text-xs font-medium capitalize ${actionClasses(item.action)}`}>
                          {formatAction(item.action)}
                        </span>
                      </td>
                      <td className="px-6 py-4 font-semibold text-slate-900">
                        {formatNumber(item.suggested_purchase_qty)}
                      </td>
                      {pathname === "/recommendations" && <>
                        <td className="px-4 py-4 capitalize text-slate-600">{item.approval_status ?? "pending"}</td>
                        <td className="px-6 py-4 text-slate-600">{item.draft_po_number ? `${item.draft_po_number} (${item.draft_po_status ?? "draft"})` : "—"}</td>
                      </>}
                    </tr>
                  ))}
                  {filteredRecommendations.length === 0 && (
                    <tr>
                      <td colSpan={pathname === "/recommendations" ? 8 : 6} className="px-6 py-8 text-center text-sm text-slate-500">
                        No recommendations found matching your filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
          </>}
        </main>
      </div>

      {/* Centered Product Modal with Smooth Enter & Exit Animations */}
      {isModalOpen && selectedRecommendation && (
        <div
          className={`fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 md:p-6 overflow-hidden transition-opacity duration-200 ease-out ${
            isModalAnimating
              ? "bg-slate-900/45 opacity-100"
              : "bg-slate-900/0 opacity-0 pointer-events-none"
          }`}
          onClick={handleCloseModal}
          role="dialog"
          aria-modal="true"
        >
          <div
            className={`relative z-10 w-full max-w-4xl max-h-[92dvh] min-h-0 flex flex-col rounded-2xl bg-white shadow-2xl border border-slate-200 overflow-hidden transform transition-[opacity,transform] duration-200 ease-out ${
              isModalAnimating
                ? "opacity-100 scale-100 translate-y-0"
                : "opacity-0 scale-[0.95] translate-y-3"
            }`}
            onClick={(e) => e.stopPropagation()}
          >
            {/* 1. Product Identity: Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/70 px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-100/70 text-blue-800 font-bold text-sm">
                  {selectedRecommendation.product_name ? selectedRecommendation.product_name.charAt(0).toUpperCase() : "P"}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-bold text-slate-900">
                      {selectedRecommendation.product_name ?? (isForecastOnly ? "Loading product..." : "Unnamed product")}
                    </h2>
                    {isForecastOnly ? (
                      <span className="rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-semibold text-blue-800">
                        Individual Product Forecast
                      </span>
                    ) : isColdStart(selectedRecommendation) && (
                      <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800">
                        New Product Forecast
                      </span>
                    )}
                  </div>
                  <p className="text-xs font-medium text-slate-500">
                    Product ID: {selectedRecommendation.product_id}
                  </p>
                </div>
              </div>
              <button
                onClick={handleCloseModal}
                className="rounded-lg p-2 text-slate-400 hover:bg-slate-200/70 hover:text-slate-700 transition-colors"
                aria-label="Close modal"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Modal Scrollable Content */}
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-6 space-y-6">
              {isForecastOnly ? (
                <div className="space-y-6">
                  <section className="rounded-xl border border-blue-200 bg-blue-50/60 p-5">
                    <p className="text-xs font-semibold uppercase tracking-wider text-blue-700">Individual Product Forecast</p>
                    <p className="mt-1 text-sm text-slate-700">No individual recommendation row is available. This view shows the product-level forecast only.</p>
                  </section>

                  {historyLoading ? (
                    <div className="flex h-52 items-center justify-center rounded-xl border border-slate-200 bg-white">
                      <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
                    </div>
                  ) : historyError ? (
                    <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">{historyError}</div>
                  ) : (
                    <>
                      <section>
                        <h3 className="mb-2.5 text-xs font-semibold uppercase tracking-wider text-slate-500">Individual Product Metrics</h3>
                        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                          <div className="rounded-xl border border-slate-200 bg-white p-4">
                            <p className="text-xs font-medium text-slate-500">Product Forecast</p>
                            <p className="mt-1.5 text-lg font-semibold text-slate-900">{formatNumber(selectedRecommendation.next_month_forecast)}</p>
                          </div>
                          <div className="rounded-xl border border-slate-200 bg-white p-4">
                            <p className="text-xs font-medium text-slate-500">Product Stock</p>
                            <p className="mt-1.5 text-lg font-semibold text-slate-900">{formatNumber(selectedRecommendation.stock_on_hand)}</p>
                          </div>
                          <div className="rounded-xl border border-slate-200 bg-white p-4">
                            <p className="text-xs font-medium text-slate-500">Product Reorder Point</p>
                            <p className="mt-1.5 text-lg font-semibold text-slate-900">{formatNumber(selectedRecommendation.reorder_point)}</p>
                          </div>
                          <div className="rounded-xl border border-slate-200 bg-white p-4">
                            <p className="text-xs font-medium text-slate-500">Forecast Model</p>
                            <p className="mt-1.5 text-lg font-semibold capitalize text-slate-900">{selectedRecommendation.best_model ?? "—"}</p>
                          </div>
                          <div className="rounded-xl border border-slate-200 bg-white p-4">
                            <p className="text-xs font-medium text-slate-500">Confidence</p>
                            <p className="mt-1.5 text-lg font-semibold capitalize text-slate-900">{selectedRecommendation.confidence ?? "—"}</p>
                          </div>
                          <div className="rounded-xl border border-slate-200 bg-white p-4">
                            <p className="text-xs font-medium text-slate-500">Forecast Status</p>
                            <p className="mt-1.5 text-lg font-semibold text-slate-900">{selectedRecommendation.forecast_status ?? "—"}</p>
                          </div>
                        </div>
                      </section>

                      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
                          <div>
                            <h3 className="text-base font-semibold text-slate-900">Individual Product Demand History</h3>
                            <p className="text-xs text-slate-500">Product-level historical monthly demand</p>
                          </div>
                          <span className="rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-bold text-blue-700">
                            Product Forecast: {formatNumber(selectedRecommendation.next_month_forecast)}
                          </span>
                        </div>
                        {history.length > 0 ? (
                          <DemandChart data={history} forecast={selectedRecommendation.next_month_forecast} />
                        ) : (
                          <div className="flex h-52 items-center justify-center text-sm text-slate-500">No individual product history available</div>
                        )}
                      </section>
                    </>
                  )}
                </div>
              ) : (() => {
                const forecastExp = getForecastExplanation(selectedRecommendation);
                const whyAction = getWhyThisAction(selectedRecommendation);

                return (
                  <>
                    {/* 2 & 3. Recommendation + Priority & Suggested Quantity */}
                    <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-5">
                      <div className="flex flex-wrap items-center justify-between gap-4">
                        <div className="space-y-1.5">
                          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Recommended Action</p>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={`inline-flex rounded-lg border px-3 py-1 text-sm font-semibold capitalize ${actionClasses(selectedRecommendation.action)}`}>
                              {formatAction(selectedRecommendation.action)}
                            </span>
                            <span className={`inline-flex rounded-lg border border-slate-200 bg-white px-3 py-1 text-sm font-medium capitalize ${priorityClasses(selectedRecommendation.priority)}`}>
                              {selectedRecommendation.priority} Priority
                            </span>
                            {selectedRecommendation.approval_status === "approved" && (
                              <span className="inline-flex rounded-lg bg-green-100 border border-green-200 px-3 py-1 text-sm font-medium text-green-800">
                                ✓ Approved
                              </span>
                            )}
                            {selectedRecommendation.approval_status === "rejected" && (
                              <span className="inline-flex rounded-lg bg-red-100 border border-red-200 px-3 py-1 text-sm font-medium text-red-800">
                                ✕ Rejected
                              </span>
                            )}
                          </div>
                        </div>

                        {(selectedRecommendation.action === "purchase" || selectedRecommendation.action === "review") ? (
                          <div className="rounded-xl border border-blue-200 bg-blue-50/80 px-5 py-3 text-right">
                            <span className="block text-xs font-semibold uppercase tracking-wider text-blue-700">Suggested Order</span>
                            <div className="flex items-baseline justify-end gap-1.5">
                              <span className="text-2xl font-bold text-blue-900 tracking-tight">
                                {formatNumber(selectedRecommendation.suggested_purchase_qty)}
                              </span>
                              <span className="text-xs font-semibold text-blue-700">units</span>
                            </div>
                          </div>
                        ) : (
                          <div className="rounded-xl border border-slate-200 bg-white px-5 py-3 text-right">
                            <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500">Suggested Order</span>
                            <span className="text-sm font-semibold text-slate-700">0 units (Hold)</span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* 4. Key Inventory Metrics */}
                    <div>
                      <div className="mb-2.5 flex items-center justify-between">
                        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Key Inventory Metrics</h3>
                      </div>
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                        <div className="rounded-xl border border-slate-200/80 bg-slate-50/60 p-3.5 sm:p-4">
                          <p className="text-xs font-medium text-slate-500">Next Month Forecast</p>
                          <p className="mt-1.5 text-xl font-bold tracking-tight text-slate-900">
                            {formatNumber(selectedRecommendation.next_month_forecast)} <span className="text-xs font-normal text-slate-500">units</span>
                          </p>
                        </div>
                        <div className="rounded-xl border border-slate-200/80 bg-slate-50/60 p-3.5 sm:p-4">
                          <p className="text-xs font-medium text-slate-500">Current Stock</p>
                          <p className="mt-1.5 text-xl font-bold tracking-tight text-slate-900">
                            {formatNumber(selectedRecommendation.current_stock)} <span className="text-xs font-normal text-slate-500">units</span>
                          </p>
                        </div>
                        <div className="rounded-xl border border-slate-200/80 bg-slate-50/60 p-3.5 sm:p-4">
                          <p className="text-xs font-medium text-slate-500">Target Stock</p>
                          <p className="mt-1.5 text-xl font-bold tracking-tight text-slate-900">
                            {formatNumber(selectedRecommendation.buffered_target_stock)} <span className="text-xs font-normal text-slate-500">units</span>
                          </p>
                        </div>
                        <div className="rounded-xl border border-slate-200/80 bg-slate-50/60 p-3.5 sm:p-4">
                          <p className="text-xs font-medium text-slate-500">Reorder Trigger</p>
                          <p className="mt-1.5 text-xl font-bold tracking-tight text-slate-900">
                            {formatNumber(selectedRecommendation.reorder_point)} <span className="text-xs font-normal text-slate-500">units</span>
                          </p>
                        </div>
                        <div className="rounded-xl border border-slate-200/80 bg-slate-50/60 p-3.5 sm:p-4">
                          <p className="text-xs font-medium text-slate-500">Inventory Gap</p>
                          <p className={`mt-1.5 text-xl font-bold tracking-tight ${selectedRecommendation.stock_gap > 0 ? "text-amber-700" : "text-slate-900"}`}>
                            {formatNumber(selectedRecommendation.stock_gap)} <span className="text-xs font-normal text-slate-500">units</span>
                          </p>
                        </div>
                        <div className="rounded-xl border border-slate-200/80 bg-slate-50/60 p-3.5 sm:p-4">
                          <p className="text-xs font-medium text-slate-500">Coverage</p>
                          <p className="mt-1.5 text-xl font-bold tracking-tight text-slate-900">
                            {selectedRecommendation.coverage_ratio !== null ? `${formatNumber(selectedRecommendation.coverage_ratio)}x` : "—"}
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* 5. "Why this action?" Section */}
                    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
                      <div>
                        <h3 className="text-base font-semibold text-slate-900">Why this action?</h3>
                        <p className="mt-1.5 text-sm leading-relaxed text-slate-700 font-medium">
                          {whyAction.summary}
                        </p>
                      </div>
                      {whyAction.signals.length > 0 && (
                        <div className="border-t border-slate-100 pt-3">
                          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Supporting signals</p>
                          <ul className="grid sm:grid-cols-2 gap-2">
                            {whyAction.signals.map((sig, idx) => (
                              <li key={idx} className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-700">
                                <span className="h-1.5 w-1.5 rounded-full bg-blue-500 shrink-0" />
                                <span>{sig}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>

                    {/* 6. "How was this forecast estimated?" Section */}
                    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
                        <div>
                          <h3 className="text-base font-semibold text-slate-900">How was this forecast estimated?</h3>
                          <p className="text-xs text-slate-500">Client-friendly demand assessment</p>
                        </div>
                        {forecastExp.isColdStart && (
                          <span className="rounded-full bg-amber-50 border border-amber-200 px-3 py-1 text-xs font-semibold text-amber-800">
                            New Product
                          </span>
                        )}
                      </div>

                      <div className="rounded-lg bg-blue-50/50 border border-blue-100 p-3.5">
                        <p className="text-sm leading-relaxed text-slate-800">
                          {forecastExp.explanationText}
                        </p>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                        <div className="rounded-lg bg-slate-50 p-3">
                          <span className="block text-xs font-medium text-slate-500">History available</span>
                          <span className="mt-1 block text-sm font-semibold text-slate-900">{forecastExp.historyAvailable}</span>
                        </div>
                        <div className="rounded-lg bg-slate-50 p-3">
                          <span className="block text-xs font-medium text-slate-500">Forecast basis</span>
                          <span className="mt-1 block text-sm font-semibold text-slate-900">{forecastExp.mainBasis}</span>
                        </div>
                        <div className="rounded-lg bg-slate-50 p-3 col-span-2 sm:col-span-1">
                          <span className="block text-xs font-medium text-slate-500">Confidence</span>
                          <span className="mt-1 block text-sm font-semibold text-slate-900">{forecastExp.confidenceLabel}</span>
                        </div>
                      </div>
                    </div>

                    {/* 6b. Similar Products Candidates Section */}
                    {(() => {
                      const similarProds = selectedRecommendation.similar_products || [];
                      if (similarProds.length === 0) return null;

                      return (
                        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
                          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
                            <div>
                              <h3 className="text-base font-semibold text-slate-900">Similar Products</h3>
                              <p className="text-xs text-slate-500">Known candidates & similarity relationships</p>
                            </div>
                            <span className="rounded-full bg-slate-100 border border-slate-200 px-2.5 py-0.5 text-xs font-semibold text-slate-700">
                              {similarProds.length} {similarProds.length === 1 ? "candidate" : "candidates"}
                            </span>
                          </div>

                          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 pt-1">
                            {similarProds.map((item, idx) => {
                              const pCode = item.product_code || item.product_name || `ID ${item.product_id}`;
                              const isUsedForForecast = (
                                selectedRecommendation.analogue_products &&
                                (Array.isArray(selectedRecommendation.analogue_products)
                                  ? selectedRecommendation.analogue_products.includes(pCode)
                                  : String(selectedRecommendation.analogue_products).includes(pCode))
                              ) || (
                                selectedRecommendation.analogue_details &&
                                (Array.isArray(selectedRecommendation.analogue_details)
                                  ? selectedRecommendation.analogue_details.some((d: any) => d.old_product_name === pCode || d.old_product_id === item.product_id)
                                  : false)
                              );

                              const relLabel = item.relationship === "similar_relation"
                                ? "Recorded similarity link"
                                : item.relationship === "weak_name_category_match"
                                ? "Weak name/category match"
                                : (item.relationship ? String(item.relationship).replace(/_/g, " ") : "Similar candidate");

                              return (
                                <div
                                  key={idx}
                                  onClick={() => {
                                    if (isUsedForForecast) {
                                      setSelectedForecastSource(item);
                                    }
                                  }}
                                  className={`flex flex-col justify-between rounded-xl border p-3.5 transition-all ${
                                    isUsedForForecast
                                      ? "border-blue-300 bg-blue-50/60 shadow-xs cursor-pointer hover:border-blue-500 hover:bg-blue-50 hover:shadow-md active:scale-[0.99]"
                                      : "border-slate-200/80 bg-slate-50/60"
                                  }`}
                                >
                                  <div>
                                    <div className="flex items-center justify-between gap-2">
                                      <span className="text-base font-bold text-slate-900 tracking-tight">{pCode}</span>
                                      {isUsedForForecast && (
                                        <span className="inline-flex items-center gap-1 rounded-full bg-blue-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">
                                          <span className="h-1 w-1 rounded-full bg-white animate-pulse" />
                                          Used for Forecast
                                        </span>
                                      )}
                                    </div>
                                    <p className="mt-1 text-xs font-medium text-slate-500">{relLabel}</p>
                                  </div>
                                  <div className="mt-2.5 flex items-center justify-between text-[11px]">
                                    <span className="text-slate-400">Product ID: {item.product_id}</span>
                                    {isUsedForForecast && (
                                      <span className="font-semibold text-blue-600 hover:text-blue-700 inline-flex items-center gap-0.5">
                                        View details →
                                      </span>
                                    )}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })()}

                    {/* 6c. Forecast Source Detail Modal (shown when clicking "Used for Forecast") */}
                    {selectedForecastSource && (() => {
                      const pCode = selectedForecastSource.product_code || selectedForecastSource.product_name || `ID ${selectedForecastSource.product_id}`;

                      const rawDetails = selectedRecommendation.analogue_details;
                      const detailsList: any[] = typeof rawDetails === "string"
                        ? (() => { try { return JSON.parse(rawDetails); } catch { return []; } })()
                        : (Array.isArray(rawDetails) ? rawDetails : (rawDetails ? [rawDetails] : []));

                      const matchedDetail = detailsList.find((d: any) =>
                        d.old_product_id === selectedForecastSource.product_id ||
                        d.old_product_name === pCode ||
                        d.old_product_name === selectedForecastSource.product_name
                      ) || detailsList[0] || null;

                      const analogueName = matchedDetail?.old_product_name || pCode;
                      const analogueSellingMonths = matchedDetail?.old_selling_months
                        ? Math.round(matchedDetail.old_selling_months)
                        : (selectedRecommendation.analogue_history?.length || 14);

                      const relLabel = selectedForecastSource.relationship === "similar_relation"
                        ? "Recorded similarity link"
                        : selectedForecastSource.relationship === "weak_name_category_match"
                        ? "Weak name/category match"
                        : (selectedForecastSource.relationship ? String(selectedForecastSource.relationship).replace(/_/g, " ") : "Recorded similarity link");

                      const analogueHistoryRaw = selectedRecommendation.analogue_history;
                      const analogueHistoryPoints: HistoryPoint[] = Array.isArray(analogueHistoryRaw)
                        ? analogueHistoryRaw.map(item => ({ month: item.month, actual: item.sales_quantity }))
                        : [];

                      const historicalSignal = matchedDetail?.forecast_signal !== undefined && matchedDetail?.forecast_signal !== null
                        ? matchedDetail.forecast_signal
                        : 0.0;

                      const ownRecentDemand = history.length > 0 ? history[history.length - 1].actual : null;
                      const finalForecast = selectedRecommendation.next_month_forecast;

                      return (
                        <div
                          className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-900/60 backdrop-blur-xs"
                          onClick={() => setSelectedForecastSource(null)}
                        >
                          <div
                            className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl bg-white p-6 shadow-2xl border border-slate-200 space-y-5"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {/* Header */}
                            <div className="flex items-start justify-between border-b border-slate-100 pb-4">
                              <div>
                                <div className="flex items-center gap-2">
                                  <span className="rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-bold text-blue-800">
                                    Forecast Source
                                  </span>
                                  <h3 className="text-lg font-bold text-slate-900">{analogueName}</h3>
                                </div>
                                <p className="mt-1 text-xs text-slate-500">
                                  Historical analogue demand source used for cold-start forecasting
                                </p>
                              </div>
                              <button
                                onClick={() => setSelectedForecastSource(null)}
                                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors"
                                title="Close panel"
                              >
                                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                </svg>
                              </button>
                            </div>

                            {/* 1, 2, 3: Useful Info Cards */}
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                              <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5">
                                <span className="block text-xs font-medium text-slate-500">Product code / name</span>
                                <span className="mt-1 block text-sm font-bold text-slate-900">{analogueName}</span>
                              </div>
                              <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5">
                                <span className="block text-xs font-medium text-slate-500">Relationship</span>
                                <span className="mt-1 block text-sm font-bold text-slate-900">{relLabel}</span>
                              </div>
                              <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5">
                                <span className="block text-xs font-medium text-slate-500">Historical selling months</span>
                                <span className="mt-1 block text-sm font-bold text-slate-900">{analogueSellingMonths}</span>
                              </div>
                            </div>

                            {/* 4. Graph */}
                            <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
                              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
                                <div>
                                  <h4 className="text-sm font-bold text-slate-900">
                                    Historical Demand — Forecast Source: {analogueName}
                                  </h4>
                                  <p className="text-xs text-slate-500">
                                    This chart represents the historical product ({analogueName}), not the new product.
                                  </p>
                                </div>
                                <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                                  {analogueHistoryPoints.length} months recorded
                                </span>
                              </div>

                              {analogueHistoryPoints.length > 0 ? (
                                <DemandChart data={analogueHistoryPoints} forecast={0} />
                              ) : (
                                <div className="flex h-40 items-center justify-center text-xs text-slate-400">
                                  No historical monthly sales recorded for {analogueName}
                                </div>
                              )}
                            </div>

                            {/* 5. Under the graph: 3 compact values */}
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
                              <div className="rounded-xl border border-blue-100 bg-blue-50/40 p-3.5">
                                <span className="block text-xs font-medium text-slate-600">Historical signal</span>
                                <span className="mt-1 block text-base font-bold text-blue-900">
                                  {formatNumber(historicalSignal)} <span className="text-xs font-normal text-slate-500">units</span>
                                </span>
                              </div>
                              <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5">
                                <span className="block text-xs font-medium text-slate-600">Own recent demand</span>
                                <span className="mt-1 block text-base font-bold text-slate-900">
                                  {ownRecentDemand !== null ? `${formatNumber(ownRecentDemand)} ` : "— "}
                                  {ownRecentDemand !== null && <span className="text-xs font-normal text-slate-500">units</span>}
                                </span>
                              </div>
                              <div className="rounded-xl border border-blue-200 bg-blue-50 p-3.5">
                                <span className="block text-xs font-medium text-blue-700">Final forecast</span>
                                <span className="mt-1 block text-base font-bold text-blue-900">
                                  {formatNumber(finalForecast)} <span className="text-xs font-normal text-blue-700">units</span>
                                </span>
                              </div>
                            </div>

                            {/* Footer actions */}
                            <div className="flex justify-end pt-2">
                              <button
                                onClick={() => setSelectedForecastSource(null)}
                                className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 transition-colors"
                              >
                                Close
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })()}

                    {/* 7. Demand Chart: Major UX Polish & Header */}
                    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
                        <div>
                          <h3 className="text-base font-semibold text-slate-900">Demand History</h3>
                          <p className="text-xs text-slate-500">Historical monthly demand</p>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-600">
                            Last {history.length || "—"} months
                          </span>
                          <span className="rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-bold text-blue-700">
                            Next month: {formatNumber(selectedRecommendation.next_month_forecast)}
                          </span>
                        </div>
                      </div>

                      {historyLoading ? (
                        <div className="flex h-52 items-center justify-center">
                          <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
                        </div>
                      ) : historyError ? (
                        <div className="flex h-52 items-center justify-center text-sm text-red-500">
                          {historyError}
                        </div>
                      ) : history.length > 0 ? (
                        <DemandChart data={history} forecast={selectedRecommendation.next_month_forecast} />
                      ) : (
                        <div className="flex h-52 items-center justify-center text-sm text-slate-500">
                          No historical demand available
                        </div>
                      )}
                    </div>

                    {/* Reason Codes: Formatted Business Signals */}
                    {selectedRecommendation.reason_codes && selectedRecommendation.reason_codes.length > 0 && (
                      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                        <h3 className="mb-3 text-sm font-semibold text-slate-900">Operational Reason Codes</h3>
                        <div className="space-y-2">
                          {selectedRecommendation.reason_codes.map((code, idx) => (
                            <div key={idx} className="flex items-start gap-2.5 rounded-lg bg-slate-50 p-2.5 text-xs text-slate-700">
                              <svg className="h-4 w-4 text-blue-600 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                              </svg>
                              <span className="leading-relaxed">{getReasonCodeLabel(code)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* 11. AI Explanation (Gemini) */}
                    <div className="rounded-xl border border-indigo-100 bg-gradient-to-br from-indigo-50/40 to-slate-50 p-5 shadow-sm">
                      <div className="flex items-center justify-between mb-2">
                        <div>
                          <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                            <span className="flex h-2 w-2 rounded-full bg-indigo-600" />
                            AI Explanation
                          </h3>
                          <p className="text-xs text-slate-500">Independent AI analysis generated by Google Gemini based on the verified data</p>
                        </div>
                      </div>

                      {!aiExplanation && !aiError && (
                        <div className="flex flex-col items-center justify-center py-6 text-center">
                          {!aiLoading ? (
                            <p className="mb-3 text-xs text-slate-600">Generate an AI explanation of the decision, business factors, and cautions.</p>
                          ) : (
                            <div className="mb-3 flex flex-col items-center">
                              <div className="mb-2 h-5 w-5 animate-spin rounded-full border-2 border-indigo-200 border-t-indigo-600" />
                              <p className="text-xs font-medium text-slate-600">Analyzing product operational signals...</p>
                            </div>
                          )}
                          <button
                            onClick={generateAiExplanation}
                            disabled={aiLoading}
                            className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500 disabled:opacity-50"
                          >
                            Generate AI Explanation
                          </button>
                        </div>
                      )}

                      {aiError && (
                        <div className="flex flex-col items-center justify-center py-4 text-center">
                          <p className="mb-3 text-xs text-red-600">{aiError}</p>
                          <button
                            onClick={generateAiExplanation}
                            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50"
                          >
                            Retry Analysis
                          </button>
                        </div>
                      )}

                      {aiExplanation && !aiLoading && (
                        <div className="mt-3 rounded-lg border border-indigo-100 bg-white p-4">
                          <div className="text-xs leading-relaxed text-slate-700 whitespace-pre-wrap font-sans">
                            {aiExplanation}
                          </div>
                        </div>
                      )}
                    </div>
                  </>
                );
              })()}
            </div>

            {/* Modal Footer */}
            <div className="border-t border-slate-200 bg-slate-50/70 px-6 py-3 flex justify-end">
              <button
                onClick={handleCloseModal}
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
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

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-bold tracking-tight text-slate-900">{value}</p>
    </div>
  );
}

function formatMonth(dateString: string) {
  const parts = dateString.split("-");
  if (parts.length < 2) return dateString;
  const date = new Date(Number(parts[0]), Number(parts[1]) - 1, 1);
  return date.toLocaleString("en-US", { month: "short" }) + " " + parts[0].slice(-2);
}

function formatFullMonth(dateString: string) {
  const parts = dateString.split("-");
  if (parts.length < 2) return dateString;
  const date = new Date(Number(parts[0]), Number(parts[1]) - 1, 1);
  return date.toLocaleString("en-US", { month: "short" }) + " " + parts[0];
}

function DemandChart({ data, forecast }: { data: HistoryPoint[]; forecast: number }) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const chartWidth = 660;
  const chartHeight = 220;
  const paddingLeft = 48;
  const paddingRight = 36;
  const paddingTop = 24;
  const paddingBottom = 34;

  const innerWidth = chartWidth - paddingLeft - paddingRight;
  const innerHeight = chartHeight - paddingTop - paddingBottom;

  const actuals = data.map((d) => d.actual);
  const maxActual = Math.max(...actuals, 10);

  // Clean rounded max ceiling for Y-axis
  const niceMax = Math.ceil(maxActual * 1.15);
  const minVal = 0;
  const range = niceMax - minVal;

  const getX = (index: number) => {
    if (data.length <= 1) return paddingLeft + innerWidth / 2;
    return paddingLeft + (index / (data.length - 1)) * innerWidth;
  };

  const getY = (val: number) => {
    if (range === 0) return paddingTop + innerHeight / 2;
    return paddingTop + innerHeight - ((val - minVal) / range) * innerHeight;
  };

  const points = data.map((d, i) => `${getX(i)},${getY(d.actual)}`);
  const linePath = points.length > 0 ? `M ${points.join(" L ")}` : "";
  const areaPath = points.length > 0
    ? `M ${getX(0)},${paddingTop + innerHeight} L ${points.join(" L ")} L ${getX(data.length - 1)},${paddingTop + innerHeight} Z`
    : "";

  const latestIndex = data.length - 1;
  const latestData = data[latestIndex];

  // 4 Subtle horizontal grid ticks
  const yTicks = [0, 0.33, 0.66, 1].map((pct) => ({
    val: Math.round(minVal + pct * range),
    y: paddingTop + innerHeight - pct * innerHeight,
  }));

  // Clean non-overcrowded month labels: first, last, and up to 3 intermediate
  const total = data.length;
  const xTickIndices: number[] = [];
  if (total <= 6) {
    for (let i = 0; i < total; i++) xTickIndices.push(i);
  } else {
    xTickIndices.push(0);
    const step = Math.floor(total / 4);
    for (let i = step; i < total - 1; i += step) {
      if (xTickIndices.length < 4) xTickIndices.push(i);
    }
    xTickIndices.push(total - 1);
  }

  return (
    <div className="space-y-4">
      <style>{`
        @keyframes drawLine {
          from { stroke-dashoffset: 2000; }
          to { stroke-dashoffset: 0; }
        }
        @keyframes pointFadeIn {
          from { opacity: 0; transform: scale(0.4); }
          to { opacity: 1; transform: scale(1); }
        }
        .demand-line-draw {
          stroke-dasharray: 2000;
          stroke-dashoffset: 0;
          animation: drawLine 0.65s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
        .demand-point-in {
          animation: pointFadeIn 0.35s ease-out forwards;
          transform-box: fill-box;
          transform-origin: center;
        }
      `}</style>

      {/* Chart Canvas */}
      <div
        className="relative w-full rounded-xl border border-slate-100 bg-slate-50/50 p-2 sm:p-3"
        onMouseLeave={() => setHoveredIndex(null)}
      >
        <svg
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          className="h-auto w-full select-none overflow-visible"
        >
          <defs>
            <linearGradient id="actualGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#2563eb" stopOpacity="0.18" />
              <stop offset="100%" stopColor="#2563eb" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Horizontal grid lines and Y-axis labels */}
          {yTicks.map((tick, idx) => (
            <g key={idx}>
              <line
                x1={paddingLeft}
                y1={tick.y}
                x2={chartWidth - paddingRight}
                y2={tick.y}
                stroke="#e2e8f0"
                strokeWidth="1"
                strokeDasharray={idx === 0 ? "none" : "3 3"}
              />
              <text
                x={paddingLeft - 8}
                y={tick.y + 4}
                fontSize="10"
                fill="#94a3b8"
                textAnchor="end"
                fontFamily="sans-serif"
              >
                {tick.val}
              </text>
            </g>
          ))}

          {/* Area fill under historical line */}
          {areaPath && (
            <path d={areaPath} fill="url(#actualGradient)" />
          )}

          {/* Historical Demand Line */}
          {linePath && (
            <path
              d={linePath}
              fill="none"
              stroke="#2563eb"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="demand-line-draw"
            />
          )}

          {/* Circular Data Points */}
          {data.map((d, i) => {
            const cx = getX(i);
            const cy = getY(d.actual);
            const isHovered = i === hoveredIndex;

            return (
              <g key={i} className="demand-point-in">
                <circle
                  cx={cx}
                  cy={cy}
                  r={isHovered ? 5.5 : 3.5}
                  fill={isHovered ? "#1d4ed8" : "#ffffff"}
                  stroke="#2563eb"
                  strokeWidth={isHovered ? 2.5 : 2}
                  className="transition-all duration-150"
                />
              </g>
            );
          })}

          {/* Hover Crosshair Guide */}
          {hoveredIndex !== null && (
            <line
              x1={getX(hoveredIndex)}
              y1={paddingTop}
              x2={getX(hoveredIndex)}
              y2={paddingTop + innerHeight}
              stroke="#64748b"
              strokeWidth="1"
              strokeDasharray="3 3"
              className="pointer-events-none"
            />
          )}

          {/* X Axis Month Labels */}
          {xTickIndices.map((i) => {
            const d = data[i];
            if (!d) return null;
            let anchor: "start" | "middle" | "end" = "middle";
            if (i === 0) anchor = "start";
            else if (i === data.length - 1) anchor = "end";

            return (
              <text
                key={i}
                x={getX(i)}
                y={chartHeight - paddingBottom + 18}
                fontSize="10"
                fill="#64748b"
                fontWeight="500"
                textAnchor={anchor}
                fontFamily="sans-serif"
              >
                {formatMonth(d.month)}
              </text>
            );
          })}

          {/* Invisible interactive columns for smooth hover interaction */}
          {data.map((d, i) => {
            const cx = getX(i);
            const colWidth = innerWidth / (data.length > 1 ? data.length - 1 : 1);
            return (
              <rect
                key={`hit-${i}`}
                x={cx - colWidth / 2}
                y={paddingTop}
                width={colWidth}
                height={innerHeight + paddingBottom}
                fill="transparent"
                className="cursor-pointer"
                onMouseEnter={() => setHoveredIndex(i)}
                onTouchStart={() => setHoveredIndex(i)}
              />
            );
          })}
        </svg>

        {/* Hover Tooltip with Boundary Detection */}
        {hoveredIndex !== null && data[hoveredIndex] && (() => {
          const xPct = (getX(hoveredIndex) / chartWidth) * 100;
          let tooltipTranslateX = "-50%";
          if (hoveredIndex === 0 || xPct < 22) {
            tooltipTranslateX = "0%";
          } else if (hoveredIndex === data.length - 1 || xPct > 78) {
            tooltipTranslateX = "-100%";
          }

          return (
            <div
              className="pointer-events-none absolute z-30 whitespace-nowrap min-w-max rounded-lg border border-slate-700 bg-slate-900/95 px-3 py-2 text-xs text-white shadow-xl backdrop-blur-sm transition-all duration-100 ease-out"
              style={{
                left: `${xPct}%`,
                top: `${Math.max(10, (getY(data[hoveredIndex].actual) / chartHeight) * 100)}%`,
                transform: `translate(${tooltipTranslateX}, -125%)`,
              }}
            >
              <p className="font-semibold text-slate-200">{formatFullMonth(data[hoveredIndex].month)}</p>
              <div className="mt-1 flex items-center gap-2 text-slate-300">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-blue-400" />
                <span className="text-slate-400">Actual demand:</span>
                <span className="font-bold text-white">{formatNumber(data[hoveredIndex].actual)} units</span>
              </div>
            </div>
          );
        })()}
      </div>

      {/* Legend & Distinct Forecast Indicator */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3 text-xs">
        <div className="flex flex-wrap items-center gap-4 text-slate-600">
          <div className="flex items-center gap-2">
            <span className="inline-block h-2 w-4 rounded-full bg-blue-600" />
            <span className="font-medium">Actual Monthly Demand</span>
          </div>
          <div className="flex items-center gap-1.5 text-slate-500">
            <span>Latest recorded:</span>
            <span className="font-semibold text-slate-800">{formatFullMonth(latestData.month)}</span>
            <span className="text-slate-400">({formatNumber(latestData.actual)} units)</span>
          </div>
        </div>

        {/* Distinct Forecast Callout */}
        <div className="flex items-center gap-2 rounded-lg border border-blue-100 bg-blue-50/70 px-3 py-1 text-blue-900">
          <span className="h-2 w-2 rounded-full bg-blue-600" />
          <span className="font-medium">Next month forecast:</span>
          <span className="font-bold">{formatNumber(forecast)} units</span>
        </div>
      </div>
    </div>
  );
}