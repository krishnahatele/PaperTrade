"use client";

import { Card, PageHeader } from "@/components/ui";
import { StatusPill } from "@/components/StatusPill";
import type { SystemInfo } from "@/lib/api";
import { useApi } from "@/lib/useApi";

export default function SettingsPage() {
  const info = useApi<SystemInfo>("/api/v1/system/info");
  return (
    <>
      <PageHeader title="Settings" description="Runtime configuration. Values come from backend environment variables." />
      <Card title="Trading safety">
        <dl className="grid grid-cols-[12rem_1fr] gap-y-2 text-sm">
          <dt className="text-muted">Trading mode</dt>
          <dd>
            <StatusPill tone="accent">{info.data?.trading_mode ?? "…"}</StatusPill>
          </dd>
          <dt className="text-muted">Live trading</dt>
          <dd>
            <StatusPill tone={info.data?.live_trading_enabled ? "bad" : "good"}>
              {info.data?.live_trading_enabled ? "enabled" : "disabled"}
            </StatusPill>
          </dd>
        </dl>
      </Card>
    </>
  );
}
