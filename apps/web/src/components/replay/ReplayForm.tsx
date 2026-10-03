"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, TextField, Toggle, useAction } from "@/components/forms";
import { Card } from "@/components/ui";
import { apiSend, type Page } from "@/lib/api";
import type { ReplayRun, SignalSource } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const MAX_DAYS = 31;
const DAY_MS = 86_400_000;

/** Today's date in IST as YYYY-MM-DD, shifted by `offsetDays`. */
function istDate(offsetDays: number): string {
  return new Date(Date.now() + 5.5 * 3_600_000 + offsetDays * DAY_MS).toISOString().slice(0, 10);
}

function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / DAY_MS);
}

const selectCls = "mt-1 w-full rounded-md border border-border bg-bg px-3 py-1.5 outline-none focus:border-accent";

export function ReplayForm() {
  const router = useRouter();
  const [dates] = useState(() => ({ yesterday: istDate(-1), today: istDate(0) }));
  const [name, setName] = useState("");
  const [dateFrom, setDateFrom] = useState(dates.yesterday);
  const [dateTo, setDateTo] = useState(dates.yesterday);
  const [sourceIds, setSourceIds] = useState<string[]>([]);
  const [messages, setMessages] = useState("auto");
  const [useAi, setUseAi] = useState(false);
  const [capital, setCapital] = useState("");
  const [riskPct, setRiskPct] = useState("");
  const [exitMode, setExitMode] = useState("");
  const [trailMode, setTrailMode] = useState("");
  const [trailValue, setTrailValue] = useState("");
  const [entryWindow, setEntryWindow] = useState("30");
  const [squareOff, setSquareOff] = useState(true);
  const [sameCandle, setSameCandle] = useState("stop_first");
  const act = useAction();

  const sources = useApi<Page<SignalSource>>("/api/v1/signal-sources?kind=telegram&limit=200");
  const groups = (sources.data?.items ?? []).filter((s) => s.kind === "telegram");

  function quick(days: number) {
    setDateFrom(istDate(-days));
    setDateTo(dates.yesterday);
  }

  const span = daysBetween(dateFrom, dateTo);
  const rangeError =
    !dateFrom || !dateTo
      ? "Pick both dates."
      : span < 0
        ? "“To” date is before “From” date."
        : span >= MAX_DAYS
          ? `Replay at most ${MAX_DAYS} days at a time.`
          : dateFrom > dates.today
            ? "“From” date is in the future."
            : null;

  function toggleSource(id: string) {
    setSourceIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  }

  async function submit() {
    if (rangeError) {
      act.setMessage({ tone: "error", text: rangeError });
      return;
    }
    const settings: Record<string, string | number> = {};
    const num = (label: string, v: string): number | null => {
      if (v.trim() === "") return null;
      const n = Number(v);
      if (Number.isNaN(n) || n < 0) throw new Error(`${label} must be a positive number.`);
      return n;
    };
    let windowMinutes = 30;
    try {
      const c = num("Capital", capital);
      if (c !== null) settings.capital = c;
      const r = num("Risk per trade", riskPct);
      if (r !== null) settings.risk_per_trade_pct = r;
      if (exitMode) settings.exit_mode = exitMode;
      if (trailMode) settings.trail_mode = trailMode;
      const tv = num("Trail value", trailValue);
      if (tv !== null) settings.trail_value = tv;
      windowMinutes = num("Entry window", entryWindow) ?? 30;
    } catch (e) {
      act.setMessage({ tone: "error", text: e instanceof Error ? e.message : String(e) });
      return;
    }
    act.setMessage(null);
    try {
      const run = await apiSend<ReplayRun>("/api/v1/replays", "POST", {
        ...(name.trim() ? { name: name.trim() } : {}),
        date_from: dateFrom,
        date_to: dateTo,
        source_ids: sourceIds,
        messages,
        use_ai: useAi,
        settings,
        entry_window_minutes: Math.round(windowMinutes),
        square_off: squareOff,
        same_candle: sameCandle,
      });
      router.push(`/replay/${run.id}`);
    } catch (e) {
      act.setMessage({ tone: "error", text: e instanceof Error ? e.message : String(e) });
    }
  }

  return (
    <Card title="New replay">
      <form
        className="space-y-5"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Days</legend>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <TextField label="From" type="date" value={dateFrom} onChange={setDateFrom} />
            <TextField label="To" type="date" value={dateTo} onChange={setDateTo} />
          </div>
          <div className="flex flex-wrap gap-2">
            <QuickButton onClick={() => quick(1)}>Yesterday</QuickButton>
            <QuickButton onClick={() => quick(2)}>Last 2 days</QuickButton>
            <QuickButton onClick={() => quick(7)}>Last 7 days</QuickButton>
            <span className="self-center text-xs text-muted">Up to {MAX_DAYS} days.</span>
          </div>
          {rangeError && <p className="text-xs text-bad">{rangeError}</p>}
        </fieldset>

        <fieldset>
          <legend className="text-sm font-medium">Groups</legend>
          <p className="mb-2 text-xs text-muted">None ticked = all your Telegram groups.</p>
          {sources.error && <p className="text-xs text-bad">Could not load groups: {sources.error}</p>}
          {sources.data && groups.length === 0 && <p className="text-xs text-muted">No Telegram groups added yet (see Sources).</p>}
          <div className="grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
            {groups.map((g) => (
              <label key={g.id} className="flex items-center gap-2 rounded px-1 py-1 text-sm hover:bg-panel-2">
                <input type="checkbox" checked={sourceIds.includes(g.id)} onChange={() => toggleSource(g.id)} className="accent-[var(--accent)]" />
                <span className="truncate">{g.name}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="text-muted">Messages</span>
            <select value={messages} onChange={(e) => setMessages(e.target.value)} className={selectCls}>
              <option value="auto">Auto: Telegram history if logged in, else messages MarketOS stored</option>
              <option value="telegram">Telegram history</option>
              <option value="stored">Messages MarketOS stored</option>
            </select>
          </label>
          <TextField label="Name (optional)" value={name} onChange={setName} placeholder="e.g. Week 40 check" />
        </div>

        <Toggle label="Use AI for unclear messages" description="Uses API credits." checked={useAi} onChange={setUseAi} />

        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Risk (optional)</legend>
          <p className="text-xs text-muted">Leave empty to use your paper account settings.</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <TextField label="Capital (₹)" value={capital} onChange={setCapital} inputMode="decimal" placeholder="account" />
            <TextField label="Risk per trade (%)" value={riskPct} onChange={setRiskPct} inputMode="decimal" placeholder="account" />
            <label className="block text-sm">
              <span className="text-muted">Exit</span>
              <select value={exitMode} onChange={(e) => setExitMode(e.target.value)} className={selectCls}>
                <option value="">Account setting</option>
                <option value="split">Split across targets</option>
                <option value="single">All at one target</option>
              </select>
            </label>
            <label className="block text-sm">
              <span className="text-muted">Trailing stop</span>
              <select value={trailMode} onChange={(e) => setTrailMode(e.target.value)} className={selectCls}>
                <option value="">Account setting</option>
                <option value="step">Step (cost, then TP1, …)</option>
                <option value="points">Points</option>
                <option value="percent">Percent</option>
                <option value="none">None</option>
              </select>
            </label>
            <TextField label="Trail value" value={trailValue} onChange={setTrailValue} inputMode="decimal" placeholder="account" />
          </div>
        </fieldset>

        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Rules</legend>
          <div className="grid gap-3 sm:grid-cols-2">
            <TextField label="Entry window (minutes)" value={entryWindow} onChange={setEntryWindow} inputMode="numeric" hint="How long after the message the entry price may be hit." />
            <label className="block text-sm">
              <span className="text-muted">Candle hits both SL and target</span>
              <select value={sameCandle} onChange={(e) => setSameCandle(e.target.value)} className={selectCls}>
                <option value="stop_first">Assume SL first (safer)</option>
                <option value="target_first">Assume target first</option>
              </select>
            </label>
          </div>
          <Toggle
            label="Close intraday positions at session end"
            description="15:20 for NSE/BSE, 23:25 for MCX."
            checked={squareOff}
            onChange={setSquareOff}
          />
        </fieldset>

        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={submit} disabled={!!rangeError}>Run replay</Button>
          {act.view}
        </div>
      </form>
    </Card>
  );
}

function QuickButton({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} className="rounded-md border border-border px-2 py-1 text-xs hover:bg-panel-2">
      {children}
    </button>
  );
}
