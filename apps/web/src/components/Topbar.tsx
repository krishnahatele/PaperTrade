"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { apiSend } from "@/lib/api";
import { signalUnauthorized } from "@/lib/auth";
import { findNavItem } from "@/lib/nav";
import type { Readiness, SystemInfo } from "@/lib/api";
import type { RuntimeSettings } from "@/lib/types";
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
  const settings = useApi<RuntimeSettings>("/api/v1/settings", 10_000);
  const unread = useApi<{ unread: number }>("/api/v1/alerts/unread-count", 30_000);
  const kill = settings.data?.trading.kill_switch;

  async function exitAll() {
    if (!confirm("EXIT ALL: cancel waiting trades, exit every open trade at market and turn the kill switch on?")) return;
    try {
      const r = await apiSend<{ exited: number; cancelled: number; flattened: number }>("/api/v1/trading/exit-all", "POST");
      alert(`Done: exited ${r.exited}, cancelled ${r.cancelled}, flattened ${r.flattened}. Kill switch is ON.`);
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
    settings.reload();
  }

  async function killOff() {
    if (!confirm("Turn the kill switch off and allow new trades again?")) return;
    try {
      await apiSend("/api/v1/trading/kill-switch", "POST", { on: false });
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
    settings.reload();
  }

  return (
    <header className="flex h-14 items-center justify-between gap-4 border-b border-border bg-panel px-4 pl-14 md:px-8">
      <h1 className="truncate text-sm font-medium">{item?.label ?? "MarketOS"}</h1>
      <div className="flex items-center gap-2">
        <Link href="/news" aria-label={`Alerts: ${unread.data?.unread ?? 0} unread`} className="relative rounded-md px-2 py-1 text-sm hover:bg-panel-2">
          🔔
          {Boolean(unread.data?.unread) && (
            <span className="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-bad px-1 text-center text-[10px] font-semibold leading-4 text-white">
              {unread.data!.unread > 99 ? "99+" : unread.data!.unread}
            </span>
          )}
        </Link>
        {kill ? (
          <button type="button" onClick={killOff} title="Kill switch is on: no new trades. Click to turn off.">
            <StatusPill tone="bad">KILL SWITCH ON</StatusPill>
          </button>
        ) : (
          <button type="button" onClick={exitAll} className="whitespace-nowrap rounded-md bg-bad px-2 py-1 text-xs font-semibold text-white hover:opacity-90" title="Exit everything and turn the kill switch on">
            🛑 EXIT ALL
          </button>
        )}
        {mode && (
          <StatusPill tone={mode === "live" ? "bad" : "accent"}>
            {mode === "live" ? "LIVE" : mode === "paper" ? "PAPER" : "TRADING OFF"}
          </StatusPill>
        )}
        <span className="hidden sm:inline-flex">
          <StatusPill tone={backendTone}>
            <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />
            {backendLabel}
          </StatusPill>
        </span>
        <button type="button" onClick={signalUnauthorized} className="ml-1 whitespace-nowrap rounded-md px-2 py-1 text-xs text-muted hover:bg-panel-2 hover:text-text">
          Sign out
        </button>
      </div>
    </header>
  );
}
