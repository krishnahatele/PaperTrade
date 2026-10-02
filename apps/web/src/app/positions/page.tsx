"use client";

import { DataTable } from "@/components/DataTable";
import { PageHeader } from "@/components/ui";
import { formatDateTime, formatNumber, shortId } from "@/lib/format";
import type { Position } from "@/lib/types";

export default function PositionsPage() {
  return (
    <>
      <PageHeader title="Positions" description="Net holdings per account, instrument and product." />
      <DataTable<Position>
        path="/api/v1/positions"
        emptyText="No open positions."
        columns={[
          { key: "instrument", header: "Instrument", render: (p) => <span className="font-mono text-xs">{shortId(p.instrument_id)}</span> },
          { key: "product", header: "Product", render: (p) => p.product },
          { key: "qty", header: "Qty", align: "right", render: (p) => p.quantity },
          { key: "avg", header: "Avg price", align: "right", render: (p) => formatNumber(p.average_price) },
          {
            key: "pnl",
            header: "Realized P&L",
            align: "right",
            render: (p) => <span className={Number(p.realized_pnl) < 0 ? "text-bad" : Number(p.realized_pnl) > 0 ? "text-good" : ""}>{formatNumber(p.realized_pnl)}</span>,
          },
          { key: "updated", header: "Updated", render: (p) => formatDateTime(p.updated_at) },
        ]}
      />
    </>
  );
}
