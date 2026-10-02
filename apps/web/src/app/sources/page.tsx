"use client";

import { DataTable } from "@/components/DataTable";
import { StatusPill } from "@/components/StatusPill";
import { PageHeader } from "@/components/ui";
import { formatDateTime } from "@/lib/format";
import type { SignalSource } from "@/lib/types";

export default function SourcesPage() {
  return (
    <>
      <PageHeader title="Sources" description="Telegram channels and other places signals come from." />
      <DataTable<SignalSource>
        path="/api/v1/signal-sources"
        emptyText="No sources configured."
        columns={[
          { key: "name", header: "Name", render: (s) => <span className="font-medium">{s.name}</span> },
          { key: "kind", header: "Kind", render: (s) => s.kind },
          { key: "ext", header: "External ID", render: (s) => <span className="font-mono text-xs">{s.external_id ?? "—"}</span> },
          { key: "enabled", header: "Enabled", render: (s) => <StatusPill tone={s.is_enabled ? "good" : "neutral"}>{s.is_enabled ? "on" : "off"}</StatusPill> },
          { key: "created", header: "Added", render: (s) => formatDateTime(s.created_at) },
        ]}
      />
    </>
  );
}
