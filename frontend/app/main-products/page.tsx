"use client";

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

type MainProductListItem = {
  main_product_template_id: number;
  main_product_name: string;
  group_size: number;
  group_valid: boolean;
  group_current_stock: number | null;
  group_usable_qty?: number | null;
  group_cut_piece_qty?: number | null;
  group_forecasted_stock?: number | null;
  group_next_month_forecast: number | null;
  best_model: string | null;
  confidence: string | null;
  group_reorder_point: number | null;
  group_buffered_target_stock: number | null;
  group_stock_gap: number | null;
  group_suggested_purchase_qty: number;
  action: string;
  priority: string;
  approval_status: "pending" | "approved" | "rejected";
  forecast_status: string;
  recommendation_scope: string;
  forecast_scope: string;
};

type MainProductMember = {
  product_id: number;
  template_id: number;
  name: string | null;
  is_main_similar: boolean | null;
  main_product_template_id: number | null;
  current_stock: number;
  usable_qty?: number | null;
  cut_piece_qty?: number | null;
  forecasted_stock?: number | null;
  incoming_qty?: number | null;
  outgoing_qty?: number | null;
};

type ForecastStep = {
  month: string;
  forecast: number;
};

type MainProductDetail = {
  main_product: {
    template_id: number;
    product_id?: number | null;
    name: string | null;
    is_main_similar: boolean | null;
    current_stock: number | null;
    usable_qty?: number | null;
    cut_piece_qty?: number | null;
    forecasted_stock?: number | null;
    incoming_qty?: number | null;
    outgoing_qty?: number | null;
  };
  group: {
    group_valid: boolean;
    group_size: number;
    validation_issues: string[];
    validation_warnings: string[];
    persisted_group_valid: boolean;
    persisted_validation_issues: string[];
    persisted_validation_warnings: string[];
    total_current_stock?: number | null;
    total_usable_qty?: number | null;
    total_cut_piece_qty?: number | null;
    total_forecasted_stock?: number | null;
    total_incoming_qty?: number | null;
    total_outgoing_qty?: number | null;
    members: MainProductMember[];
  };
  forecast: {
    forecast_scope: string;
    main_product_template_id: number;
    main_product_name: string;
    group_size: number;
    months_available: number | null;
    history_start: string | null;
    history_end: string | null;
    next_month_forecast: number | null;
    forecast_3_months?: ForecastStep[];
    best_model: string | null;
    confidence: string | null;
    mae: number | null;
    wape: number | null;
    mase: number | null;
    avg_monthly_demand: number | null;
    forecast_status: string;
  };
  recommendation: {
    recommendation_scope: string;
    main_product_template_id: number;
    main_product_name: string;
    group_size: number;
    group_valid: boolean;
    group_current_stock: number | null;
    group_next_month_forecast: number | null;
    best_model: string | null;
    confidence: string | null;
    group_reorder_point: number | null;
    group_buffered_target_stock: number | null;
    group_stock_gap: number | null;
    group_coverage_ratio: number | null;
    group_suggested_purchase_qty: number;
    action: string;
    priority: string;
    reason_codes: string[];
    validation_issues: string[];
    validation_warnings: string[];
    recommendation_status: string;
    approval_status: "pending" | "approved" | "rejected";
  };
};

type GroupHistoryPoint = {
  month: string;
  actual: number;
};

type MemberIntelligence = {
  forecast?: number | null;
  confidence?: string | null;
  bestModel?: string | null;
  status: "loading" | "loaded" | "unavailable";
};

type MemberRecommendation = {
  action: string;
  priority: string;
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

function actionClass(action: string) {
  switch (action) {
    case "purchase": return "border-blue-200 bg-blue-50 text-blue-700";
    case "review": return "border-amber-200 bg-amber-50 text-amber-700";
    case "excess_stock": return "border-purple-200 bg-purple-50 text-purple-700";
    case "dead_stock": return "border-red-200 bg-red-50 text-red-700";
    default: return "border-slate-200 bg-slate-50 text-slate-700";
  }
}

function priorityRowClass(priority: string) {
  if (priority === "high") return "border-l-4 border-l-red-500 bg-red-50/15 hover:bg-red-50/30";
  if (priority === "medium") return "border-l-4 border-l-amber-500 bg-amber-50/10 hover:bg-amber-50/25";
  return "border-l-4 border-l-emerald-500/40 bg-white hover:bg-slate-50";
}

function displayLabel(value: string) {
  return value.replace(/_/g, " ");
}

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const detailCache = new Map<number, MainProductDetail>();
const groupHistoryCache = new Map<number, GroupHistoryPoint[]>();
const memberIntelligenceCache = new Map<number, MemberIntelligence>();

export default function MainProductsPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [groups, setGroups] = useState<MainProductListItem[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null);
  const [detail, setDetail] = useState<MainProductDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [groupHistory, setGroupHistory] = useState<GroupHistoryPoint[]>([]);
  const [groupHistoryLoading, setGroupHistoryLoading] = useState(false);
  const [groupHistoryError, setGroupHistoryError] = useState("");
  const [recommendationsMap, setRecommendationsMap] = useState<Record<number, MemberRecommendation>>({});
  const [memberIntelligenceMap, setMemberIntelligenceMap] = useState<Record<number, MemberIntelligence>>({});

  // PO Flow States
  const [isPoModalOpen, setIsPoModalOpen] = useState(false);
  const [orderQuantity, setOrderQuantity] = useState<number | string>(0);
  const [poSubmitting, setPoSubmitting] = useState(false);
  const [poSuccess, setPoSuccess] = useState<{ po_number: string; quantity: number } | null>(null);
  const [poError, setPoError] = useState("");

  // Secondary Member Product Modal State (Part 1 Routing Fix)
  const [selectedMemberProductId, setSelectedMemberProductId] = useState<number | null>(null);
  const [memberDetailData, setMemberDetailData] = useState<any>(null);
  const [memberDetailLoading, setMemberDetailLoading] = useState(false);
  const [memberDetailError, setMemberDetailError] = useState("");
  const [memberHistoryData, setMemberHistoryData] = useState<GroupHistoryPoint[]>([]);
  const [memberHistoryLoading, setMemberHistoryLoading] = useState(false);

  const requestId = useRef(0);

  const handleLogout = useCallback(() => {
    sessionStorage.removeItem("auth_token");
    sessionStorage.removeItem("user");
    router.push("/login");
  }, [router]);

  useEffect(() => {
    const storedToken = sessionStorage.getItem("auth_token");
    const storedUser = sessionStorage.getItem("user");
    if (!storedToken || !storedUser) {
      router.push("/login");
      return;
    }

    try {
      const parsedUser = JSON.parse(storedUser) as User;
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setToken(storedToken);
      setUser(parsedUser);
    } catch {
      router.push("/login");
    }
  }, [router]);

  const loadGroups = useCallback(async () => {
    if (!token) return;
    setListLoading(true);
    setListError("");
    try {
      const response = await fetch(`${API_BASE}/api/main-products`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error("Failed to load main-product groups");
      const data: MainProductListItem[] = await response.json();
      setGroups(data);
    } catch (error) {
      setListError(error instanceof Error ? error.message : "Unable to connect to backend");
    } finally {
      setListLoading(false);
    }
  }, [token]);

  const loadRecommendations = useCallback(async () => {
    if (!token) return;
    try {
      const response = await fetch(`${API_BASE}/api/inventory/recommendations`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) return;
      const data = await response.json();
      if (Array.isArray(data)) {
        const map: Record<number, MemberRecommendation> = {};
        for (const item of data) {
          if (item && item.product_id) {
            map[item.product_id] = {
              action: item.action,
              priority: item.priority,
            };
          }
        }
        setRecommendationsMap(map);
      }
    } catch {
      // optional enrichment
    }
  }, [token]);

  useEffect(() => {
    if (!token) return;
    const timeoutId = window.setTimeout(() => {
      void loadGroups();
      void loadRecommendations();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [token, loadGroups, loadRecommendations]);

  const fetchMembersIntelligence = useCallback(async (members: MainProductMember[], currentReqId: number) => {
    if (!token || members.length === 0) return;

    const initialMap: Record<number, MemberIntelligence> = {};
    const missingMembers: MainProductMember[] = [];

    for (const member of members) {
      const cached = memberIntelligenceCache.get(member.product_id);
      if (cached) {
        initialMap[member.product_id] = cached;
      } else {
        initialMap[member.product_id] = { status: "loading" };
        missingMembers.push(member);
      }
    }
    setMemberIntelligenceMap(initialMap);

    if (missingMembers.length === 0) return;

    const promises = missingMembers.map(async (member) => {
      try {
        const response = await fetch(
          `${API_BASE}/api/forecast/product/${member.product_id}`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        if (!response.ok) {
          const resObj: MemberIntelligence = {
            forecast: null,
            confidence: null,
            bestModel: null,
            status: "unavailable",
          };
          memberIntelligenceCache.set(member.product_id, resObj);
          return { productId: member.product_id, intelligence: resObj };
        }
        const data = await response.json();
        const resObj: MemberIntelligence = {
          forecast: data.next_month_forecast,
          confidence: data.confidence,
          bestModel: data.best_model,
          status: "loaded",
        };
        memberIntelligenceCache.set(member.product_id, resObj);
        return { productId: member.product_id, intelligence: resObj };
      } catch {
        const resObj: MemberIntelligence = {
          forecast: null,
          confidence: null,
          bestModel: null,
          status: "unavailable",
        };
        memberIntelligenceCache.set(member.product_id, resObj);
        return { productId: member.product_id, intelligence: resObj };
      }
    });

    const results = await Promise.all(promises);
    if (currentReqId === requestId.current) {
      setMemberIntelligenceMap(prev => {
        const next = { ...prev };
        for (const r of results) {
          next[r.productId] = r.intelligence;
        }
        return next;
      });
    }
  }, [token]);

  const openDetail = useCallback(async (templateId: number) => {
    const currentRequest = ++requestId.current;
    setSelectedTemplateId(templateId);
    setIsPoModalOpen(false);
    setPoSuccess(null);
    setPoError("");

    const cachedDetail = detailCache.get(templateId);
    const cachedHistory = groupHistoryCache.get(templateId);

    // 1. Instantly populate safe detail data
    if (cachedDetail) {
      setDetail(cachedDetail);
      setDetailLoading(false);
      setDetailError("");
      const suggested = Number(cachedDetail.recommendation?.group_suggested_purchase_qty || 0);
      setOrderQuantity(suggested > 0 ? suggested : 0);
      if (cachedDetail.group && Array.isArray(cachedDetail.group.members)) {
        void fetchMembersIntelligence(cachedDetail.group.members, currentRequest);
      }
    } else {
      const existingGroup = groups.find(g => g.main_product_template_id === templateId);
      if (existingGroup) {
        setDetail({
          main_product: {
            template_id: existingGroup.main_product_template_id,
            name: existingGroup.main_product_name,
            is_main_similar: true,
            current_stock: existingGroup.group_current_stock,
            usable_qty: existingGroup.group_usable_qty,
            cut_piece_qty: existingGroup.group_cut_piece_qty,
          },
          group: {
            group_valid: existingGroup.group_valid,
            group_size: existingGroup.group_size,
            validation_issues: [],
            validation_warnings: [],
            persisted_group_valid: existingGroup.group_valid,
            persisted_validation_issues: [],
            persisted_validation_warnings: [],
            total_current_stock: existingGroup.group_current_stock,
            total_usable_qty: existingGroup.group_usable_qty,
            total_cut_piece_qty: existingGroup.group_cut_piece_qty,
            members: [],
          },
          forecast: {
            forecast_scope: existingGroup.forecast_scope,
            main_product_template_id: existingGroup.main_product_template_id,
            main_product_name: existingGroup.main_product_name,
            group_size: existingGroup.group_size,
            months_available: null,
            history_start: null,
            history_end: null,
            next_month_forecast: existingGroup.group_next_month_forecast,
            best_model: existingGroup.best_model,
            confidence: existingGroup.confidence,
            mae: null,
            wape: null,
            mase: null,
            avg_monthly_demand: null,
            forecast_status: existingGroup.forecast_status,
          },
          recommendation: {
            recommendation_scope: existingGroup.recommendation_scope,
            main_product_template_id: existingGroup.main_product_template_id,
            main_product_name: existingGroup.main_product_name,
            group_size: existingGroup.group_size,
            group_valid: existingGroup.group_valid,
            group_current_stock: existingGroup.group_current_stock,
            group_next_month_forecast: existingGroup.group_next_month_forecast,
            best_model: existingGroup.best_model,
            confidence: existingGroup.confidence,
            group_reorder_point: existingGroup.group_reorder_point,
            group_buffered_target_stock: existingGroup.group_buffered_target_stock,
            group_stock_gap: existingGroup.group_stock_gap,
            group_coverage_ratio: null,
            group_suggested_purchase_qty: existingGroup.group_suggested_purchase_qty,
            action: existingGroup.action,
            priority: existingGroup.priority,
            reason_codes: [],
            validation_issues: [],
            validation_warnings: [],
            recommendation_status: "persisted",
            approval_status: existingGroup.approval_status,
          },
        });
        const suggested = Number(existingGroup.group_suggested_purchase_qty || 0);
        setOrderQuantity(suggested > 0 ? suggested : 0);
        setDetailLoading(false);
      } else {
        setDetail(null);
        setDetailLoading(true);
      }
      setDetailError("");
    }

    // 2. Instantly populate cached history or show loading
    if (cachedHistory) {
      setGroupHistory(cachedHistory);
      setGroupHistoryLoading(false);
      setGroupHistoryError("");
    } else {
      setGroupHistory([]);
      setGroupHistoryLoading(true);
      setGroupHistoryError("");
    }

    // 3. INDEPENDENT Group Demand History Fetch (with timeout & safety)
    const historyController = new AbortController();
    const historyTimeout = setTimeout(() => historyController.abort(), 6000);

    fetch(`${API_BASE}/api/products/${templateId}/group/history`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: historyController.signal,
    })
      .then(async res => {
        clearTimeout(historyTimeout);
        if (!res.ok) throw new Error("Unable to load group demand history");
        const data = await res.json();
        const points: GroupHistoryPoint[] = Array.isArray(data)
          ? data
          : (Array.isArray(data?.months) ? data.months : []);
        if (currentRequest === requestId.current) {
          groupHistoryCache.set(templateId, points);
          setGroupHistory(points);
          setGroupHistoryLoading(false);
          setGroupHistoryError("");
        }
      })
      .catch(err => {
        clearTimeout(historyTimeout);
        if (currentRequest === requestId.current) {
          setGroupHistoryLoading(false);
          if (!cachedHistory) {
            setGroupHistoryError(
              err?.name === "AbortError"
                ? "Group demand history request timed out"
                : "Unable to load group demand history"
            );
          }
        }
      });

    // 4. INDEPENDENT Main Product Detail Fetch
    fetch(`${API_BASE}/api/main-products/${templateId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async res => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || "Failed to load main-product detail");
        }
        const data = (await res.json()) as MainProductDetail;
        if (currentRequest === requestId.current) {
          detailCache.set(templateId, data);
          setDetail(data);
          setDetailLoading(false);
          setDetailError("");
          const suggested = Number(data.recommendation?.group_suggested_purchase_qty || 0);
          setOrderQuantity(suggested > 0 ? suggested : 0);
          if (data.group && Array.isArray(data.group.members)) {
            void fetchMembersIntelligence(data.group.members, currentRequest);
          }
        }
      })
      .catch(err => {
        if (currentRequest === requestId.current) {
          setDetailLoading(false);
          if (!cachedDetail && !groups.some(g => g.main_product_template_id === templateId)) {
            setDetailError(err instanceof Error ? err.message : "Unable to load group detail");
          }
        }
      });
  }, [token, groups, fetchMembersIntelligence]);

  const closeDetail = useCallback(() => {
    requestId.current += 1;
    setSelectedTemplateId(null);
    setDetail(null);
    setDetailError("");
    setDetailLoading(false);
    setGroupHistory([]);
    setGroupHistoryError("");
    setGroupHistoryLoading(false);
    setMemberIntelligenceMap({});
    setIsPoModalOpen(false);
    setPoSuccess(null);
    setPoError("");
  }, []);

  const closeIndividualProduct = useCallback(() => {
    setSelectedMemberProductId(null);
    setMemberDetailData(null);
    setMemberDetailError("");
    setMemberHistoryData([]);
  }, []);

  const openIndividualProduct = useCallback((productId: number) => {
    if (!token) return;
    setSelectedMemberProductId(productId);
    setMemberDetailData(null);
    setMemberDetailError("");
    setMemberDetailLoading(true);
    setMemberHistoryData([]);
    setMemberHistoryLoading(true);

    fetch(`${API_BASE}/api/forecast/product/${productId}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(async res => {
        if (!res.ok) throw new Error("Failed to load product detail");
        const data = await res.json();
        setMemberDetailData(data);
      })
      .catch(err => {
        setMemberDetailError(err instanceof Error ? err.message : "Error loading detail");
      })
      .finally(() => {
        setMemberDetailLoading(false);
      });

    fetch(`${API_BASE}/api/forecast/product/${productId}/history`, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(async res => {
        if (!res.ok) throw new Error("Failed to load product history");
        const data = await res.json();
        setMemberHistoryData(Array.isArray(data) ? data : []);
      })
      .catch(() => {
        setMemberHistoryData([]);
      })
      .finally(() => {
        setMemberHistoryLoading(false);
      });
  }, [token]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        if (selectedMemberProductId !== null) {
          closeIndividualProduct();
        } else if (isPoModalOpen) {
          setIsPoModalOpen(false);
        } else if (selectedTemplateId !== null) {
          closeDetail();
        }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedTemplateId, isPoModalOpen, selectedMemberProductId, closeDetail, closeIndividualProduct]);

  useEffect(() => {
    if (selectedTemplateId !== null) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [selectedTemplateId]);



  async function handleConfirmPo() {
    if (!detail || !token) return;
    const qty = Number(orderQuantity);
    if (isNaN(qty) || qty <= 0) {
      setPoError("Please enter a valid positive quantity");
      return;
    }

    setPoSubmitting(true);
    setPoError("");
    try {
      const response = await fetch(
        `${API_BASE}/api/main-products/${detail.main_product.template_id}/create-po`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ quantity: qty }),
        },
      );

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to create Purchase Order");
      }

      const resData = await response.json();
      setPoSuccess({ po_number: resData.po_number, quantity: resData.quantity });
      setIsPoModalOpen(false);
      void loadGroups();
    } catch (err) {
      setPoError(err instanceof Error ? err.message : "Error creating purchase order");
    } finally {
      setPoSubmitting(false);
    }
  }

  if (!token || !user) return null;

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50 text-slate-900 font-sans">
      {isSidebarOpen && (
        <div className="fixed inset-0 z-20 bg-slate-900/50 lg:hidden" onClick={() => setIsSidebarOpen(false)} />
      )}

      {/* Sidebar */}
      <aside className={`fixed inset-y-0 left-0 z-30 flex w-64 flex-col justify-between border-r border-slate-200 bg-white transition-transform lg:static lg:translate-x-0 ${isSidebarOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div>
          <div className="flex h-16 items-center border-b border-slate-200 px-6">
            <span className="text-lg font-bold tracking-tight text-slate-900">Inventory Intelligence</span>
          </div>
          <nav className="space-y-1 p-4" aria-label="Primary navigation">
            <Link href="/" className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" /></svg>
              Overview
            </Link>
            <Link href="/main-products" className="flex w-full items-center gap-3 rounded-lg bg-blue-50 px-3 py-2 text-sm font-medium text-blue-700">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7h18M5 7v13h14V7M8 7V4h8v3m-8 5h8m-8 4h5" /></svg>
              Main Products
            </Link>
            <Link href="/recommendations" className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 12h6m-6 4h6" /></svg>
              Recommendations
            </Link>
            <Link href="/draft-pos" className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" /></svg>
              Draft POs
            </Link>
            <Link href="/account" className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
              Account
            </Link>
          </nav>
        </div>
        <div className="border-t border-slate-200 p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-sm font-bold text-slate-600">{user.name.charAt(0).toUpperCase()}</div>
            <div className="flex min-w-0 flex-1 flex-col">
              <span className="truncate text-sm font-medium text-slate-900">{user.name}</span>
              <span className="truncate text-xs text-slate-500">{user.email}</span>
            </div>
            <button onClick={handleLogout} className="text-slate-400 hover:text-slate-600" title="Logout" aria-label="Logout">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" /></svg>
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
          <div className="flex items-center gap-4">
            <button onClick={() => setIsSidebarOpen(true)} className="text-slate-500 lg:hidden" aria-label="Open navigation">
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" /></svg>
            </button>
            <h1 className="text-lg font-semibold text-slate-900">Main Products</h1>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-6 lg:p-8">
          <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold text-slate-900">Main Products</h2>
              <p className="mt-1 text-sm text-slate-500">Group-level inventory intelligence, demand history, and replenishment</p>
            </div>
          </div>

          {listLoading ? (
            <div className="flex min-h-64 items-center justify-center rounded-xl border border-slate-200 bg-white">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
            </div>
          ) : listError ? (
            <section className="rounded-xl border border-red-200 bg-white p-8 text-center">
              <h3 className="font-semibold text-slate-900">Could not load main products</h3>
              <p className="mt-2 text-sm text-red-700">{listError}</p>
              <button onClick={loadGroups} className="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800">Retry</button>
            </section>
          ) : groups.length === 0 ? (
            <section className="rounded-xl border border-slate-200 bg-white px-6 py-16 text-center">
              <h3 className="font-semibold text-slate-900">No main-product groups available</h3>
              <p className="mt-2 text-sm text-slate-500">Product groups will appear here once configured.</p>
            </section>
          ) : (
            <section className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3" aria-label="Main products list">
              {groups.map(group => (
                <button
                  key={group.main_product_template_id}
                  type="button"
                  onClick={() => void openDetail(group.main_product_template_id)}
                  className={`group rounded-xl border border-slate-200 p-5 text-left shadow-sm transition-all hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${priorityRowClass(group.priority)}`}
                  aria-label={`Open main product ${group.main_product_name}`}
                >
                  {/* Top Bar: Title, Group Size & Action / Stock breakdown */}
                  <div className="flex items-start justify-between gap-3 border-b border-slate-100 pb-3">
                    <div className="min-w-0">
                      <p className="text-xs font-semibold uppercase tracking-wider text-blue-700">Main Product</p>
                      <h3 className="mt-1 truncate text-xl font-bold text-slate-900 group-hover:text-blue-800">{group.main_product_name}</h3>
                      <p className="mt-0.5 text-xs text-slate-500">{group.group_size} products</p>
                    </div>
                    <div className="flex flex-col items-end shrink-0 gap-1.5">
                      <span className={`rounded-md border px-2.5 py-1 text-xs font-semibold capitalize ${actionClass(group.action)}`}>
                        {displayLabel(group.action)}
                      </span>
                      <div className="flex items-center text-xs text-slate-600">
                        <span>Usable: <span className="font-semibold text-emerald-600">{formatNumber(group.group_usable_qty)}</span></span>
                        <span className="mx-1 text-slate-400">·</span>
                        <span>Cut-piece: <span className="font-semibold text-rose-600">{formatNumber(group.group_cut_piece_qty)}</span></span>
                      </div>
                    </div>
                  </div>

                  {/* Clean Metrics Grid */}
                  <div className="mt-3.5 grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                    <div className="rounded-lg bg-white/80 p-2.5 border border-slate-100">
                      <p className="text-xs font-medium text-slate-500">Forecast</p>
                      <p className="mt-1 text-base font-bold text-slate-900">{formatNumber(group.group_next_month_forecast)}</p>
                    </div>
                    <div className="rounded-lg bg-white/80 p-2.5 border border-slate-100">
                      <p className="text-xs font-medium text-slate-500">Total Stock</p>
                      <p className="mt-1 text-base font-bold text-slate-900">{formatNumber(group.group_current_stock)}</p>
                    </div>
                    <div className="rounded-lg bg-white/80 p-2.5 border border-slate-100">
                      <p className="text-xs font-medium text-slate-500">Suggested Purchase</p>
                      <p className="mt-1 text-base font-bold text-blue-900">{formatNumber(group.group_suggested_purchase_qty)} units</p>
                    </div>
                  </div>
                </button>
              ))}
            </section>
          )}
        </main>
      </div>

      {/* Main Product Detail Modal */}
      {selectedTemplateId !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center overflow-hidden bg-slate-900/50 p-3 sm:p-5" onClick={closeDetail} role="dialog" aria-modal="true">
          <section className="flex max-h-[94dvh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl" onClick={event => event.stopPropagation()}>

            {/* PART 4: CLEAN MODAL HEADER */}
            <header className="flex shrink-0 items-center justify-between border-b border-slate-200 bg-slate-50/80 px-6 py-4">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-wider text-blue-700">MAIN PRODUCT GROUP</p>
                {detail?.main_product.name ? (
                  <h2 className="mt-0.5 truncate text-2xl font-bold text-slate-900">
                    {detail.main_product.name}
                  </h2>
                ) : (
                  <div className="mt-1.5 h-7 w-48 rounded-md bg-slate-200 animate-pulse" />
                )}
              </div>
              <div className="flex items-center gap-4">
                {detail ? (
                  <span className="rounded-full bg-slate-100 border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-700">
                    {detail.group.group_size} products
                  </span>
                ) : (
                  <div className="h-6 w-24 rounded-full bg-slate-200 animate-pulse" />
                )}
                <button onClick={closeDetail} className="rounded-lg p-2 text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition-colors" aria-label="Close modal">
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              </div>
            </header>

            <div className="min-h-0 flex-1 overflow-y-auto p-6 space-y-6">
              {detailLoading && !detail ? (
                <div className="space-y-6">
                  {/* Skeleton Purchase Order Section */}
                  <section className="rounded-xl border border-blue-100 bg-blue-50/50 p-5 shadow-xs animate-pulse">
                    <div className="flex flex-wrap items-center justify-between gap-4">
                      <div className="space-y-2">
                        <div className="h-3 w-28 rounded bg-blue-200/80" />
                        <div className="h-5 w-48 rounded bg-blue-200/80" />
                        <div className="h-3 w-36 rounded bg-blue-200/80" />
                      </div>
                      <div className="h-10 w-44 rounded-lg bg-blue-200/90" />
                    </div>
                  </section>

                  {/* Skeleton Inventory Overview */}
                  <section className="space-y-3">
                    <div className="h-3.5 w-36 rounded bg-slate-200 animate-pulse" />
                    <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-3">
                      {[1, 2, 3].map(i => (
                        <div key={i} className="rounded-xl border border-slate-200 bg-white p-4.5 shadow-xs animate-pulse space-y-3">
                          <div className="h-3 w-28 rounded bg-slate-200" />
                          <div className="flex items-baseline justify-between gap-2">
                            <div className="h-7 w-28 rounded bg-slate-200" />
                            {i !== 2 && <div className="h-4 w-32 rounded bg-slate-200" />}
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>

                  {/* Skeleton Similar Products */}
                  <section className="space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="h-3.5 w-32 rounded bg-slate-200 animate-pulse" />
                      <div className="h-3 w-24 rounded bg-slate-200 animate-pulse" />
                    </div>
                    <div className="grid gap-3.5 sm:grid-cols-2">
                      {[1, 2].map(i => (
                        <div key={i} className="rounded-xl border border-slate-200 bg-white p-4.5 shadow-xs animate-pulse space-y-3.5">
                          <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
                            <div className="h-5 w-32 rounded bg-slate-200" />
                            <div className="h-5 w-24 rounded-full bg-slate-200" />
                          </div>
                          <div className="space-y-1.5">
                            <div className="h-3 w-28 rounded bg-slate-200" />
                            <div className="h-6 w-20 rounded bg-slate-200" />
                            <div className="h-3 w-36 rounded bg-slate-200" />
                          </div>
                          <div className="grid grid-cols-3 gap-2 pt-2 border-t border-slate-100">
                            <div className="h-12 rounded-lg bg-slate-100" />
                            <div className="h-12 rounded-lg bg-slate-100" />
                            <div className="h-12 rounded-lg bg-slate-100" />
                          </div>
                          <div className="pt-2 border-t border-slate-100">
                            <div className="h-3.5 w-44 rounded bg-slate-200" />
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>

                  {/* Skeleton Group Demand History */}
                  <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs animate-pulse space-y-4">
                    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
                      <div className="space-y-1.5">
                        <div className="h-4 w-40 rounded bg-slate-200" />
                        <div className="h-3 w-60 rounded bg-slate-200" />
                      </div>
                      <div className="h-7 w-48 rounded-lg bg-slate-200" />
                    </div>
                    <div className="h-56 rounded-xl bg-slate-100/80" />
                  </section>
                </div>
              ) : detailError && !detail ? (
                <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">{detailError}</div>
              ) : detail ? (
                <>
                  {/* PART 14: PURCHASE ORDER SECTION (TOP OF DETAIL) */}
                  {detail.group.group_valid && (
                    <section className="rounded-xl border border-blue-200 bg-blue-50/70 p-5 shadow-xs">
                      <div className="flex flex-wrap items-center justify-between gap-4">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-wider text-blue-800">PURCHASE ORDER</p>
                          <div className="mt-1 flex flex-wrap items-baseline gap-2">
                            <span className="text-sm font-medium text-slate-700">Main Product:</span>
                            <span className="text-base font-bold text-slate-900">{detail.main_product.name}</span>
                          </div>
                          <p className="mt-1 text-xs text-slate-600">
                            System Suggested Quantity: <span className="font-bold text-blue-900">{formatNumber(detail.recommendation.group_suggested_purchase_qty)}</span> units
                          </p>
                          {Number(detail.recommendation.group_suggested_purchase_qty) === 0 && (
                            <p className="mt-1 text-[11px] text-slate-500">
                              No purchase currently recommended — manual ordering is still available.
                            </p>
                          )}
                          {poSuccess && (
                            <p className="mt-2 text-xs font-semibold text-emerald-700">
                              ✓ Purchase Order <span className="font-bold">{poSuccess.po_number}</span> confirmed for {formatNumber(poSuccess.quantity)} units
                            </p>
                          )}
                        </div>

                        <div>
                          <button
                            type="button"
                            onClick={() => {
                              const suggested = Number(detail.recommendation.group_suggested_purchase_qty) || 0;
                              setOrderQuantity(suggested > 0 ? suggested : 0);
                              setIsPoModalOpen(true);
                            }}
                            className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-all active:scale-[0.99]"
                          >
                            Create Purchase Order
                          </button>
                        </div>
                      </div>
                    </section>
                  )}

                  {/* PART 5 & 6: INVENTORY OVERVIEW (3 PRIMARY BOXES) */}
                  <section>
                    <div className="mb-3">
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Inventory Overview</h3>
                    </div>
                    <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-3">
                      {/* Box 1: On-hand Stock */}
                      <div className="rounded-xl border border-slate-200 bg-white p-4.5 shadow-xs">
                        <p className="text-xs font-medium uppercase tracking-wider text-slate-500">ON-HAND STOCK</p>
                        <div className="mt-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                          <p className="text-2xl font-bold tracking-tight text-slate-900">
                            {formatNumber(detail.main_product.current_stock)} <span className="text-xs font-normal text-slate-500">units</span>
                          </p>
                          <div className="flex items-center text-xs text-slate-600">
                            <span>
                              Usable: <span className="font-semibold text-emerald-600">{formatNumber(detail.main_product.usable_qty)}</span>
                            </span>
                            <span className="mx-1.5 text-slate-400">·</span>
                            <span>
                              Cut-piece: <span className="font-semibold text-rose-600">{formatNumber(detail.main_product.cut_piece_qty)}</span>
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Box 2: Forecasted Stock (Part 2 Odoo Projected Inventory) */}
                      <div className="rounded-xl border border-slate-200 bg-white p-4.5 shadow-xs">
                        <p className="text-xs font-medium uppercase tracking-wider text-slate-500">FORECASTED STOCK</p>
                        <div className="mt-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                          <p className="text-2xl font-bold tracking-tight text-slate-900">
                            {formatNumber(detail.group.total_forecasted_stock ?? detail.main_product.forecasted_stock)} <span className="text-xs font-normal text-slate-500">units</span>
                          </p>
                          <span className="mt-1 block w-full text-xs font-medium text-slate-500">
                            Odoo projected inventory position
                          </span>
                        </div>
                      </div>

                      {/* Box 3: Total Stock */}
                      <div className="rounded-xl border border-slate-200 bg-white p-4.5 shadow-xs">
                        <p className="text-xs font-medium uppercase tracking-wider text-slate-500">TOTAL STOCK</p>
                        <div className="mt-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                          <p className="text-2xl font-bold tracking-tight text-slate-900">
                            {formatNumber(detail.group.total_current_stock ?? detail.recommendation.group_current_stock)} <span className="text-xs font-normal text-slate-500">units</span>
                          </p>
                          <div className="flex items-center text-xs text-slate-600">
                            <span>
                              Usable: <span className="font-semibold text-emerald-600">{formatNumber(detail.group.total_usable_qty)}</span>
                            </span>
                            <span className="mx-1.5 text-slate-400">·</span>
                            <span>
                              Cut-piece: <span className="font-semibold text-rose-600">{formatNumber(detail.group.total_cut_piece_qty)}</span>
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </section>

                  {/* PART 7 & 8: SIMILAR PRODUCTS (GROUP MEMBERS) */}
                  <section>
                    <div className="mb-3 flex items-center justify-between">
                      <div>
                        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Similar Products</h3>
                      </div>
                      <span className="text-xs text-slate-500">{detail.group.members.length} group members</span>
                    </div>

                    <div className="grid gap-3.5 sm:grid-cols-2">
                      {detail.group.members.map(member => {
                        const isCanonical = member.template_id === detail.main_product.template_id;
                        const intel = memberIntelligenceMap[member.product_id];
                        const rec = recommendationsMap[member.product_id];

                        return (
                          <div
                            key={member.product_id}
                            className="flex flex-col justify-between rounded-xl border border-slate-200 bg-white p-4.5 shadow-xs transition-all hover:border-blue-300"
                          >
                            <div>
                              <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
                                <span className="text-base font-bold text-slate-900">{member.name ?? `Product ${member.product_id}`}</span>
                                <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-semibold border ${isCanonical ? "bg-blue-50 text-blue-800 border-blue-200" : "bg-slate-50 text-slate-700 border-slate-200"}`}>
                                  {isCanonical ? "Main Product" : "Similar Product"}
                                </span>
                              </div>

                              <div className="mt-3">
                                <span className="text-xs font-medium text-slate-500">Individual In-hand</span>
                                <p className="mt-0.5 text-lg font-bold text-slate-900">{formatNumber(member.current_stock)}</p>
                                <div className="mt-1 flex items-center text-xs text-slate-600">
                                  <span>Usable: <span className="font-semibold text-emerald-600">{formatNumber(member.usable_qty)}</span></span>
                                  <span className="mx-2 text-slate-400">·</span>
                                  <span>Cut-piece: <span className="font-semibold text-rose-600">{formatNumber(member.cut_piece_qty)}</span></span>
                                </div>
                              </div>

                              <div className="mt-3 grid grid-cols-3 gap-2 border-t border-slate-100 pt-3 text-xs">
                                <div className="rounded-lg bg-slate-50 p-2">
                                  <span className="text-[11px] font-medium text-slate-500 block">Individual Forecast</span>
                                  <span className="font-bold text-slate-900 mt-0.5 block">
                                    {!intel || intel.status === "loading" ? "..." : (intel.status === "unavailable" ? "—" : formatNumber(intel.forecast))}
                                  </span>
                                </div>
                                <div className="rounded-lg bg-slate-50 p-2">
                                  <span className="text-[11px] font-medium text-slate-500 block">Individual Action</span>
                                  <span className="font-semibold capitalize text-slate-800 mt-0.5 block">
                                    {rec?.action ? displayLabel(rec.action) : "—"}
                                  </span>
                                </div>
                                <div className="rounded-lg bg-slate-50 p-2">
                                  <span className="text-[11px] font-medium text-slate-500 block">Confidence</span>
                                  <span className="font-semibold capitalize text-slate-800 mt-0.5 block">
                                    {intel?.confidence ? displayLabel(intel.confidence) : "—"}
                                  </span>
                                </div>
                              </div>
                            </div>

                            <div className="mt-3.5 border-t border-slate-100 pt-2.5">
                              <button
                                type="button"
                                onClick={() => openIndividualProduct(member.product_id)}
                                className="group flex w-full items-center justify-between text-xs font-semibold text-blue-600 hover:text-blue-800"
                              >
                                <span>Open individual product detail</span>
                                <span className="transition-transform group-hover:translate-x-0.5">→</span>
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </section>

                  {/* PART 10: GROUP DEMAND HISTORY (YEAR-OVER-YEAR GRAPH + 3-MONTH FORECAST) */}
                  <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
                      <div>
                        <h3 className="text-base font-semibold text-slate-900">Group Demand History</h3>
                        <p className="text-xs text-slate-500">Year-over-year comparison & 3-month demand forecast</p>
                      </div>
                      <div className="flex items-center gap-2.5">
                        {detail.forecast.confidence && (
                          <span className="rounded-full bg-slate-100 border border-slate-200 px-2.5 py-0.5 text-xs font-medium text-slate-700 capitalize">
                            Confidence: {displayLabel(detail.forecast.confidence)}
                          </span>
                        )}
                        <span className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-bold text-blue-700">
                          Next Month Forecast: {formatNumber(detail.forecast.next_month_forecast)} units
                        </span>
                      </div>
                    </div>

                    {groupHistoryLoading ? (
                      <div className="flex h-56 items-center justify-center">
                        <div className="h-7 w-7 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
                      </div>
                    ) : groupHistoryError ? (
                      <div className="flex h-56 items-center justify-center text-sm font-medium text-red-600">{groupHistoryError}</div>
                    ) : groupHistory.length > 0 ? (
                      <GroupYearOverYearChart
                        history={groupHistory}
                        forecast3Months={detail.forecast.forecast_3_months || []}
                        nextMonthForecast={detail.forecast.next_month_forecast}
                      />
                    ) : (
                      <div className="flex h-56 items-center justify-center text-sm text-slate-500">No demand history recorded</div>
                    )}
                  </section>
                </>
              ) : null}
            </div>

            <footer className="flex shrink-0 justify-end border-t border-slate-200 bg-slate-50/80 px-6 py-3.5">
              <button onClick={closeDetail} className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors">
                Close
              </button>
            </footer>
          </section>
        </div>
      )}

      {/* PART 14: PURCHASE ORDER CONFIRMATION MODAL */}
      {isPoModalOpen && detail && (
        <div className="fixed inset-0 z-60 flex items-center justify-center overflow-hidden bg-slate-900/60 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-slate-200" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-lg font-bold text-slate-900">Purchase Order</h3>
              <button onClick={() => setIsPoModalOpen(false)} className="text-slate-400 hover:text-slate-600">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>

            <div className="mt-4 space-y-4">
              <div>
                <span className="block text-xs font-medium text-slate-500">Main Product</span>
                <span className="mt-0.5 block text-base font-bold text-slate-900">{detail.main_product.name}</span>
              </div>

              <div className="rounded-lg bg-blue-50/60 border border-blue-100 p-3 text-xs text-blue-900">
                <span className="font-semibold">System Suggested Quantity:</span>{" "}
                <span className="font-bold">{formatNumber(detail.recommendation.group_suggested_purchase_qty)}</span> units
              </div>

              <div>
                <label htmlFor="po-qty-input" className="block text-xs font-semibold text-slate-700">
                  Quantity to Order
                </label>
                <input
                  id="po-qty-input"
                  type="number"
                  step="any"
                  min="0"
                  value={orderQuantity}
                  onChange={e => setOrderQuantity(e.target.value)}
                  className="mt-1.5 block w-full rounded-lg border border-slate-300 px-3.5 py-2 text-base font-semibold text-slate-900 shadow-xs focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600"
                />
                <p className="mt-1.5 text-xs text-slate-500">
                  Suggested quantity is based on group forecast and inventory position.
                </p>
              </div>

              {poError && (
                <div className="rounded-lg bg-red-50 p-3 text-xs font-medium text-red-700">
                  {poError}
                </div>
              )}
            </div>

            <div className="mt-6 flex justify-end gap-3 border-t border-slate-100 pt-4">
              <button
                type="button"
                onClick={() => setIsPoModalOpen(false)}
                disabled={poSubmitting}
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmPo}
                disabled={poSubmitting}
                className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {poSubmitting ? "Confirming..." : "Confirm Purchase Order"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* INDIVIDUAL MEMBER PRODUCT DETAIL MODAL (NESTED OVER MAIN PRODUCT MODAL) */}
      {selectedMemberProductId !== null && (
        <div
          className="fixed inset-0 z-70 flex items-center justify-center p-3 sm:p-4 bg-slate-900/60 backdrop-blur-xs overflow-hidden"
          onClick={closeIndividualProduct}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="relative w-full max-w-3xl max-h-[90dvh] flex flex-col rounded-2xl bg-white shadow-2xl border border-slate-200 overflow-hidden"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/70 px-6 py-4 shrink-0">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-100 text-blue-800 font-bold text-sm">
                  {memberDetailData?.product_name ? memberDetailData.product_name.charAt(0).toUpperCase() : "P"}
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-900">
                    {memberDetailData?.product_name || `Product ${selectedMemberProductId}`}
                  </h3>
                  <p className="text-xs font-medium text-slate-500">Individual Product ID: {selectedMemberProductId}</p>
                </div>
              </div>
              <button
                onClick={closeIndividualProduct}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors"
                aria-label="Close modal"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {memberDetailLoading ? (
              <div className="flex h-56 items-center justify-center p-6">
                <div className="h-7 w-7 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
              </div>
            ) : memberDetailError ? (
              <div className="p-6 text-center text-sm text-red-600">{memberDetailError}</div>
            ) : memberDetailData ? (
              <div className="flex-1 overflow-y-auto p-6 space-y-5">
                {/* 2. Main Metrics (4 boxes) */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {/* In-hand Stock */}
                  <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-xs">
                    <span className="block text-xs font-medium text-slate-500">In-hand Stock</span>
                    <span className="mt-1 block text-lg font-bold text-slate-900">
                      {formatNumber(memberDetailData.current_stock ?? memberDetailData.stock_on_hand)} units
                    </span>
                    <div className="mt-1 flex items-center text-[11px] text-slate-600">
                      <span>Usable: <span className="font-semibold text-emerald-600">{formatNumber(memberDetailData.usable_qty)}</span></span>
                      <span className="mx-1 text-slate-400">·</span>
                      <span>Cut-piece: <span className="font-semibold text-rose-600">{formatNumber(memberDetailData.cut_piece_qty)}</span></span>
                    </div>
                  </div>

                  {/* Next Month Forecast */}
                  <div className="rounded-xl border border-blue-100 bg-blue-50/50 p-3.5 shadow-xs">
                    <span className="block text-xs font-medium text-blue-700">Next Month Forecast</span>
                    <span className="mt-1 block text-lg font-bold text-blue-900">
                      {formatNumber(memberDetailData.next_month_forecast)} units
                    </span>
                  </div>

                  {/* Target Stock */}
                  <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-xs">
                    <span className="block text-xs font-medium text-slate-500">Target Stock</span>
                    <span className="mt-1 block text-lg font-bold text-slate-900">
                      {formatNumber(memberDetailData.buffered_target_stock)} units
                    </span>
                  </div>

                  {/* Reorder Trigger */}
                  <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-xs">
                    <span className="block text-xs font-medium text-slate-500">Reorder Trigger</span>
                    <span className="mt-1 block text-lg font-bold text-slate-900">
                      {formatNumber(memberDetailData.reorder_point)} units
                    </span>
                  </div>
                </div>

                {/* Individual Product Demand History Graph */}
                <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
                    <div>
                      <h4 className="text-sm font-bold text-slate-900">Individual Product Demand History</h4>
                      <p className="text-xs text-slate-500">Historical monthly sales for product {selectedMemberProductId}</p>
                    </div>
                    <span className="rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-0.5 text-xs font-bold text-blue-700">
                      Forecast: {formatNumber(memberDetailData.next_month_forecast)} units
                    </span>
                  </div>

                  {memberHistoryLoading ? (
                    <div className="flex h-44 items-center justify-center">
                      <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600" />
                    </div>
                  ) : memberHistoryData.length > 0 ? (
                    <IndividualDemandChart data={memberHistoryData} forecast={memberDetailData.next_month_forecast} />
                  ) : (
                    <div className="flex h-44 items-center justify-center text-xs text-slate-500">No individual demand history recorded</div>
                  )}
                </section>
              </div>
            ) : null}

            <div className="flex justify-end border-t border-slate-200 bg-slate-50/80 px-6 py-3.5 shrink-0">
              <button
                type="button"
                onClick={closeIndividualProduct}
                className="rounded-lg bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800 transition-colors"
              >
                Back to Main Product
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// PART 10: YEAR-OVER-YEAR DEMAND & 3-MONTH FORECAST CHART
const IndividualDemandChart = memo(function IndividualDemandChart({
  data,
  forecast,
}: {
  data: GroupHistoryPoint[];
  forecast: number | null | undefined;
}) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const chartWidth = 660;
  const chartHeight = 180;
  const paddingLeft = 40;
  const paddingRight = 24;
  const paddingTop = 20;
  const paddingBottom = 28;

  const innerWidth = chartWidth - paddingLeft - paddingRight;
  const innerHeight = chartHeight - paddingTop - paddingBottom;

  const actuals = data.map((d) => d.actual);
  const maxActual = Math.max(...actuals, 10);
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

  const yTicks = [0, 0.5, 1].map((pct) => ({
    val: Math.round(minVal + pct * range),
    y: paddingTop + innerHeight - pct * innerHeight,
  }));

  const total = data.length;
  const xTickIndices: number[] = [];
  if (total <= 6) {
    for (let i = 0; i < total; i++) xTickIndices.push(i);
  } else {
    xTickIndices.push(0);
    const step = Math.floor(total / 4);
    for (let i = step; i < total - 1; i += step) {
      xTickIndices.push(i);
    }
    xTickIndices.push(total - 1);
  }

  return (
    <div className="relative w-full rounded-xl border border-slate-100 bg-slate-50/50 p-3" onMouseLeave={() => setHoveredIndex(null)}>
      <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="h-auto w-full select-none overflow-visible">
        <defs>
          <linearGradient id="indGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2563eb" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#2563eb" stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {yTicks.map((tick, idx) => (
          <g key={idx}>
            <line x1={paddingLeft} y1={tick.y} x2={chartWidth - paddingRight} y2={tick.y} stroke="#e2e8f0" strokeWidth="1" strokeDasharray={idx === 0 ? "none" : "3 3"} />
            <text x={paddingLeft - 6} y={tick.y + 4} fontSize="9" fill="#94a3b8" textAnchor="end" fontFamily="sans-serif">{tick.val}</text>
          </g>
        ))}

        {areaPath && <path d={areaPath} fill="url(#indGrad)" />}
        {linePath && <path d={linePath} fill="none" stroke="#2563eb" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />}

        {data.map((d, i) => {
          const cx = getX(i);
          const cy = getY(d.actual);
          const isHovered = i === hoveredIndex;
          return (
            <circle key={i} cx={cx} cy={cy} r={isHovered ? 5 : 3} fill={isHovered ? "#1d4ed8" : "#ffffff"} stroke="#2563eb" strokeWidth={2} />
          );
        })}

        {xTickIndices.map((i) => {
          const d = data[i];
          if (!d) return null;
          return (
            <text key={i} x={getX(i)} y={chartHeight - paddingBottom + 16} fontSize="9" fill="#64748b" textAnchor="middle" fontFamily="sans-serif">
              {d.month}
            </text>
          );
        })}

        {data.map((d, i) => {
          const cx = getX(i);
          const colWidth = innerWidth / (data.length > 1 ? data.length - 1 : 1);
          return (
            <rect key={`hit-${i}`} x={cx - colWidth / 2} y={paddingTop} width={colWidth} height={innerHeight + paddingBottom} fill="transparent" className="cursor-pointer" onMouseEnter={() => setHoveredIndex(i)} />
          );
        })}
      </svg>

      {hoveredIndex !== null && data[hoveredIndex] && (
        <div className="absolute top-2 right-2 rounded-md bg-slate-900 px-2.5 py-1 text-xs text-white shadow-md">
          <span className="font-medium text-slate-300">{data[hoveredIndex].month}: </span>
          <span className="font-bold text-white">{formatNumber(data[hoveredIndex].actual)} units</span>
        </div>
      )}
    </div>
  );
});

type GroupYearOverYearChartProps = {
  history: GroupHistoryPoint[];
  forecast3Months: ForecastStep[];
  nextMonthForecast: number | null | undefined;
};

const GroupYearOverYearChart = memo(function GroupYearOverYearChart({ history, forecast3Months, nextMonthForecast }: GroupYearOverYearChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const chartWidth = 760;
  const chartHeight = 250;
  const paddingLeft = 50;
  const paddingRight = 40;
  const paddingTop = 25;
  const paddingBottom = 40;

  const innerWidth = chartWidth - paddingLeft - paddingRight;
  const innerHeight = chartHeight - paddingTop - paddingBottom;

  // Determine latest actual year and month from dataset
  const lastActualPoint = history.length > 0 ? history[history.length - 1] : null;
  const lastActualMonthStr = lastActualPoint ? lastActualPoint.month : "2026-08";
  const [lastActualYearNum, lastActualMonthNum] = lastActualMonthStr.split("-").map(Number);

  const currentYear = lastActualYearNum || 2026;
  const prevYear = currentYear - 1;

  // Create lookups
  const historyMap = useMemo(() => {
    const map: Record<string, number> = {};
    for (const item of history) {
      map[item.month] = item.actual;
    }
    return map;
  }, [history]);

  // Construct 12 month slots (Jan - Dec)
  // Prev year: Jan-Dec of prevYear
  const prevYearData = useMemo(() => {
    return Array.from({ length: 12 }).map((_, mIdx) => {
      const monthStr = `${prevYear}-${String(mIdx + 1).padStart(2, "0")}`;
      return {
        monthIndex: mIdx,
        monthName: MONTH_NAMES[mIdx],
        monthStr,
        actual: historyMap[monthStr] !== undefined ? historyMap[monthStr] : null,
      };
    });
  }, [prevYear, historyMap]);

  // Current year: Jan to latest available actual month
  const currYearData = useMemo(() => {
    return Array.from({ length: 12 }).map((_, mIdx) => {
      const monthNum = mIdx + 1;
      const monthStr = `${currentYear}-${String(monthNum).padStart(2, "0")}`;
      const isActualAvailable = monthNum <= lastActualMonthNum && historyMap[monthStr] !== undefined;
      return {
        monthIndex: mIdx,
        monthName: MONTH_NAMES[mIdx],
        monthStr,
        isActual: isActualAvailable,
        actual: isActualAvailable ? historyMap[monthStr] : null,
      };
    });
  }, [currentYear, lastActualMonthNum, historyMap]);

  // 3-Month Forecast points
  const forecastPoints = useMemo(() => {
    if (!forecast3Months || forecast3Months.length === 0) {
      if (nextMonthForecast !== null && nextMonthForecast !== undefined && lastActualMonthNum < 12) {
        return [{
          monthIndex: lastActualMonthNum,
          monthName: MONTH_NAMES[lastActualMonthNum],
          monthStr: `${currentYear}-${String(lastActualMonthNum + 1).padStart(2, "0")}`,
          forecast: nextMonthForecast,
        }];
      }
      return [];
    }
    return forecast3Months.map(fc => {
      const [y, m] = fc.month.split("-").map(Number);
      const mIdx = (m - 1) % 12;
      return {
        monthIndex: mIdx,
        monthName: MONTH_NAMES[mIdx],
        monthStr: fc.month,
        forecast: fc.forecast,
      };
    });
  }, [forecast3Months, nextMonthForecast, lastActualMonthNum, currentYear]);

  // Calculate scales
  const allValues: number[] = [
    ...prevYearData.map(d => d.actual ?? 0),
    ...currYearData.filter(d => d.actual !== null).map(d => d.actual ?? 0),
    ...forecastPoints.map(d => d.forecast),
  ];
  const maxVal = Math.max(...allValues, 10);
  const niceMax = Math.ceil(maxVal * 1.15);
  const minVal = 0;
  const range = niceMax - minVal;

  const getX = (monthIndex: number) => {
    return paddingLeft + (monthIndex / 11) * innerWidth;
  };

  const getY = (val: number) => {
    if (range === 0) return paddingTop + innerHeight / 2;
    return paddingTop + innerHeight - ((val - minVal) / range) * innerHeight;
  };

  // SVG Paths
  // 1. Previous Year Line (Solid slate)
  const prevPoints = prevYearData.filter(d => d.actual !== null).map(d => `${getX(d.monthIndex)},${getY(d.actual!)}`);
  const prevLinePath = prevPoints.length > 0 ? `M ${prevPoints.join(" L ")}` : "";

  // 2. Current Year Line (Solid blue)
  const currPoints = currYearData.filter(d => d.actual !== null).map(d => `${getX(d.monthIndex)},${getY(d.actual!)}`);
  const currLinePath = currPoints.length > 0 ? `M ${currPoints.join(" L ")}` : "";

  // 3. Forecast Line (Dashed blue starting from last actual point)
  const lastActualMonthIdx = lastActualMonthNum - 1;
  const lastActualVal = historyMap[lastActualMonthStr] ?? 0;
  const forecastCoords = [
    `${getX(lastActualMonthIdx)},${getY(lastActualVal)}`,
    ...forecastPoints.map(f => `${getX(f.monthIndex)},${getY(f.forecast)}`),
  ];
  const forecastLinePath = forecastPoints.length > 0 ? `M ${forecastCoords.join(" L ")}` : "";

  // Horizontal ticks
  const yTicks = [0, 0.33, 0.66, 1].map(pct => ({
    val: Math.round(minVal + pct * range),
    y: paddingTop + innerHeight - pct * innerHeight,
  }));

  return (
    <div className="space-y-4">
      <div className="relative w-full rounded-xl border border-slate-100 bg-slate-50/50 p-3" onMouseLeave={() => setHoveredIndex(null)}>
        <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="h-auto w-full select-none overflow-visible">
          {/* Grid lines */}
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

          {/* Line 1: Previous Year (Solid Slate) */}
          {prevLinePath && (
            <path
              d={prevLinePath}
              fill="none"
              stroke="#94a3b8"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          {/* Points for Previous Year */}
          {prevYearData.filter(d => d.actual !== null).map(d => (
            <circle
              key={`prev-${d.monthIndex}`}
              cx={getX(d.monthIndex)}
              cy={getY(d.actual!)}
              r={hoveredIndex === d.monthIndex ? 4.5 : 3}
              fill="#ffffff"
              stroke="#94a3b8"
              strokeWidth="2"
            />
          ))}

          {/* Line 2: Current Year (Solid Vibrant Blue) */}
          {currLinePath && (
            <path
              d={currLinePath}
              fill="none"
              stroke="#2563eb"
              strokeWidth="2.75"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          {/* Points for Current Year Actuals */}
          {currYearData.filter(d => d.actual !== null).map(d => (
            <circle
              key={`curr-${d.monthIndex}`}
              cx={getX(d.monthIndex)}
              cy={getY(d.actual!)}
              r={hoveredIndex === d.monthIndex ? 5.5 : 3.75}
              fill={hoveredIndex === d.monthIndex ? "#1d4ed8" : "#ffffff"}
              stroke="#2563eb"
              strokeWidth="2.5"
            />
          ))}

          {/* Line 3: 3-Month Forecast Line (Dashed Blue) */}
          {forecastLinePath && (
            <path
              d={forecastLinePath}
              fill="none"
              stroke="#3b82f6"
              strokeWidth="2.5"
              strokeDasharray="4 4"
              strokeLinecap="round"
            />
          )}

          {/* Points for Forecast Months */}
          {forecastPoints.map(f => (
            <g key={`fc-${f.monthIndex}`}>
              <circle
                cx={getX(f.monthIndex)}
                cy={getY(f.forecast)}
                r={hoveredIndex === f.monthIndex ? 8 : 6.5}
                fill="none"
                stroke="#3b82f6"
                strokeWidth="1.5"
                strokeDasharray="2 2"
                className="animate-pulse"
              />
              <circle
                cx={getX(f.monthIndex)}
                cy={getY(f.forecast)}
                r={hoveredIndex === f.monthIndex ? 5 : 4}
                fill="#2563eb"
                stroke="#ffffff"
                strokeWidth="2"
              />
            </g>
          ))}

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

          {/* X Axis Month Labels (Jan - Dec) */}
          {MONTH_NAMES.map((mName, i) => (
            <text
              key={i}
              x={getX(i)}
              y={chartHeight - paddingBottom + 18}
              fontSize="10"
              fill={hoveredIndex === i ? "#0f172a" : "#64748b"}
              fontWeight={hoveredIndex === i ? "700" : "500"}
              textAnchor="middle"
              fontFamily="sans-serif"
            >
              {mName}
            </text>
          ))}

          {/* Invisible interactive columns for smooth hover interaction */}
          {Array.from({ length: 12 }).map((_, i) => {
            const cx = getX(i);
            const colWidth = innerWidth / 11;
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
              />
            );
          })}
        </svg>

        {/* Hover Tooltip */}
        {hoveredIndex !== null && (() => {
          const mIdx = hoveredIndex;
          const mName = MONTH_NAMES[mIdx];
          const prevD = prevYearData[mIdx];
          const currD = currYearData[mIdx];
          const fcD = forecastPoints.find(f => f.monthIndex === mIdx);

          const xPct = (getX(mIdx) / chartWidth) * 100;
          let tooltipTranslateX = "-50%";
          if (mIdx === 0 || xPct < 22) tooltipTranslateX = "0%";
          else if (mIdx === 11 || xPct > 78) tooltipTranslateX = "-100%";

          return (
            <div
              className="pointer-events-none absolute z-30 min-w-max rounded-lg border border-slate-700 bg-slate-900/95 px-3 py-2 text-xs text-white shadow-xl backdrop-blur-xs"
              style={{
                left: `${xPct}%`,
                top: "15%",
                transform: `translate(${tooltipTranslateX}, 0)`,
              }}
            >
              <p className="font-bold text-slate-200 border-b border-slate-700 pb-1 mb-1.5">{mName}</p>

              {prevD && prevD.actual !== null && (
                <div className="flex items-center justify-between gap-4 text-slate-300">
                  <span className="flex items-center gap-1.5 text-slate-400">
                    <span className="h-2 w-2 rounded-full bg-slate-400" />
                    Previous Year ({prevYear}):
                  </span>
                  <span className="font-semibold text-white">{formatNumber(prevD.actual)} units</span>
                </div>
              )}

              {currD && currD.actual !== null && (
                <div className="mt-1 flex items-center justify-between gap-4 text-slate-300">
                  <span className="flex items-center gap-1.5 text-blue-400">
                    <span className="h-2 w-2 rounded-full bg-blue-500" />
                    Current Year ({currentYear}):
                  </span>
                  <span className="font-semibold text-white">{formatNumber(currD.actual)} units</span>
                </div>
              )}

              {fcD && (
                <div className="mt-1 flex items-center justify-between gap-4 text-blue-200 font-bold">
                  <span className="flex items-center gap-1.5 text-blue-400">
                    <span className="h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
                    Forecast:
                  </span>
                  <span className="font-bold text-blue-200">{formatNumber(fcD.forecast)} units</span>
                </div>
              )}
            </div>
          );
        })()}
      </div>

      {/* Chart Legend */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-t border-slate-100 pt-3 text-xs">
        <div className="flex flex-wrap items-center gap-5 text-slate-600">
          <div className="flex items-center gap-2">
            <span className="inline-block h-2.5 w-4 rounded-full bg-slate-400" />
            <span className="font-medium">Previous Year ({prevYear})</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-block h-2.5 w-4 rounded-full bg-blue-600" />
            <span className="font-medium">Current Year ({currentYear})</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-block h-2.5 w-4 rounded-full border border-dashed border-blue-600 bg-blue-100" />
            <span className="font-medium text-blue-700">Next 3 Months Forecast</span>
          </div>
        </div>

        {lastActualPoint && (
          <div className="text-xs text-slate-500">
            Latest recorded: <span className="font-semibold text-slate-800">{lastActualPoint.month}</span> ({formatNumber(lastActualPoint.actual)} units)
          </div>
        )}
      </div>
    </div>
  );
});