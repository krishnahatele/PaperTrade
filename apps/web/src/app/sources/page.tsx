"use client";

import Link from "next/link";
import { useState } from "react";
import { Button, TextField, Toggle, useAction } from "@/components/forms";
import { StatusPill } from "@/components/StatusPill";
import { Card, Notice, PageHeader } from "@/components/ui";
import { apiSend, type Page } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { SignalSource, TelegramChannel, TelegramStatus } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function SourcesPage() {
  const sources = useApi<Page<SignalSource>>("/api/v1/signal-sources?limit=200");
  const tg = useApi<TelegramStatus>("/api/v1/telegram/status");
  const [showChannels, setShowChannels] = useState(false);
  const [manualName, setManualName] = useState("");
  const act = useAction();

  return (
    <>
      <PageHeader
        title="Sources"
        description="Telegram channels and other places signals come from."
        actions={
          <Button variant="secondary" disabled={!tg.data?.authorized} onClick={() => setShowChannels((v) => !v)}>
            {showChannels ? "Hide Telegram channels" : "Add Telegram channel"}
          </Button>
        }
      />
      {tg.data && !tg.data.authorized && (
        <div className="mb-4">
          <Notice>
            Telegram is not connected. Add your credentials and log in on the <Link href="/settings" className="text-accent underline">Settings</Link> page to add channels.
          </Notice>
        </div>
      )}
      {showChannels && <ChannelPicker onAdded={sources.reload} />}

      <div className="space-y-2">
        {sources.error && <Notice tone="error">{sources.error}</Notice>}
        {sources.data?.items.length === 0 && <p className="text-sm text-muted">No sources yet.</p>}
        {sources.data?.items.map((s) => (
          <SourceRow key={s.id} source={s} onChange={sources.reload} />
        ))}
      </div>

      <Card title="Manual source" className="mt-6">
        <p className="mb-3 text-sm text-muted">For signals you enter by hand or test with.</p>
        <div className="flex flex-wrap items-end gap-2">
          <div className="w-64">
            <TextField label="Name" value={manualName} onChange={setManualName} placeholder="My desk" />
          </div>
          <Button
            onClick={async () => {
              if (!manualName.trim()) return;
              if (await act.run(() => apiSend("/api/v1/signal-sources", "POST", { kind: "manual", name: manualName.trim(), is_enabled: true }), "Added.")) {
                setManualName("");
                sources.reload();
              }
            }}
          >
            Add
          </Button>
          {act.view}
        </div>
      </Card>
    </>
  );
}

function SourceRow({ source, onChange }: { source: SignalSource; onChange: () => void }) {
  const act = useAction();
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-panel px-4 py-3">
      <div className="min-w-0">
        <Link href={`/sources/${source.id}`} className="font-medium hover:text-accent">
          {source.name}
        </Link>
        <p className="text-xs text-muted">
          <StatusPill tone="neutral">{source.kind}</StatusPill>{" "}
          {source.external_id && <span className="font-mono">{source.external_id}</span>} · added {formatDateTime(source.created_at)}
        </p>
      </div>
      <div className="flex items-center gap-2">
        {act.view}
        {source.kind === "telegram" && (
          <Button
            variant="secondary"
            onClick={() =>
              act.run(async () => {
                const r = await apiSend<{ stored: number }>(`/api/v1/telegram/sources/${source.id}/backfill?limit=50`, "POST");
                act.setMessage({ tone: "ok", text: `Fetched ${r.stored} new message(s).` });
              })
            }
          >
            Fetch recent
          </Button>
        )}
        <div className="w-28">
          <Toggle label="Enabled" checked={source.is_enabled} onChange={(v) => act.run(() => apiSend(`/api/v1/signal-sources/${source.id}`, "PATCH", { is_enabled: v })).then(onChange)} />
        </div>
        <Button
          variant="secondary"
          onClick={async () => {
            if (!confirm(`Delete source “${source.name}”?`)) return;
            if (await act.run(() => apiSend(`/api/v1/signal-sources/${source.id}`, "DELETE"))) onChange();
          }}
        >
          Delete
        </Button>
      </div>
    </div>
  );
}

function ChannelPicker({ onAdded }: { onAdded: () => void }) {
  const channels = useApi<TelegramChannel[]>("/api/v1/telegram/channels");
  const [filter, setFilter] = useState("");
  const act = useAction();
  const list = (channels.data ?? []).filter((c) => c.title.toLowerCase().includes(filter.toLowerCase()));

  return (
    <Card title="Your Telegram channels and groups" className="mb-6">
      <div className="mb-3 flex items-center gap-2">
        <div className="w-72">
          <TextField label="Filter" value={filter} onChange={setFilter} placeholder="Search…" />
        </div>
        {act.view}
      </div>
      {channels.loading && <p className="text-sm text-muted">Loading channels…</p>}
      {channels.error && <Notice tone="error">{channels.error}</Notice>}
      <ul className="max-h-80 divide-y divide-border overflow-y-auto">
        {list.map((c) => (
          <li key={c.id} className="flex items-center justify-between gap-2 py-2 text-sm">
            <span className="min-w-0 truncate">
              {c.title} <span className="text-xs text-muted">{c.username ? `@${c.username}` : c.kind}</span>
            </span>
            {c.source_id ? (
              <StatusPill tone={c.source_enabled ? "good" : "neutral"}>{c.source_enabled ? "added" : "added (off)"}</StatusPill>
            ) : (
              <Button
                variant="secondary"
                onClick={async () => {
                  if (await act.run(() => apiSend("/api/v1/telegram/channels", "POST", { channel_id: c.id, name: c.title.slice(0, 128) }), `Added ${c.title}.`)) {
                    channels.reload();
                    onAdded();
                  }
                }}
              >
                Add
              </Button>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
