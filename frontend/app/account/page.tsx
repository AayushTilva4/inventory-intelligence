"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import AppLayout, { User } from "@/components/AppLayout";

export default function AccountPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

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
    router.push("/login");
  };

  return (
    <AppLayout>
      <div className="space-y-6 max-w-3xl mx-auto">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">Account &amp; System Settings</h1>
          <p className="text-sm text-slate-500 mt-0.5">User profile, workspace configuration, and POC system parameters.</p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-xs">
          <div className="border-b border-slate-200 px-6 py-4 bg-slate-50">
            <h2 className="text-sm font-bold text-slate-900">User Profile</h2>
          </div>
          <div className="p-6 space-y-4 text-sm">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-1">
              <span className="text-slate-500 font-medium">Name</span>
              <span className="sm:col-span-2 font-semibold text-slate-900">{user?.name || "Admin User"}</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-1">
              <span className="text-slate-500 font-medium">Email</span>
              <span className="sm:col-span-2 font-semibold text-slate-900">{user?.email || "admin@example.com"}</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-1">
              <span className="text-slate-500 font-medium">Role</span>
              <span className="sm:col-span-2 font-semibold text-slate-900">Inventory Intelligence Planner</span>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-xs">
          <div className="border-b border-slate-200 px-6 py-4 bg-slate-50">
            <h2 className="text-sm font-bold text-slate-900">POC System Configuration</h2>
          </div>
          <div className="p-6 space-y-4 text-sm">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-1">
              <span className="text-slate-500 font-medium">Forecasting Model</span>
              <span className="sm:col-span-2 font-mono font-bold text-blue-700">trimmed_mean_3 (Champion)</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-1">
              <span className="text-slate-500 font-medium">Dataset Scope</span>
              <span className="sm:col-span-2 font-semibold text-slate-900">1,000 Catalog Products / 985 Main Product Groups</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-1">
              <span className="text-slate-500 font-medium">ERP Isolation</span>
              <span className="sm:col-span-2 font-semibold text-emerald-700">Odoo 100% Read-Only (0 writes, 0 RFQs)</span>
            </div>
          </div>
        </div>

        <div className="flex justify-end pt-2">
          <button
            onClick={handleLogout}
            className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white font-semibold text-xs transition-colors"
          >
            Sign Out
          </button>
        </div>
      </div>
    </AppLayout>
  );
}
