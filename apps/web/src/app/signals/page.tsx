"use client";

import { DataTable } from "@/components/DataTable";
import { StatusPill, toneForState } from "@/components/StatusPill";
import { PageHeader } from "@/components/ui";
import { formatDateTime, formatNumber } from "@/lib/format";
import type { Signal } from "@/lib/types";

export default function SignalsPage() {
  return (
    <>
      <PageHeader title="Signals" description="Structured trade ideas from your sources." />
      <DataTable<Signal>
        path="/api/v1/signals"
        emptyText="No signals yet."
        columns={[
          { key: "created", header: "Received", render: (s) => formatDateTime(s.created_at) },
          { key: "symbol", header: "Symbol", render: (s) => <span className="font-medium">{s.symbol_text}</span> },
          { key: "side", header: "Side", render: (s) => <StatusPill tone={s.side === "BUY" ? "good" : "bad"}>{s.side}</StatusPill> },
          { key: "entry", header: "Entry", align: "right", render: (s) => (s.entry_low === s.entry_high || !s.entry_high ? formatNumber(s.entry_low) : `${formatNumber(s.entry_low)} – ${formatNumber(s.entry_high)}`) },
          { key: "sl", header: "Stop", align: "right", render: (s) => formatNumber(s.stop_loss) },
          { key: "targets", header: "Targets", render: (s) => (s.targets.length ? s.targets.map((t) => formatNumber(t)).join(", ") : "—") },
          { key: "parser", header: "Parser", render: (s) => s.parser },
          { key: "status", header: "Status", render: (s) => <StatusPill tone={toneForState(s.status)}>{s.status}</StatusPill> },
        ]}
      />
    </>
  );
}
