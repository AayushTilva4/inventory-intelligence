"use client";

import { ReactNode } from "react";
import { PlanningRunProvider } from "./PlanningRunContext";

export function Providers({ children }: { children: ReactNode }) {
  return <PlanningRunProvider>{children}</PlanningRunProvider>;
}
