"use client";

import { useState } from "react";
import { DataTable } from "@/components/DataTable";
import { Button, useAction } from "@/components/forms";
import { apiSend } from "@/lib/api";
import { PageHeader } from "@/components/ui";
import { formatNumber } from "@/lib/format";
import type { Instrument } from "@/lib/types";

export default function InstrumentsPage() {
  const [q, setQ] = useState("");
  const [version, setVersion] = useState(0);
  const sync = useAction();
  return (
    <>
      <PageHeader
        title="Instruments"
        description="Tradable contracts known to MarketOS."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {sync.view}
            <Button
              variant="secondary"
              onClick={() =>
                sync.run(async () => {
                  const r = await apiSend<Record<string, number>>("/api/v1/instruments/sync", "POST", { exchanges: ["NSE", "NFO"] });
                  sync.setMessage({ tone: "ok", text: `Synced ${Object.entries(r).map(([k, v]) => `${k} ${v}`).join(", ")}` });
                  setVersion((v) => v + 1);
                })
              }
            >
              Sync from Kite
            </Button>
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value.toUpperCase())}
            placeholder="Search symbol…"
            aria-label="Search symbol"
            className="w-56 rounded-md border border-border bg-panel px-3 py-1.5 text-sm outline-none focus:border-accent"
          />
          </div>
        }
      />
      <DataTable<Instrument>
        key={`${q}:${version}`}
        path="/api/v1/instruments"
        query={q ? `&q=${encodeURIComponent(q)}` : ""}
        emptyText="No instruments yet. Click “Sync from Kite” to download the NSE and F&O list (takes a minute)."
        columns={[
          { key: "ex", header: "Exchange", render: (i) => i.exchange },
          { key: "sym", header: "Symbol", render: (i) => <span className="font-medium">{i.tradingsymbol}</span> },
          { key: "name", header: "Name", render: (i) => i.name ?? "—" },
          { key: "type", header: "Type", render: (i) => i.instrument_type },
          { key: "expiry", header: "Expiry", render: (i) => i.expiry ?? "—" },
          { key: "strike", header: "Strike", align: "right", render: (i) => formatNumber(i.strike) },
          { key: "lot", header: "Lot", align: "right", render: (i) => i.lot_size },
          { key: "tick", header: "Tick", align: "right", render: (i) => formatNumber(i.tick_size) },
          {
            key: "px",
            header: "",
            render: (i) => (
              <button
                type="button"
                className="text-xs text-accent underline"
                title="Without a Kite session, set a price by hand to practise paper trading"
                onClick={async () => {
                  const v = prompt(`Set a practice price for ${i.tradingsymbol}`);
                  if (!v) return;
                  try {
                    await apiSend("/api/v1/market/manual-price", "POST", { instrument_id: i.id, price: v });
                  } catch (e) {
                    alert(e instanceof Error ? e.message : String(e));
                  }
                }}
              >
                set price
              </button>
            ),
          },
        ]}
      />
    </>
  );
}
