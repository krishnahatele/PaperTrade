"use client";

import { DataTable } from "@/components/DataTable";
import { PageHeader } from "@/components/ui";
import { formatDateTime, shortId } from "@/lib/format";
import type { EventRecord } from "@/lib/types";

export default function EventsPage() {
  return (
    <>
      <PageHeader title="Event log" description="Append-only audit trail of everything that happens in MarketOS." />
      <DataTable<EventRecord>
        path="/api/v1/events"
        emptyText="No events recorded."
        columns={[
          { key: "at", header: "Occurred", render: (e) => formatDateTime(e.occurred_at) },
          { key: "type", header: "Type", render: (e) => <span className="font-mono text-xs">{e.event_type}</span> },
          { key: "agg", header: "Aggregate", render: (e) => (e.aggregate_type ? `${e.aggregate_type}:${shortId(e.aggregate_id)}` : "—") },
          { key: "corr", header: "Correlation", render: (e) => <span className="font-mono text-xs">{shortId(e.correlation_id)}</span> },
          {
            key: "payload",
            header: "Payload",
            render: (e) => <code className="block max-w-md truncate text-xs text-muted">{JSON.stringify(e.payload)}</code>,
          },
        ]}
      />
    </>
  );
}
