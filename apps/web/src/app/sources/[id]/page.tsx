"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { DataTable } from "@/components/DataTable";
import { StatusPill, toneForState } from "@/components/StatusPill";
import { Notice, PageHeader } from "@/components/ui";
import { formatDateTime } from "@/lib/format";
import type { RawMessage, SignalSource } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function SourceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const source = useApi<SignalSource>(`/api/v1/signal-sources/${id}`);

  return (
    <>
      <PageHeader
        title={source.data?.name ?? "Source"}
        description={source.data ? `${source.data.kind}${source.data.external_id ? ` · ${source.data.external_id}` : ""}` : undefined}
        actions={
          <Link href="/sources" className="text-sm text-accent underline">
            All sources
          </Link>
        }
      />
      {source.error && <Notice tone="error">{source.error}</Notice>}
      <DataTable<RawMessage>
        path={`/api/v1/signal-sources/${id}/messages`}
        emptyText="No messages received yet."
        columns={[
          { key: "at", header: "Received", render: (m) => formatDateTime(m.received_at) },
          {
            key: "text",
            header: "Message",
            render: (m) => <p className="max-w-2xl whitespace-pre-wrap break-words text-sm">{m.content}</p>,
          },
          { key: "status", header: "Status", render: (m) => <StatusPill tone={toneForState(m.status)}>{m.status}</StatusPill> },
        ]}
      />
    </>
  );
}
