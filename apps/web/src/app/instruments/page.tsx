"use client";

import { useState } from "react";
import { DataTable } from "@/components/DataTable";
import { PageHeader } from "@/components/ui";
import { formatNumber } from "@/lib/format";
import type { Instrument } from "@/lib/types";

export default function InstrumentsPage() {
  const [q, setQ] = useState("");
  return (
    <>
      <PageHeader
        title="Instruments"
        description="Tradable contracts known to MarketOS."
        actions={
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value.toUpperCase())}
            placeholder="Search symbol…"
            aria-label="Search symbol"
            className="w-56 rounded-md border border-border bg-panel px-3 py-1.5 text-sm outline-none focus:border-accent"
          />
        }
      />
      <DataTable<Instrument>
        key={q}
        path="/api/v1/instruments"
        query={q ? `&q=${encodeURIComponent(q)}` : ""}
        emptyText="No instruments."
        columns={[
          { key: "ex", header: "Exchange", render: (i) => i.exchange },
          { key: "sym", header: "Symbol", render: (i) => <span className="font-medium">{i.tradingsymbol}</span> },
          { key: "name", header: "Name", render: (i) => i.name ?? "—" },
          { key: "type", header: "Type", render: (i) => i.instrument_type },
          { key: "expiry", header: "Expiry", render: (i) => i.expiry ?? "—" },
          { key: "strike", header: "Strike", align: "right", render: (i) => formatNumber(i.strike) },
          { key: "lot", header: "Lot", align: "right", render: (i) => i.lot_size },
          { key: "tick", header: "Tick", align: "right", render: (i) => formatNumber(i.tick_size) },
        ]}
      />
    </>
  );
}
