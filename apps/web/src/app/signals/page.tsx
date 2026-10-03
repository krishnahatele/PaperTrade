"use client";

import Link from "next/link";
import { useState } from "react";
import { DataTable } from "@/components/DataTable";
import { ParserPlayground } from "@/components/ParserPlayground";
import { StatusPill, toneForState } from "@/components/StatusPill";
import { PageHeader } from "@/components/ui";
import { formatDateTime, formatNumber } from "@/lib/format";
import type { Signal } from "@/lib/types";

const TABS = [
  { key: "", label: "All" },
  { key: "new", label: "Needs review" },
  { key: "validated", label: "Validated" },
  { key: "expired", label: "Expired" },
  { key: "rejected", label: "Rejected" },
];

export default function SignalsPage() {
  const [tab, setTab] = useState("");
  return (
    <>
      <PageHeader title="Signals" description="Trade ideas parsed from your sources. Validated signals are complete and resolved to a real instrument." />
      <div className="mb-3 flex flex-wrap gap-1" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-md px-3 py-1 text-sm ${tab === t.key ? "bg-panel-2 font-medium" : "text-muted hover:text-text"}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <DataTable<Signal>
        key={tab}
        path="/api/v1/signals"
        query={tab ? `&status=${tab}` : ""}
        emptyText="No signals yet. They appear here automatically as messages arrive."
        columns={[
          { key: "created", header: "Received", render: (s) => formatDateTime(s.created_at) },
          {
            key: "symbol",
            header: "Symbol",
            render: (s) => (
              <Link href={`/signals/${s.id}`} className="font-medium hover:text-accent">
                {s.symbol_text}
              </Link>
            ),
          },
          { key: "side", header: "Side", render: (s) => <StatusPill tone={s.side === "BUY" ? "good" : "bad"}>{s.side}</StatusPill> },
          { key: "entry", header: "Entry", align: "right", render: (s) => (s.entry_low === s.entry_high || !s.entry_high ? formatNumber(s.entry_low) : `${formatNumber(s.entry_low)} – ${formatNumber(s.entry_high)}`) },
          { key: "sl", header: "Stop", align: "right", render: (s) => formatNumber(s.stop_loss) },
          { key: "targets", header: "Targets", render: (s) => (s.targets.length ? s.targets.map((t) => formatNumber(t)).join(", ") : "—") },
          { key: "conf", header: "Conf.", align: "right", render: (s) => (s.confidence ? `${Math.round(Number(s.confidence) * 100)}%` : "—") },
          { key: "parser", header: "Parser", render: (s) => (s.parser === "llm" ? "AI" : s.parser) },
          { key: "status", header: "Status", render: (s) => <StatusPill tone={toneForState(s.status)}>{s.status === "new" ? "needs review" : s.status}</StatusPill> },
        ]}
      />
      <div className="mt-6">
        <ParserPlayground />
      </div>
    </>
  );
}
