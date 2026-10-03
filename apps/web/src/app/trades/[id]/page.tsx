"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { DataTable } from "@/components/DataTable";
import { Button, TextField, useAction } from "@/components/forms";
import { StatusPill, toneForState } from "@/components/StatusPill";
import { Card, Notice, PageHeader } from "@/components/ui";
import { apiSend } from "@/lib/api";
import { formatDateTime, formatNumber, inr, pnlClass } from "@/lib/format";
import type { Order, TradePlan, TrailMode } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const TRAIL_LABELS: Record<TrailMode, string> = {
  none: "No trailing",
  step: "Step: SL to cost after TP1, to TP1 after TP2",
  points: "Follow the price by points",
  percent: "Follow the price by %",
};

export default function TradeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const trade = useApi<TradePlan>(`/api/v1/trades/${id}`, 3000);
  const t = trade.data;
  const live = t && (t.status === "open" || t.status === "pending");

  return (
    <>
      <PageHeader
        title={t ? `${t.side} ${t.tradingsymbol ?? ""}` : "Trade"}
        description={
          t ? `${t.exchange ?? ""} · ${segmentLabel(t.segment)} · created ${formatDateTime(t.created_at)}${t.signal_id ? "" : " · manual"}` : undefined
        }
        actions={<Link href="/trades" className="text-sm text-accent underline">All trades</Link>}
      />
      {trade.error && <Notice tone="error">{trade.error}</Notice>}
      {t && (
        <div className="grid gap-4 lg:grid-cols-2 [&>*]:min-w-0">
          <Card title="Position">
            <div className="mb-3 flex flex-wrap gap-1">
              <StatusPill tone={toneForState(t.status === "open" ? "ok" : t.status)}>{t.status === "pending" ? "waiting for entry" : t.status}</StatusPill>
              {t.exit_reason && <StatusPill tone={toneForState(t.exit_reason)}>{t.exit_reason.replace("_", " ")}</StatusPill>}
              {t.trailing.mode && t.trailing.mode !== "none" && <StatusPill tone="accent">trailing: {t.trailing.mode}</StatusPill>}
            </div>
            <dl className="grid grid-cols-[9rem_1fr] gap-y-1.5 text-sm">
              <dt className="text-muted">Quantity</dt>
              <dd>
                {t.status === "open" ? `${t.open_quantity} open of ${t.quantity}` : t.quantity}
                {t.lot_size ? ` (${t.quantity / t.lot_size} lot${t.quantity / t.lot_size === 1 ? "" : "s"} of ${t.lot_size})` : ""}
              </dd>
              <dt className="text-muted">Entry</dt>
              <dd>{t.entry_price ? `${formatNumber(t.entry_price)} filled` : `${formatNumber(t.planned_entry)} planned`}</dd>
              <dt className="text-muted">Live price</dt>
              <dd>{formatNumber(t.ltp)}</dd>
              <dt className="text-muted">Open P&amp;L</dt>
              <dd className={pnlClass(t.unrealized_pnl)}>{inr(t.unrealized_pnl)}</dd>
              <dt className="text-muted">Booked P&amp;L</dt>
              <dd className={pnlClass(t.realized_pnl)}>{inr(t.realized_pnl)} <span className="text-xs text-muted">(after ₹{formatNumber(t.charges, 0)} charges)</span></dd>
              {t.exit_price && (
                <>
                  <dt className="text-muted">Avg exit</dt>
                  <dd>{formatNumber(t.exit_price)}</dd>
                </>
              )}
              {t.best_price && (
                <>
                  <dt className="text-muted">Best price seen</dt>
                  <dd>{formatNumber(t.best_price)}</dd>
                </>
              )}
            </dl>
            {live && <Actions t={t} onDone={trade.reload} />}
          </Card>

          <Card title="Price ladder">
            <PriceLadder t={t} />
          </Card>

          {live && (
            <Card title="Stop-loss, targets & trailing" className="lg:col-span-2">
              <EditForm key={JSON.stringify([t.stop_loss, t.targets, t.trailing, t.open_quantity])} t={t} onSaved={trade.reload} />
            </Card>
          )}

          <div className="lg:col-span-2">
            <h3 className="mb-2 text-sm font-medium text-muted">Orders for this trade</h3>
            <DataTable<Order>
              path={`/api/v1/orders?trade_plan_id=${t.id}`}
              refreshMs={3000}
              columns={[
                { key: "at", header: "Time", render: (o) => formatDateTime(o.created_at) },
                { key: "role", header: "Role", render: (o) => o.role },
                { key: "side", header: "Side", render: (o) => o.side },
                { key: "type", header: "Type", render: (o) => o.order_type },
                { key: "qty", header: "Qty", align: "right", render: (o) => o.quantity },
                { key: "px", header: "Price / trigger", align: "right", render: (o) => formatNumber(o.price ?? o.trigger_price) },
                { key: "avg", header: "Filled at", align: "right", render: (o) => formatNumber(o.average_price) },
                { key: "st", header: "Status", render: (o) => <StatusPill tone={toneForState(o.status)}>{o.status}</StatusPill> },
                { key: "msg", header: "Note", render: (o) => <span className="text-xs text-muted">{o.status_message ?? ""}</span> },
              ]}
            />
          </div>
        </div>
      )}
    </>
  );
}

function segmentLabel(s: string | null): string {
  return { fno: "F&O", equity: "Equity", commodity: "Commodity", currency: "Currency", index: "Index" }[s ?? ""] ?? "—";
}

function Actions({ t, onDone }: { t: TradePlan; onDone: () => void }) {
  const lot = t.lot_size ?? 1;
  const openLots = Math.floor(t.open_quantity / lot);
  const [lots, setLots] = useState("1");
  const act = useAction();
  const run = (fn: () => Promise<unknown>, ok: string) => act.run(fn, ok).then(onDone);

  if (t.status === "pending") {
    return (
      <div className="mt-4 space-y-2">
        <p className="text-xs text-muted">Waiting for the signal&apos;s entry price. You can enter now at the market price instead (same stop-loss and targets).</p>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => run(() => apiSend(`/api/v1/trades/${t.id}/enter-now`, "POST"), "Entered at market.")}>⚡ Buy now @ market</Button>
          <Button
            variant="secondary"
            onClick={() => confirm("Cancel this waiting trade?") && run(() => apiSend(`/api/v1/trades/${t.id}/close`, "POST"), "Cancelled.")}
          >
            Cancel
          </Button>
          {act.view}
        </div>
      </div>
    );
  }
  return (
    <div className="mt-4 space-y-2">
      <div className="flex flex-wrap items-end gap-2">
        {openLots > 1 && (
          <>
            <div className="w-24">
              <TextField label="Lots" value={lots} onChange={setLots} inputMode="numeric" />
            </div>
            <Button
              variant="secondary"
              onClick={() => {
                const n = Number(lots);
                if (!Number.isInteger(n) || n < 1 || n > openLots) return act.setMessage({ tone: "error", text: `Choose 1 to ${openLots} lots.` });
                return run(() => apiSend(`/api/v1/trades/${t.id}/exit`, "POST", { quantity: n * lot }), `Exiting ${n * lot}.`);
              }}
            >
              Exit lots
            </Button>
          </>
        )}
        <Button variant="danger" onClick={() => confirm(`Exit all ${t.open_quantity} at market now?`) && run(() => apiSend(`/api/v1/trades/${t.id}/exit`, "POST", {}), "Exiting all.")}>
          Exit all
        </Button>
        <Button variant="secondary" onClick={() => run(() => apiSend(`/api/v1/trades/${t.id}/stop-to-cost`, "POST"), "Stop-loss moved to cost.")}>
          SL → cost
        </Button>
      </div>
      {act.view}
    </div>
  );
}

type Row = { label: string; price: number; tone: string; note?: string };

function PriceLadder({ t }: { t: TradePlan }) {
  const rows: Row[] = [];
  rows.push({ label: "Stop-loss", price: Number(t.stop_loss), tone: "bg-bad", note: t.initial_stop_loss && t.initial_stop_loss !== t.stop_loss ? `was ${formatNumber(t.initial_stop_loss)}` : undefined });
  const entry = t.entry_price ?? t.planned_entry;
  if (entry) rows.push({ label: t.entry_price ? "Entry" : "Entry (planned)", price: Number(entry), tone: "bg-muted" });
  t.targets.forEach((l, i) => {
    if (l.status !== "cancelled") rows.push({ label: `T${i + 1} · ${l.quantity} qty`, price: Number(l.price), tone: l.status === "hit" ? "bg-good" : "bg-good/50", note: l.status === "hit" ? "hit ✓" : undefined });
  });
  if (t.ltp) rows.push({ label: "Live price", price: Number(t.ltp), tone: "bg-accent" });
  const prices = rows.map((r) => r.price);
  const lo = Math.min(...prices);
  const hi = Math.max(...prices);
  const span = hi - lo || 1;
  const sorted = [...rows].sort((a, b) => b.price - a.price);
  return (
    <ul className="space-y-1.5" aria-label="Price levels, highest first">
      {sorted.map((r) => (
        <li key={`${r.label}-${r.price}`} className="grid grid-cols-[8rem_1fr_5rem] items-center gap-2 text-sm">
          <span className={r.label === "Live price" ? "font-medium text-accent" : "text-muted"}>{r.label}</span>
          <span className="relative h-2 rounded-full bg-panel-2">
            <span className={`absolute top-0 h-2 w-2 rounded-full ${r.tone}`} style={{ left: `calc(${((r.price - lo) / span) * 100}% - 4px)` }} />
          </span>
          <span className="text-right font-mono tabular-nums">
            {formatNumber(r.price)}
            {r.note && <span className="block text-[10px] text-muted">{r.note}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

function EditForm({ t, onSaved }: { t: TradePlan; onSaved: () => void }) {
  const lot = t.lot_size ?? 1;
  const hit = t.targets.filter((l) => l.status === "hit");
  const [stop, setStop] = useState(String(Number(t.stop_loss)));
  const [legs, setLegs] = useState(
    t.targets.filter((l) => l.status === "open").map((l) => ({ price: String(Number(l.price)), lots: String(l.quantity / lot) })),
  );
  const [mode, setMode] = useState<TrailMode>((t.trailing.mode as TrailMode) ?? "none");
  const [value, setValue] = useState(String(Number(t.trailing.value ?? 0)));
  const act = useAction();
  const avail = t.status === "pending" ? t.quantity : t.open_quantity;
  const usedLots = legs.reduce((s, l) => s + (Number(l.lots) || 0), 0);

  async function save() {
    const ok = await act.run(
      () =>
        apiSend(`/api/v1/trades/${t.id}`, "PATCH", {
          stop_loss: Number(stop),
          targets: legs.filter((l) => l.price && l.lots).map((l) => ({ price: Number(l.price), quantity: Math.round(Number(l.lots) * lot) })),
          trail_mode: mode,
          trail_value: Number(value) || 0,
        }),
      "Saved.",
    );
    if (ok) onSaved();
  }

  return (
    <div className="grid gap-4 md:grid-cols-3">
      <div>
        <TextField label="Stop-loss" value={stop} onChange={setStop} inputMode="decimal" hint="Changes the working stop order right away." />
      </div>
      <div className="md:col-span-2">
        <p className="text-sm text-muted">Targets (exit lots at each price)</p>
        {hit.map((l, i) => (
          <p key={`hit-${i}`} className="mt-1 text-sm text-good">
            T{i + 1} {formatNumber(l.price)} × {l.quantity} — hit ✓
          </p>
        ))}
        {legs.map((l, i) => (
          <div key={i} className="mt-1 grid grid-cols-[1fr_6rem_auto] items-end gap-2">
            <TextField label={`T${hit.length + i + 1} price`} value={l.price} inputMode="decimal" onChange={(v) => setLegs((s) => s.map((x, j) => (j === i ? { ...x, price: v } : x)))} />
            <TextField label="Lots" value={l.lots} inputMode="numeric" onChange={(v) => setLegs((s) => s.map((x, j) => (j === i ? { ...x, lots: v } : x)))} />
            <button type="button" aria-label={`Remove target ${hit.length + i + 1}`} onClick={() => setLegs((s) => s.filter((_, j) => j !== i))} className="mb-1 rounded px-2 py-1 text-sm text-muted hover:text-bad">
              ✕
            </button>
          </div>
        ))}
        <div className="mt-2 flex items-center gap-3 text-xs text-muted">
          <button type="button" onClick={() => setLegs((s) => [...s, { price: "", lots: "1" }])} className="rounded border border-border px-2 py-1 text-text">
            + Add target
          </button>
          <span>
            {usedLots} of {avail / lot} lots have a target{usedLots < avail / lot ? "; the rest rides with the stop-loss" : ""}.
          </span>
        </div>
      </div>
      <label className="block text-sm md:col-span-2">
        <span className="text-muted">Trailing stop-loss</span>
        <select value={mode} onChange={(e) => setMode(e.target.value as TrailMode)} className="mt-1 w-full rounded-md border border-border bg-bg px-3 py-1.5">
          {(Object.keys(TRAIL_LABELS) as TrailMode[]).map((m) => (
            <option key={m} value={m}>{TRAIL_LABELS[m]}</option>
          ))}
        </select>
      </label>
      {(mode === "points" || mode === "percent") && (
        <TextField label={mode === "points" ? "Trail distance (points)" : "Trail distance (%)"} value={value} onChange={setValue} inputMode="decimal" />
      )}
      <div className="flex items-center gap-2 md:col-span-3">
        <Button onClick={save}>Save changes</Button>
        {act.view}
      </div>
    </div>
  );
}
