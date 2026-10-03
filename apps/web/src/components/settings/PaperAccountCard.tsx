"use client";

import { useState } from "react";
import { Button, TextField, Toggle, useAction } from "@/components/forms";
import { Card } from "@/components/ui";
import { apiSend, type Page } from "@/lib/api";
import type { BrokerAccount, TrailMode } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const FIELDS: { key: string; label: string; hint: string }[] = [
  { key: "capital", label: "Capital (₹)", hint: "Paper money used for sizing." },
  { key: "risk_per_trade_pct", label: "Risk per trade (%)", hint: "Loss if the stop is hit. 1% is common." },
  { key: "max_position_pct", label: "Max position size (%)", hint: "Cap on the value of one trade." },
  { key: "max_open_trades", label: "Max open trades", hint: "New signals are skipped beyond this." },
  { key: "daily_loss_limit_pct", label: "Daily loss limit (%)", hint: "Stop taking trades for the day after this loss." },
  { key: "slippage_bps", label: "Slippage (bps)", hint: "Simulated cost on market fills. 5 = 0.05%." },
  { key: "charges_per_order", label: "Charges per order (₹)", hint: "Brokerage + taxes estimate." },
];

type ExitMode = "split" | "single";

const EXIT_MODES: { value: ExitMode; label: string }[] = [
  { value: "split", label: "Split lots across targets (TP1, TP2, …)" },
  { value: "single", label: "Everything at one target" },
];

const TRAIL_MODES: { value: TrailMode; label: string }[] = [
  { value: "step", label: "Step: SL to cost after TP1, to TP1 after TP2 (recommended)" },
  { value: "points", label: "Follow price by points" },
  { value: "percent", label: "Follow price by %" },
  { value: "none", label: "No trailing" },
];

const selectCls = "mt-1 w-full rounded-md border border-border bg-bg px-3 py-1.5";

function setting(acct: BrokerAccount, key: string, fallback: string): string {
  const v = acct.settings[key];
  return v === undefined || v === null || v === "" ? fallback : String(v);
}

export function PaperAccountCard() {
  const accounts = useApi<Page<BrokerAccount>>("/api/v1/broker-accounts");
  const acct = accounts.data?.items.find((a) => a.mode === "paper");
  return (
    <Card title="Paper account & risk">
      {acct ? <Form key={JSON.stringify(acct.settings)} acct={acct} onSaved={accounts.reload} /> : <p className="text-sm text-muted">Loading…</p>}
    </Card>
  );
}

function Form({ acct, onSaved }: { acct: BrokerAccount; onSaved: () => void }) {
  const [vals, setVals] = useState<Record<string, string>>(
    Object.fromEntries(FIELDS.map((f) => [f.key, String(Number(acct.settings[f.key] ?? ""))])),
  );
  const [exitMode, setExitMode] = useState<ExitMode>(setting(acct, "exit_mode", "split") === "single" ? "single" : "split");
  const [targetIndex, setTargetIndex] = useState(setting(acct, "target_index", "1"));
  const [maxSplit, setMaxSplit] = useState(setting(acct, "max_split_targets", "3"));
  const [trailMode, setTrailMode] = useState<TrailMode>(
    TRAIL_MODES.find((m) => m.value === acct.settings.trail_mode)?.value ?? "step",
  );
  const [trailValue, setTrailValue] = useState(setting(acct, "trail_value", "0"));
  const act = useAction();
  const save = (settings: Record<string, unknown>) =>
    act.run(() => apiSend(`/api/v1/broker-accounts/${acct.id}`, "PATCH", { settings }), "Saved.").then(onSaved);

  return (
    <>
      <div className="divide-y divide-border">
        <Toggle label="Auto-execute on this account" description="Validated signals become paper trades automatically (needs the global switch on too)." checked={Boolean(acct.settings.auto_execute)} onChange={(v) => save({ auto_execute: v })} />
        <Toggle label="Allow short selling" description="Take SELL signals on instruments you don't hold." checked={Boolean(acct.settings.allow_short)} onChange={(v) => save({ allow_short: v })} />
        <Toggle label="Allow 1 lot when sizing rounds to zero" description="Only if one lot risks at most 2× the per-trade budget." checked={Boolean(acct.settings.allow_min_lot)} onChange={(v) => save({ allow_min_lot: v })} />
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        {FIELDS.map((f) => (
          <TextField key={f.key} label={f.label} hint={f.hint} value={vals[f.key] ?? ""} inputMode="decimal" onChange={(v) => setVals((s) => ({ ...s, [f.key]: v }))} />
        ))}
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="text-muted">How to exit</span>
          <select value={exitMode} onChange={(e) => setExitMode(e.target.value as ExitMode)} className={selectCls}>
            {EXIT_MODES.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
        </label>
        {exitMode === "single" ? (
          <TextField label="Exit at target #" hint="1 = first target in the signal." value={targetIndex} inputMode="numeric" onChange={setTargetIndex} />
        ) : (
          <TextField label="Use up to N targets" hint="Lots are spread over the first N targets." value={maxSplit} inputMode="numeric" onChange={setMaxSplit} />
        )}
        <label className="block text-sm">
          <span className="text-muted">Trailing stop-loss</span>
          <select value={trailMode} onChange={(e) => setTrailMode(e.target.value as TrailMode)} className={selectCls}>
            {TRAIL_MODES.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
        </label>
        {(trailMode === "points" || trailMode === "percent") && (
          <TextField
            label={trailMode === "points" ? "Trail distance (points)" : "Trail distance (%)"}
            hint="SL stays this far behind the best price."
            value={trailValue}
            inputMode="decimal"
            onChange={setTrailValue}
          />
        )}
      </div>
      <div className="mt-3 flex items-center gap-2">
        <Button
          onClick={() =>
            save({
              ...Object.fromEntries(FIELDS.map((f) => [f.key, vals[f.key]])),
              exit_mode: exitMode,
              target_index: targetIndex,
              max_split_targets: maxSplit,
              trail_mode: trailMode,
              trail_value: trailValue,
            })
          }
        >
          Save
        </Button>
        {act.view}
      </div>
    </>
  );
}
