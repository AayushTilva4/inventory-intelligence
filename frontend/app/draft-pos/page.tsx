"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function DraftPOsRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/recommendations");
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 font-sans">
      <div className="text-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-blue-600 mx-auto"></div>
        <p className="mt-4 text-sm font-medium text-slate-600">Redirecting to Recommendations...</p>
      </div>
    </div>
  );
}
