"use client";

import { useState } from "react";
import { DataTable } from "@/components/DataTable";
import { Button } from "@/components/forms";
import { StatusPill, toneForState } from "@/components/StatusPill";
import { PageHeader } from "@/components/ui";
import { apiSend } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";
import type { Order } from "@/lib/types";

const CANCELLABLE = new Set(["open", "submitted", "partially_filled"]);

export default function OrdersPage() {
  const [version, setVersion] = useState(0);
  return (
    <>
      <PageHeader title="Orders" description="Every order MarketOS has placed. Stop-loss and target orders belong to a trade; exit the trade to remove them." />
      <DataTable<Order>
        key={version}
        path="/api/v1/orders"
        refreshMs={5000}
        emptyText="No orders yet."
        columns={[
          { key: "created", header: "Created", render: (o) => formatDateTime(o.created_at) },
          { key: "mode", header: "Mode", render: (o) => <StatusPill tone={o.mode === "live" ? "bad" : "accent"}>{o.mode}</StatusPill> },
          { key: "role", header: "Role", render: (o) => o.role },
          { key: "side", header: "Side", render: (o) => o.side },
          { key: "type", header: "Type", render: (o) => `${o.order_type} · ${o.product}` },
          { key: "qty", header: "Qty", align: "right", render: (o) => `${o.filled_quantity}/${o.quantity}` },
          { key: "price", header: "Price / trigger", align: "right", render: (o) => (o.trigger_price ? `@${formatNumber(o.trigger_price)}` : formatNumber(o.price)) },
          { key: "avg", header: "Avg fill", align: "right", render: (o) => formatNumber(o.average_price) },
          { key: "status", header: "Status", render: (o) => <span title={o.status_message ?? undefined}><StatusPill tone={toneForState(o.status)}>{o.status}</StatusPill></span> },
          {
            key: "act",
            header: "",
            render: (o) =>
              CANCELLABLE.has(o.status) && (o.role === "manual" || o.role === "entry") ? (
                <Button
                  variant="secondary"
                  onClick={async () => {
                    try {
                      await apiSend(`/api/v1/orders/${o.id}/cancel`, "POST");
                    } catch (e) {
                      alert(e instanceof Error ? e.message : String(e));
                    }
                    setVersion((v) => v + 1);
                  }}
                >
                  Cancel
                </Button>
              ) : null,
          },
        ]}
      />
    </>
  );
}
