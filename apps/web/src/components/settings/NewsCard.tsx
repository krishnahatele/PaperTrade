"use client";

import { useState } from "react";
import { Button, TextField, Toggle, useAction } from "@/components/forms";
import { Card, Notice } from "@/components/ui";
import { apiSend } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { Feed, NewsSettings } from "@/lib/types";
import { useApi } from "@/lib/useApi";

type NewsStatus = { last_poll: string | null; feed_errors: Record<string, string> };
type WatchDraft = { symbol: string; label: string; threshold_pct: string; window_minutes: string; enabled: boolean };

const inputCls = "w-full rounded-md border border-border bg-bg px-2 py-1 text-sm outline-none focus:border-accent";

export function NewsCard() {
  const settings = useApi<NewsSettings>("/api/v1/news/settings");
  const status = useApi<NewsStatus>("/api/v1/news/status");
  const errors = Object.entries(status.data?.feed_errors ?? {});

  return (
    <Card title="News & market alerts">
      {settings.error && <Notice tone="error">{settings.error}</Notice>}
      {settings.data ? (
        <Form
          key={JSON.stringify(settings.data)}
          data={settings.data}
          onSaved={() => {
            settings.reload();
            status.reload();
          }}
        />
      ) : (
        !settings.error && <p className="text-sm text-muted">Loading…</p>
      )}
      <div className="mt-3 text-xs text-muted">
        Last fetched: {formatDateTime(status.data?.last_poll)}
        {errors.length > 0 && (
          <ul className="mt-1 text-bad">
            {errors.map(([name, err]) => (
              <li key={name}>
                {name}: {err}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

function Form({ data, onSaved }: { data: NewsSettings; onSaved: () => void }) {
  const [enabled, setEnabled] = useState(data.enabled);
  const [marketAlerts, setMarketAlerts] = useState(data.market_alerts);
  const [poll, setPoll] = useState(String(data.poll_minutes));
  const [cooldown, setCooldown] = useState(String(data.alert_cooldown_minutes));
  const [keywords, setKeywords] = useState(data.keywords.join(", "));
  const [feeds, setFeeds] = useState<Feed[]>(data.feeds);
  const [watches, setWatches] = useState<WatchDraft[]>(
    data.watches.map((w) => ({ ...w, threshold_pct: String(w.threshold_pct), window_minutes: String(w.window_minutes) })),
  );
  const [newFeed, setNewFeed] = useState({ name: "", url: "" });
  const [result, setResult] = useState<{ fetched: number; new: number; alerts: number } | null>(null);
  const act = useAction();

  const setFeed = (i: number, patch: Partial<Feed>) => setFeeds((fs) => fs.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  const setWatch = (i: number, patch: Partial<WatchDraft>) => setWatches((ws) => ws.map((w, j) => (j === i ? { ...w, ...patch } : w)));

  function addFeed() {
    const name = newFeed.name.trim();
    const url = newFeed.url.trim();
    if (!url) return;
    setFeeds((fs) => [...fs, { name: name || url, url, enabled: true }]);
    setNewFeed({ name: "", url: "" });
  }

  function save() {
    return act
      .run(async () => {
        const toInt = (v: string, label: string) => {
          const n = Number(v);
          if (!Number.isInteger(n) || n <= 0) throw new Error(`${label} must be a whole number above 0.`);
          return n;
        };
        const body: NewsSettings = {
          enabled,
          market_alerts: marketAlerts,
          poll_minutes: toInt(poll, "Check every (minutes)"),
          alert_cooldown_minutes: toInt(cooldown, "Alert cooldown"),
          keywords: keywords
            .split(/[,\n]/)
            .map((k) => k.trim())
            .filter(Boolean),
          feeds: feeds.filter((f) => f.url.trim()).map((f) => ({ ...f, name: f.name.trim() || f.url.trim(), url: f.url.trim() })),
          watches: watches
            .filter((w) => w.symbol.trim())
            .map((w) => ({
              symbol: w.symbol.trim().toUpperCase(),
              label: w.label.trim() || w.symbol.trim().toUpperCase(),
              threshold_pct: w.threshold_pct.trim(),
              window_minutes: toInt(w.window_minutes, `Window for ${w.symbol.trim()}`),
              enabled: w.enabled,
            })),
        };
        await apiSend("/api/v1/news/settings", "PUT", body);
      }, "Saved.")
      .then((ok) => {
        if (ok) onSaved();
      });
  }

  return (
    <>
      <div className="divide-y divide-border">
        <Toggle label="Fetch news" description="Read the RSS feeds below on a timer." checked={enabled} onChange={setEnabled} />
        <Toggle label="Market-move alerts" description="Alert when a watched instrument moves sharply." checked={marketAlerts} onChange={setMarketAlerts} />
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <TextField label="Check every (minutes)" value={poll} onChange={setPoll} inputMode="numeric" />
        <TextField label="Alert cooldown (minutes)" value={cooldown} onChange={setCooldown} inputMode="numeric" hint="No repeat alert for the same thing within this time." />
      </div>

      <label className="mt-3 block text-sm">
        <span className="text-muted">Keywords</span>
        <textarea
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
          rows={3}
          placeholder="RBI, Fed, crude, rate cut"
          className="mt-1 w-full rounded-md border border-border bg-bg px-3 py-1.5 outline-none focus:border-accent"
        />
        <span className="mt-1 block text-xs text-muted">
          Headlines containing these words become alerts (sent to the app and the Telegram bot). Short capitalised words like RBI or Fed match exactly.
        </span>
      </label>

      <h4 className="mt-4 text-sm font-medium">News feeds</h4>
      <ul className="mt-2 space-y-2">
        {feeds.map((f, i) => (
          <li key={i} className="flex flex-wrap items-center gap-2 sm:flex-nowrap">
            <input type="checkbox" checked={f.enabled} onChange={(e) => setFeed(i, { enabled: e.target.checked })} aria-label={`Use feed ${f.name}`} className="h-4 w-4 accent-accent" />
            <input value={f.name} onChange={(e) => setFeed(i, { name: e.target.value })} aria-label="Feed name" className={`${inputCls} sm:w-40`} />
            <input value={f.url} onChange={(e) => setFeed(i, { url: e.target.value })} aria-label="Feed RSS URL" className={`${inputCls} min-w-0 flex-1`} />
            <button type="button" onClick={() => setFeeds((fs) => fs.filter((_, j) => j !== i))} aria-label={`Remove feed ${f.name}`} className="px-2 text-sm text-bad">
              ✕
            </button>
          </li>
        ))}
        {feeds.length === 0 && <li className="text-xs text-muted">No feeds yet.</li>}
      </ul>
      <div className="mt-2 flex flex-wrap items-end gap-2 sm:flex-nowrap">
        <div className="sm:w-40">
          <TextField label="Name" value={newFeed.name} onChange={(v) => setNewFeed((s) => ({ ...s, name: v }))} placeholder="Moneycontrol" />
        </div>
        <div className="min-w-0 flex-1">
          <TextField label="RSS URL" value={newFeed.url} onChange={(v) => setNewFeed((s) => ({ ...s, url: v }))} placeholder="https://…/rss" />
        </div>
        <Button variant="secondary" disabled={!newFeed.url.trim()} onClick={addFeed}>
          Add feed
        </Button>
      </div>

      <h4 className="mt-4 text-sm font-medium">Watched instruments</h4>
      <p className="text-xs text-muted">
        Symbol: a contract name or an underlying (e.g. CRUDEOIL, NIFTY 50, NIFTY BANK, INDIA VIX, GOLD); underlyings use the nearest future.
      </p>
      <div className="mt-2 space-y-2">
        {watches.map((w, i) => (
          <div key={i} className="grid grid-cols-2 items-end gap-2 rounded-md border border-border p-2 sm:grid-cols-[1.3fr_1.3fr_0.8fr_0.8fr_auto_auto]">
            <label className="block text-xs">
              <span className="text-muted">Symbol</span>
              <input value={w.symbol} onChange={(e) => setWatch(i, { symbol: e.target.value })} placeholder="NIFTY 50" className={`${inputCls} mt-1`} />
            </label>
            <label className="block text-xs">
              <span className="text-muted">Label</span>
              <input value={w.label} onChange={(e) => setWatch(i, { label: e.target.value })} placeholder="Nifty" className={`${inputCls} mt-1`} />
            </label>
            <label className="block text-xs">
              <span className="text-muted">Move %</span>
              <input value={w.threshold_pct} onChange={(e) => setWatch(i, { threshold_pct: e.target.value })} inputMode="decimal" className={`${inputCls} mt-1`} />
            </label>
            <label className="block text-xs">
              <span className="text-muted">Within (min)</span>
              <input value={w.window_minutes} onChange={(e) => setWatch(i, { window_minutes: e.target.value })} inputMode="numeric" className={`${inputCls} mt-1`} />
            </label>
            <label className="flex items-center gap-1 pb-1.5 text-xs">
              <input type="checkbox" checked={w.enabled} onChange={(e) => setWatch(i, { enabled: e.target.checked })} className="h-4 w-4 accent-accent" />
              On
            </label>
            <button
              type="button"
              onClick={() => setWatches((ws) => ws.filter((_, j) => j !== i))}
              aria-label={`Remove watch ${w.symbol}`}
              className="pb-1.5 text-left text-sm text-bad"
            >
              ✕
            </button>
          </div>
        ))}
        {watches.length === 0 && <p className="text-xs text-muted">Nothing watched yet.</p>}
      </div>
      <div className="mt-2">
        <Button
          variant="secondary"
          onClick={() => setWatches((ws) => [...ws, { symbol: "", label: "", threshold_pct: "1", window_minutes: "15", enabled: true }])}
        >
          Add instrument
        </Button>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button onClick={save}>Save</Button>
        <Button
          variant="secondary"
          onClick={() =>
            act
              .run(async () => setResult(await apiSend<{ fetched: number; new: number; alerts: number }>("/api/v1/news/refresh", "POST")))
              .then((ok) => {
                if (ok) onSaved();
              })
          }
        >
          Fetch news now
        </Button>
        {act.view}
      </div>
      {result && (
        <p className="mt-2 text-sm" role="status">
          Fetched {result.fetched} headlines, {result.new} new, {result.alerts} alerts.
        </p>
      )}
    </>
  );
}
