"use client";

import { DataTable } from "@/components/DataTable";
import { StatusPill, toneForState } from "@/components/StatusPill";
import { PageHeader } from "@/components/ui";
import { formatDateTime, formatNumber } from "@/lib/format";
import type { Order } from "@/lib/types";

export default function OrdersPage() {
  return (
    <>
      <PageHeader title="Orders" description="Every order MarketOS has created, paper or live." />
      <DataTable<Order>
        path="/api/v1/orders"
        emptyText="No orders yet."
        columns={[
          { key: "created", header: "Created", render: (o) => formatDateTime(o.created_at) },
          { key: "mode", header: "Mode", render: (o) => <StatusPill tone={o.mode === "live" ? "bad" : "accent"}>{o.mode}</StatusPill> },
          { key: "side", header: "Side", render: (o) => o.side },
          { key: "type", header: "Type", render: (o) => `${o.order_type} · ${o.product}` },
          { key: "qty", header: "Qty", align: "right", render: (o) => `${o.filled_quantity}/${o.quantity}` },
          { key: "price", header: "Price", align: "right", render: (o) => formatNumber(o.price) },
          { key: "avg", header: "Avg fill", align: "right", render: (o) => formatNumber(o.average_price) },
          { key: "status", header: "Status", render: (o) => <StatusPill tone={toneForState(o.status)}>{o.status}</StatusPill> },
        ]}
      />
    </>
  );
}
