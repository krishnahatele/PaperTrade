"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Button, TextField, useAction } from "@/components/forms";
import { StatusPill, toneForState } from "@/components/StatusPill";
import { Card, Notice, PageHeader } from "@/components/ui";
import { apiSend, type Page } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";
import type { Instrument, RawMessage, Signal } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function SignalDetailPage() {
  const { id } = useParams<{ id: string }>();
  const sig = useApi<Signal>(`/api/v1/signals/${id}`);
  const s = sig.data;

  return (
    <>
      <PageHeader
        title={s ? `${s.side} ${s.symbol_text}` : "Signal"}
        description={s ? `Received ${formatDateTime(s.created_at)} · parsed by ${s.parser === "llm" ? "AI" : s.parser}` : undefined}
        actions={<Link href="/signals" className="text-sm text-accent underline">All signals</Link>}
      />
      {sig.error && <Notice tone="error">{sig.error}</Notice>}
      {s && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Details">
            <dl className="grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
              <dt className="text-muted">Status</dt>
              <dd><StatusPill tone={toneForState(s.status)}>{s.status === "new" ? "needs review" : s.status}</StatusPill></dd>
              <dt className="text-muted">Instrument</dt>
              <dd><InstrumentName id={s.instrument_id} /></dd>
              <dt className="text-muted">Entry</dt>
              <dd className="font-mono">{s.entry_low === s.entry_high || !s.entry_high ? formatNumber(s.entry_low) : `${formatNumber(s.entry_low)} – ${formatNumber(s.entry_high)}`}</dd>
              <dt className="text-muted">Stop loss</dt>
              <dd className="font-mono">{formatNumber(s.stop_loss)}</dd>
              <dt className="text-muted">Targets</dt>
              <dd className="font-mono">{s.targets.map((t) => formatNumber(t)).join(", ") || "—"}</dd>
              <dt className="text-muted">Confidence</dt>
              <dd>{s.confidence ? `${Math.round(Number(s.confidence) * 100)}%` : "—"}</dd>
            </dl>
            {(s.details.warnings?.length ?? 0) > 0 && (
              <ul className="mt-3 list-inside list-disc text-xs text-warn">
                {s.details.warnings!.map((w) => <li key={w}>{w}</li>)}
              </ul>
            )}
            {s.details.llm_error && <p className="mt-2 text-xs text-bad">AI parser: {s.details.llm_error}</p>}
          </Card>
          <Card title="Original message">{s.raw_message_id ? <RawMessageText signal={s} /> : <p className="text-sm text-muted">Entered manually.</p>}</Card>
          <ReviewCard signal={s} onChange={sig.reload} />
        </div>
      )}
    </>
  );
}

function InstrumentName({ id }: { id: string | null }) {
  const inst = useApi<Instrument>(id ? `/api/v1/instruments/${id}` : null);
  if (!id) return <StatusPill tone="warn">not resolved</StatusPill>;
  return <span className="font-mono">{inst.data ? `${inst.data.exchange}:${inst.data.tradingsymbol}` : "…"}</span>;
}

function RawMessageText({ signal }: { signal: Signal }) {
  const msgs = useApi<Page<RawMessage>>(`/api/v1/signal-sources/${signal.source_id}/messages?limit=200`);
  const m = msgs.data?.items.find((x) => x.id === signal.raw_message_id);
  return <p className="whitespace-pre-wrap break-words text-sm">{m?.content ?? "…"}</p>;
}

function ReviewCard({ signal, onChange }: { signal: Signal; onChange: () => void }) {
  const plain = (v: string | null) => (v ? String(Number(v)) : "");
  const [entry, setEntry] = useState(plain(signal.entry_low));
  const [sl, setSl] = useState(plain(signal.stop_loss));
  const [targets, setTargets] = useState(signal.targets.map(plain).join(", "));
  const [q, setQ] = useState("");
  const results = useApi<Page<Instrument>>(q.length >= 2 ? `/api/v1/instruments?limit=8&q=${encodeURIComponent(q)}` : null);
  const act = useAction();
  const patch = (body: Record<string, unknown>, ok: string) => act.run(() => apiSend(`/api/v1/signals/${signal.id}`, "PATCH", body), ok).then(onChange);

  return (
    <Card title="Review" className="lg:col-span-2">
      <div className="flex flex-wrap items-center gap-2">
        {signal.status !== "validated" && signal.status !== "executed" && <Button onClick={() => patch({ status: "validated" }, "Approved.")}>Approve</Button>}
        {signal.status === "validated" && (
          <Button onClick={() => act.run(() => apiSend(`/api/v1/signals/${signal.id}/execute`, "POST", {}), "Trade placed on the paper account — see Trades.").then(onChange)}>
            Execute (paper)
          </Button>
        )}
        {signal.status !== "rejected" && <Button variant="secondary" onClick={() => patch({ status: "rejected" }, "Rejected.")}>Reject</Button>}
        {act.view}
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <TextField label="Entry" value={entry} onChange={setEntry} inputMode="decimal" />
        <TextField label="Stop loss" value={sl} onChange={setSl} inputMode="decimal" />
        <TextField label="Targets (comma separated)" value={targets} onChange={setTargets} />
      </div>
      <div className="mt-2">
        <Button
          variant="secondary"
          onClick={() =>
            patch(
              {
                entry_low: entry || undefined,
                entry_high: entry || undefined,
                stop_loss: sl || undefined,
                targets: targets.split(/[,\s/]+/).filter(Boolean),
              },
              "Saved.",
            )
          }
        >
          Save prices
        </Button>
      </div>
      <div className="mt-4 max-w-md">
        <TextField label="Change instrument" value={q} onChange={(v) => setQ(v.toUpperCase())} placeholder="Search symbol, e.g. NIFTY25" />
        <ul className="mt-1 divide-y divide-border text-sm">
          {results.data?.items.map((i) => (
            <li key={i.id} className="flex items-center justify-between py-1.5">
              <span className="font-mono text-xs">{i.exchange}:{i.tradingsymbol} {i.expiry ? `· ${i.expiry}` : ""}</span>
              <Button variant="secondary" onClick={() => patch({ instrument_id: i.id }, `Instrument set to ${i.tradingsymbol}.`).then(() => setQ(""))}>
                Use
              </Button>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  );
}
