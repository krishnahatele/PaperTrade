"use client";

import Link from "next/link";
import { useState } from "react";
import { DataTable } from "@/components/DataTable";
import { Button } from "@/components/forms";
import { StatusPill, toneForState } from "@/components/StatusPill";
import { PageHeader } from "@/components/ui";
import { apiSend } from "@/lib/api";
import { formatDateTime, formatNumber, inr, pnlClass } from "@/lib/format";
import { Ladder } from "@/components/trade/Ladder";
import type { TradePlan } from "@/lib/types";

const TABS = [
  { key: "", label: "All" },
  { key: "open", label: "Open" },
  { key: "pending", label: "Waiting for entry" },
  { key: "closed", label: "Closed" },
  { key: "cancelled", label: "Cancelled" },
];

export default function TradesPage() {
  const [tab, setTab] = useState("");
  const [version, setVersion] = useState(0);

  async function close(t: TradePlan) {
    const what = t.status === "pending" ? "Cancel this pending entry?" : `Exit ${t.tradingsymbol} at market now?`;
    if (!confirm(what)) return;
    try {
      await apiSend(`/api/v1/trades/${t.id}/close`, "POST");
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
    setVersion((v) => v + 1);
  }

  return (
    <>
      <PageHeader title="Trades" description="Each signal becomes a managed trade: an entry, a stop-loss for what you hold, and one exit per target (TP1, TP2…). The stop can trail. Open a trade to change its stop-loss or targets, or exit some lots. Paper trades use simulated fills." />
      <div className="mb-3 flex flex-wrap gap-1" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)} className={`rounded-md px-3 py-1 text-sm ${tab === t.key ? "bg-panel-2 font-medium" : "text-muted hover:text-text"}`}>
            {t.label}
          </button>
        ))}
      </div>
      <DataTable<TradePlan>
        key={`${tab}:${version}`}
        path="/api/v1/trades"
        query={tab ? `&status=${tab}` : ""}
        refreshMs={3000}
        emptyText="No trades yet. Validated signals are executed automatically when auto-execute is on."
        columns={[
          { key: "at", header: "Created", render: (t) => formatDateTime(t.created_at) },
          {
            key: "sym",
            header: "Instrument",
            render: (t) => (
              <span>
                <StatusPill tone={t.side === "BUY" ? "good" : "bad"}>{t.side}</StatusPill>{" "}
                <Link href={`/trades/${t.id}`} className="font-medium text-accent hover:underline">{t.tradingsymbol}</Link>
                {t.signal_id && (
                  <Link href={`/signals/${t.signal_id}`} className="ml-1 text-xs text-accent">signal</Link>
                )}
              </span>
            ),
          },
          { key: "qty", header: "Qty", align: "right", render: (t) => (t.status === "open" && t.open_quantity !== t.quantity ? `${t.open_quantity}/${t.quantity}` : t.quantity) },
          { key: "entry", header: "Entry", align: "right", render: (t) => formatNumber(t.entry_price ?? t.planned_entry) },
          { key: "sl", header: "Stop", align: "right", render: (t) => formatNumber(t.stop_loss) },
          { key: "tgt", header: "Targets", align: "right", render: (t) => <Ladder t={t} /> },
          { key: "ltp", header: "LTP / exit", align: "right", render: (t) => formatNumber(t.exit_price ?? t.ltp) },
          {
            key: "pnl",
            header: "P&L",
            align: "right",
            render: (t) => {
              const v = t.realized_pnl ?? t.unrealized_pnl;
              return <span className={pnlClass(v)}>{inr(v)}</span>;
            },
          },
          {
            key: "status",
            header: "Status",
            render: (t) => (
              <span className="flex gap-1">
                <StatusPill tone={toneForState(t.status === "open" ? "ok" : t.status)}>{t.status === "pending" ? "waiting" : t.status}</StatusPill>
                {t.exit_reason && <StatusPill tone={toneForState(t.exit_reason)}>{t.exit_reason}</StatusPill>}
              </span>
            ),
          },
          {
            key: "act",
            header: "",
            render: (t) =>
              t.status === "open" || t.status === "pending" ? (
                <span className="flex gap-1">
                  <Link href={`/trades/${t.id}`} className="rounded-md border border-border px-3 py-1.5 text-sm">Manage</Link>
                  <Button variant="secondary" onClick={() => close(t)}>
                    {t.status === "open" ? "Exit" : "Cancel"}
                  </Button>
                </span>
              ) : null,
          },
        ]}
      />
    </>
  );
}
