"use client";

import Link from "next/link";
import { Card, Notice, PageHeader } from "@/components/ui";
import { StatusPill, toneForState } from "@/components/StatusPill";
import type { Page, Readiness, SystemInfo } from "@/lib/api";
import { adapterLabel, formatDateTime } from "@/lib/format";
import { inr, pnlClass } from "@/lib/format";
import type { AccountSummary, EventRecord } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function Count({ label, path, href }: { label: string; path: string; href: string }) {
  const { data, error } = useApi<Page<unknown>>(`${path}?limit=1`);
  return (
    <Link href={href} className="rounded-lg border border-border bg-panel p-4 hover:border-accent/50">
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-2 font-mono text-2xl tabular-nums">{error ? "—" : (data?.total ?? "…")}</p>
    </Link>
  );
}

function Stat({ label, value, hint, cls = "" }: { label: string; value: string; hint?: string; cls?: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className={`mt-1 font-mono text-xl tabular-nums ${cls}`}>{value}</p>
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const info = useApi<SystemInfo>("/api/v1/system/info");
  const ready = useApi<Readiness>("/health/ready");
  const events = useApi<Page<EventRecord>>("/api/v1/events?limit=8", 10_000);
  const portfolio = useApi<AccountSummary[]>("/api/v1/portfolio/summary", 5_000);

  return (
    <>
      <PageHeader title="Dashboard" description="System status and recent activity." />
      {(info.error || ready.error) && (
        <div className="mb-6">
          <Notice tone="error">
            The API is unreachable. Start the backend (see README) and this page will refresh automatically.
          </Notice>
        </div>
      )}
      {portfolio.data?.map((a) => (
        <section key={a.broker_account_id} className="mb-4 grid grid-cols-2 gap-4 rounded-lg border border-border bg-panel p-4 md:grid-cols-5">
          <Stat label={`${a.label} account`} value={inr(a.capital)} hint={a.mode === "paper" ? "paper capital" : "live"} />
          <Stat label="P&L today" value={inr(a.realized_today)} cls={pnlClass(a.realized_today)} hint="realized" />
          <Stat label="Open P&L" value={inr(a.unrealized)} cls={pnlClass(a.unrealized)} hint={`${a.open_trades} open · ${a.pending_trades} waiting`} />
          <Stat label="Total realized" value={inr(a.realized_total)} cls={pnlClass(a.realized_total)} hint={`${a.closed_trades} closed trades`} />
          <Stat label="Win rate" value={a.win_rate ? `${a.win_rate}%` : "—"} hint="closed trades" />
        </section>
      ))}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Count label="Signals" path="/api/v1/signals" href="/signals" />
        <Count label="Trades" path="/api/v1/trades" href="/trades" />
        <Count label="Orders" path="/api/v1/orders" href="/orders" />
        <Count label="Sources" path="/api/v1/signal-sources" href="/sources" />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card title="System">
          {info.data ? (
            <dl className="grid grid-cols-2 gap-y-2 text-sm">
              <dt className="text-muted">Version</dt>
              <dd className="font-mono">{info.data.version}</dd>
              <dt className="text-muted">Environment</dt>
              <dd>{info.data.environment}</dd>
              <dt className="text-muted">Trading mode</dt>
              <dd>
                <StatusPill tone="accent">{info.data.trading_mode}</StatusPill>
              </dd>
              <dt className="text-muted">Database</dt>
              <dd>
                <StatusPill tone={toneForState(ready.data?.status ?? "")}>{ready.data?.status ?? "…"}</StatusPill>
              </dd>
            </dl>
          ) : (
            <p className="text-sm text-muted">Loading…</p>
          )}
        </Card>
        <Card title="Integrations">
          <ul className="space-y-2 text-sm">
            {info.data &&
              Object.entries(info.data.adapters).map(([key, a]) => (
                <li key={key} className="flex items-center justify-between">
                  <span>{adapterLabel(key)}</span>
                  <StatusPill tone={toneForState(a.state)}>{a.state.replace("_", " ")}</StatusPill>
                </li>
              ))}
          </ul>
        </Card>
        <Card title="Recent events">
          <ul className="space-y-2 text-sm">
            {events.data?.items.length === 0 && <li className="text-muted">No events yet.</li>}
            {events.data?.items.map((e) => (
              <li key={e.id} className="flex items-center justify-between gap-2">
                <span className="truncate font-mono text-xs">{e.event_type}</span>
                <span className="shrink-0 text-xs text-muted">{formatDateTime(e.occurred_at)}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}
