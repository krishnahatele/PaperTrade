"use client";

import { useState } from "react";
import { DataTable } from "@/components/DataTable";
import { Button } from "@/components/forms";
import { StatusPill } from "@/components/StatusPill";
import { API_URL } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { formatDateTime, formatNumber, inr, pnlClass } from "@/lib/format";
import type { ReplayOutcome, ReplayTrade } from "@/lib/types";
import { exitLabel, OUTCOME_LABELS, outcomeTone, SEGMENT_LABELS, segmentLabel } from "./labels";

const OUTCOMES = Object.keys(OUTCOME_LABELS) as ReplayOutcome[];
const selectCls = "mt-1 w-full rounded-md border border-border bg-bg px-2 py-1.5 text-sm outline-none focus:border-accent";

function timeOnly(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
}

async function downloadCsv(runId: string) {
  const token = getToken();
  const res = await fetch(`${API_URL}/api/v1/replays/${runId}/trades.csv`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `replay-${runId.slice(0, 8)}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ReplayTrades({ runId, sources }: { runId: string; sources: string[] }) {
  const [outcome, setOutcome] = useState("");
  const [source, setSource] = useState("");
  const [segment, setSegment] = useState("");
  const [open, setOpen] = useState<ReplayTrade | null>(null);
  const [dlError, setDlError] = useState<string | null>(null);

  let query = "";
  if (outcome) query += `&outcome=${outcome}`;
  if (source) query += `&source=${encodeURIComponent(source)}`;
  if (segment) query += `&segment=${segment}`;

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h3 className="text-sm font-medium text-muted">Every message</h3>
        <div className="flex items-center gap-2">
          {dlError && <span role="alert" className="text-xs text-bad">{dlError}</span>}
          <Button
            variant="secondary"
            onClick={async () => {
              setDlError(null);
              try {
                await downloadCsv(runId);
              } catch (e) {
                setDlError(e instanceof Error ? e.message : String(e));
              }
            }}
          >
            Download CSV
          </Button>
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="block text-sm">
          <span className="text-muted">Result</span>
          <select value={outcome} onChange={(e) => setOutcome(e.target.value)} className={selectCls}>
            <option value="">All</option>
            {OUTCOMES.map((o) => (
              <option key={o} value={o}>{OUTCOME_LABELS[o]}</option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          <span className="text-muted">Group</span>
          <select value={source} onChange={(e) => setSource(e.target.value)} className={selectCls}>
            <option value="">All</option>
            {sources.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          <span className="text-muted">Segment</span>
          <select value={segment} onChange={(e) => setSegment(e.target.value)} className={selectCls}>
            <option value="">All</option>
            {Object.entries(SEGMENT_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </label>
      </div>

      {open && (
        <div className="fixed inset-x-4 bottom-4 z-30 max-h-[50vh] overflow-auto rounded-lg border border-accent/40 bg-panel p-4 shadow-lg md:left-auto md:w-[30rem]" role="dialog" aria-label="Original message">
          <div className="mb-2 flex items-start justify-between gap-3">
            <p className="text-xs text-muted">
              {open.source_name} · {formatDateTime(open.message_at)}
              {open.tradingsymbol && ` · ${open.tradingsymbol}`}
            </p>
            <button type="button" onClick={() => setOpen(null)} className="text-xs text-accent underline">Close</button>
          </div>
          <p className="whitespace-pre-wrap break-words text-sm">{open.message_text}</p>
          {open.notes && <p className="mt-2 text-xs text-muted">Notes: {open.notes}</p>}
        </div>
      )}

      <DataTable<ReplayTrade>
        key={query}
        path={`/api/v1/replays/${runId}/trades`}
        query={query}
        emptyText="No messages match these filters."
        columns={[
          { key: "at", header: "Message time", render: (t) => <span className="text-xs">{formatDateTime(t.message_at)}</span> },
          { key: "src", header: "Group", render: (t) => <span className="inline-block max-w-[10rem] truncate align-bottom" title={t.source_name}>{t.source_name}</span> },
          {
            key: "sym",
            header: "Instrument",
            render: (t) => (
              <span className="flex items-center gap-1">
                {t.side && <StatusPill tone={t.side === "BUY" ? "good" : "bad"}>{t.side}</StatusPill>}
                <span className="font-medium">{t.tradingsymbol ?? "—"}</span>
                {t.segment && <span className="text-xs text-muted">{segmentLabel(t.segment)}</span>}
              </span>
            ),
          },
          {
            key: "out",
            header: "Result",
            render: (t) => (
              <span className="block">
                <StatusPill tone={outcomeTone(t.outcome)}>{OUTCOME_LABELS[t.outcome] ?? t.outcome}</StatusPill>
                {t.notes && !["win", "loss", "breakeven"].includes(t.outcome) && (
                  <span className="mt-0.5 block max-w-xs whitespace-normal text-xs text-muted">{t.notes}</span>
                )}
              </span>
            ),
          },
          { key: "qty", header: "Qty", align: "right", render: (t) => t.quantity ?? "—" },
          {
            key: "entry",
            header: "Entry",
            align: "right",
            render: (t) => (t.entry_price ? <span>{formatNumber(t.entry_price)} <span className="text-xs text-muted">@ {timeOnly(t.entry_at)}</span></span> : "—"),
          },
          {
            key: "exit",
            header: "Exit",
            align: "right",
            render: (t) => (t.exit_price ? <span>{formatNumber(t.exit_price)} <span className="text-xs text-muted">@ {timeOnly(t.exit_at)}</span></span> : "—"),
          },
          { key: "why", header: "Exit reason", render: (t) => exitLabel(t.exit_reason) },
          { key: "tp", header: "TP hits", align: "right", render: (t) => t.targets_hit },
          { key: "pnl", header: "Net P&L", align: "right", render: (t) => <span className={pnlClass(t.net_pnl)}>{inr(t.net_pnl)}</span> },
          { key: "r", header: "R", align: "right", render: (t) => formatNumber(t.r_multiple) },
          {
            key: "msg",
            header: "",
            render: (t) => (
              <button
                type="button"
                onClick={() => setOpen(open?.id === t.id ? null : t)}
                aria-expanded={open?.id === t.id}
                className="rounded border border-border px-2 py-0.5 text-xs hover:bg-panel-2"
              >
                Message
              </button>
            ),
          },
        ]}
      />
    </section>
  );
}
