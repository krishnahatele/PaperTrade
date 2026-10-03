"use client";

import { useState } from "react";
import { DataTable } from "@/components/DataTable";
import { Button, useAction } from "@/components/forms";
import { StatusPill } from "@/components/StatusPill";
import { apiSend } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { AlertItem } from "@/lib/types";

const KINDS = [
  { key: "", label: "All" },
  { key: "news", label: "News" },
  { key: "market", label: "Market moves" },
];

export function AlertsTab() {
  const [kind, setKind] = useState("");
  const [version, setVersion] = useState(0);
  const act = useAction();

  async function markAll() {
    await act.run(() => apiSend("/api/v1/alerts/read-all", "POST"));
    setVersion((v) => v + 1);
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="text-sm">
          <span className="text-muted">Show</span>
          <select value={kind} onChange={(e) => setKind(e.target.value)} className="ml-2 rounded-md border border-border bg-bg px-2 py-1.5">
            {KINDS.map((k) => (
              <option key={k.key} value={k.key}>{k.label}</option>
            ))}
          </select>
        </label>
        <Button variant="secondary" onClick={markAll}>Mark all read</Button>
      </div>
      {act.view}
      <DataTable<AlertItem>
        key={`${kind}:${version}`}
        path="/api/v1/alerts"
        query={kind ? `&kind=${kind}` : ""}
        refreshMs={30_000}
        emptyText="No alerts yet. Alerts appear when a headline matches your keywords or a watched instrument moves sharply."
        columns={[
          {
            key: "kind",
            header: "Type",
            render: (a) => <StatusPill tone={a.kind === "news" ? "accent" : a.kind === "market" ? "warn" : "neutral"}>{a.kind}</StatusPill>,
          },
          {
            key: "title",
            header: "Alert",
            render: (a) => (
              <div className={`max-w-xl whitespace-normal ${a.read ? "" : "font-semibold"}`}>
                {!a.read && <span className="sr-only">Unread: </span>}
                {a.url ? (
                  <a href={a.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">{a.title}</a>
                ) : (
                  <span>{a.title}</span>
                )}
                {a.body && <p className="mt-0.5 text-xs font-normal text-muted">{a.body}</p>}
              </div>
            ),
          },
          { key: "at", header: "Time", render: (a) => <span className="text-xs text-muted">{formatDateTime(a.created_at)}</span> },
        ]}
      />
    </div>
  );
}
