"use client";

import { usePathname } from "next/navigation";
import { findNavItem } from "@/lib/nav";
import type { Readiness, SystemInfo } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { StatusPill } from "./StatusPill";

export function Topbar() {
  const pathname = usePathname();
  const item = findNavItem(pathname);
  const info = useApi<SystemInfo>("/api/v1/system/info", 30_000);
  const ready = useApi<Readiness>("/health/ready", 15_000);

  const backendTone = ready.error ? "bad" : ready.data?.status === "ok" ? "good" : ready.data ? "warn" : "neutral";
  const backendLabel = ready.error ? "API offline" : ready.data?.status === "ok" ? "API ready" : ready.data ? "API degraded" : "Connecting…";
  const mode = info.data?.trading_mode;

  return (
    <header className="flex h-14 items-center justify-between gap-4 border-b border-border bg-panel px-4 pl-14 md:px-8">
      <h1 className="truncate text-sm font-medium">{item?.label ?? "MarketOS"}</h1>
      <div className="flex items-center gap-2">
        {mode && (
          <StatusPill tone={mode === "live" ? "bad" : "accent"}>
            {mode === "live" ? "LIVE" : mode === "paper" ? "PAPER" : "TRADING OFF"}
          </StatusPill>
        )}
        <StatusPill tone={backendTone}>
          <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />
          {backendLabel}
        </StatusPill>
      </div>
    </header>
  );
}
