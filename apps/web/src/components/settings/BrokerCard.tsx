"use client";

import { useState } from "react";
import { Button, TextField, useAction } from "@/components/forms";
import { StatusPill } from "@/components/StatusPill";
import { Card, Notice } from "@/components/ui";
import { apiSend } from "@/lib/api";
import { formatDateTime, formatNumber, inr } from "@/lib/format";
import type { BrokerCapabilities, BrokerRuntime, BrokerStatus, ConnectionTest, DataSource } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const CAPABILITIES: { key: keyof BrokerCapabilities; label: string }[] = [
  { key: "broker_bracket", label: "Target + SL held at the broker" },
  { key: "broker_trailing", label: "Trailing SL at the broker" },
  { key: "exit_all", label: "Exit all positions" },
  { key: "kill_switch", label: "Broker kill switch" },
  { key: "market_data", label: "Live prices" },
  { key: "historical", label: "Historical candles for replay" },
];

const SOURCES: { value: DataSource; label: string }[] = [
  { value: "auto", label: "Auto (Kite if logged in, else Dhan)" },
  { value: "kite", label: "Kite" },
  { value: "dhan", label: "Dhan" },
  { value: "manual", label: "Manual (practice prices)" },
];

const selectCls = "mt-1 w-full rounded-md border border-border bg-bg px-3 py-1.5";

function timeAgo(iso: string): string {
  const ms = new Date().getTime() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return formatDateTime(iso);
  const min = Math.round(ms / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const h = Math.round(min / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.round(h / 24)} days ago`;
}

export function BrokerCard() {
  const brokers = useApi<BrokerStatus[]>("/api/v1/brokers");
  const runtime = useApi<BrokerRuntime>("/api/v1/brokers/settings");
  const act = useAction();

  const reload = () => {
    brokers.reload();
    runtime.reload();
  };
  const patch = (body: Partial<Pick<BrokerRuntime, "primary" | "market_data" | "history">>) =>
    act.run(() => apiSend("/api/v1/brokers/settings", "PATCH", body), "Saved.").then(reload);

  const list = brokers.data ?? [];
  const primary = runtime.data?.primary ?? list.find((b) => b.selected)?.info.id ?? "";
  const current = list.find((b) => b.info.id === primary);
  const error = brokers.error ?? runtime.error;

  return (
    <Card title="Broker">
      {error && <Notice tone="error">{error}</Notice>}
      {!brokers.data || !runtime.data ? (
        !error && <p className="text-sm text-muted">Loading…</p>
      ) : (
        <>
          <label className="block text-sm">
            <span className="text-muted">Broker</span>
            <select value={primary} onChange={(e) => patch({ primary: e.target.value })} className={selectCls}>
              {list.map((b) => (
                <option key={b.info.id} value={b.info.id} disabled={!b.info.available}>
                  {b.info.label}
                </option>
              ))}
            </select>
          </label>

          {act.view && <div className="mt-2">{act.view}</div>}

          {current && (
            <BrokerDetails
              key={`${current.info.id}:${JSON.stringify(current.fields)}`}
              status={current}
              tokenSavedAt={runtime.data.dhan_token_saved_at}
              onChange={reload}
            />
          )}

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="text-muted">Live prices from</span>
              <select value={runtime.data.market_data} onChange={(e) => patch({ market_data: e.target.value as DataSource })} className={selectCls}>
                {SOURCES.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="text-muted">Replay candles from</span>
              <select value={runtime.data.history} onChange={(e) => patch({ history: e.target.value as DataSource })} className={selectCls}>
                {SOURCES.filter((s) => s.value !== "manual").map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </label>
          </div>
        </>
      )}
    </Card>
  );
}

function BrokerDetails({ status, tokenSavedAt, onChange }: { status: BrokerStatus; tokenSavedAt: string | null; onChange: () => void }) {
  const { info } = status;
  const [values, setValues] = useState<Record<string, string>>({});
  const [test, setTest] = useState<ConnectionTest | null>(null);
  const [sync, setSync] = useState<{ dhan_rows: number; updated: number; mapped: number } | null>(null);
  const act = useAction();
  const isKite = info.id === "kite";
  const isDhan = info.id === "dhan";

  async function save() {
    const filled = Object.fromEntries(
      Object.entries(values)
        .map(([k, v]) => [k, v.trim()])
        .filter(([, v]) => v),
    );
    if (!Object.keys(filled).length) return;
    if (await act.run(() => apiSend(`/api/v1/brokers/${info.id}/credentials`, "PUT", { values: filled }), "Saved (encrypted).")) {
      setValues({});
      onChange();
    }
  }

  return (
    <div className="mt-3 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-sm">{info.description}</p>
        <div className="flex gap-1">
          <StatusPill tone={status.configured ? "good" : "warn"}>{status.configured ? "keys saved" : "not set up"}</StatusPill>
          {status.configured && <StatusPill tone={status.session_active ? "good" : "neutral"}>{status.session_active ? "connected" : "no session"}</StatusPill>}
        </div>
      </div>
      {info.costs && <p className="text-xs text-muted">Cost: {info.costs}</p>}
      {info.login_note && <p className="text-xs text-muted">{info.login_note}</p>}
      {info.docs_url && (
        <a href={info.docs_url} target="_blank" rel="noreferrer" className="text-xs text-accent underline">
          Broker API docs
        </a>
      )}

      <ul className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2" aria-label="What this broker supports">
        {CAPABILITIES.map((c) => {
          const yes = info.capabilities[c.key];
          return (
            <li key={c.key} className="flex items-center gap-2">
              <span aria-hidden className={yes ? "text-good" : "text-bad"}>{yes ? "✓" : "✗"}</span>
              <span className={yes ? "" : "text-muted"}>{c.label}</span>
              <span className="sr-only">{yes ? "(supported)" : "(not supported)"}</span>
            </li>
          );
        })}
      </ul>

      {info.static_ip_required && (
        <Notice>
          Placing real orders needs a static IP registered with the broker (SEBI rule). MarketOS trades paper-only for now; reading prices, positions and history works from anywhere.
        </Notice>
      )}

      {info.fields.length > 0 && (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            {info.fields.map((f) => {
              const st = status.fields.find((s) => s.name === f.name);
              const placeholder = st?.set ? `saved ${st.hint ?? "••••"}` : f.placeholder;
              return (
                <TextField
                  key={f.name}
                  label={f.label}
                  type={f.secret ? "password" : "text"}
                  value={values[f.name] ?? ""}
                  onChange={(v) => setValues((s) => ({ ...s, [f.name]: v }))}
                  placeholder={placeholder}
                  hint={f.help || undefined}
                />
              );
            })}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={save}>Save</Button>
            {status.configured && (
              <Button
                variant="secondary"
                onClick={async () => {
                  if (!confirm(`Remove saved ${info.label} credentials?`)) return;
                  if (await act.run(() => apiSend(`/api/v1/brokers/${info.id}/credentials`, "DELETE"), "Removed.")) {
                    setTest(null);
                    onChange();
                  }
                }}
              >
                Remove
              </Button>
            )}
          </div>
        </>
      )}

      {isKite && <p className="text-sm text-muted">Daily login is in the Zerodha Kite card below.</p>}

      {info.id !== "paper" && (
      <div className="rounded-md border border-border bg-panel-2 p-3 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            disabled={!status.configured}
            onClick={() => act.run(async () => setTest(await apiSend<ConnectionTest>(`/api/v1/brokers/${info.id}/test`, "POST")))}
          >
            Test connection
          </Button>
          <span className="text-xs text-muted">Read-only check. It never places orders.</span>
        </div>
        {test && <TestResult test={test} />}
      </div>
      )}

      {isDhan && (
        <div className="rounded-md border border-border bg-panel-2 p-3 text-sm">
          <p className="mb-2 text-xs text-muted">
            Dhan prices and candles need Dhan’s instrument IDs. Run this after each instrument sync.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              disabled={!status.configured}
              onClick={() =>
                act.run(async () => setSync(await apiSend<{ dhan_rows: number; updated: number; mapped: number }>("/api/v1/brokers/dhan/sync-instruments", "POST")))
              }
            >
              Sync Dhan instrument IDs
            </Button>
            <Button
              variant="secondary"
              disabled={!status.configured}
              onClick={async () => {
                let renewed = false;
                const ok = await act.run(async () => {
                  renewed = (await apiSend<{ renewed: boolean }>("/api/v1/brokers/dhan/renew-token", "POST")).renewed;
                });
                if (ok) {
                  act.setMessage(renewed ? { tone: "ok", text: "Token renewed." } : { tone: "error", text: "Token was not renewed." });
                  onChange();
                }
              }}
            >
              Renew token now
            </Button>
          </div>
          {sync && (
            <p className="mt-2 text-xs">
              Read {formatNumber(sync.dhan_rows, 0)} Dhan rows, updated {formatNumber(sync.updated, 0)}; {formatNumber(sync.mapped, 0)} instruments mapped.
            </p>
          )}
          <p className="mt-2 text-xs text-muted">
            {tokenSavedAt ? `Token saved ${timeAgo(tokenSavedAt)}; renewed automatically every ~20 h.` : "No token saved yet."}
          </p>
        </div>
      )}

      {act.view}
    </div>
  );
}

function TestResult({ test }: { test: ConnectionTest }) {
  return (
    <div className="mt-3 space-y-2">
      {test.ok ? (
        <>
          <p>
            <StatusPill tone="good">connected</StatusPill>{" "}
            Client ID <b>{test.profile?.user_id ?? "—"}</b>
            {test.profile?.name ? ` (${test.profile.name})` : ""}
          </p>
          <p>
            Available funds: <b>{inr(test.funds?.available)}</b>
            {test.funds?.used ? ` · used ${inr(test.funds.used)}` : ""}
          </p>
          <p>Open positions: {test.positions.length}</p>
          {test.positions.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-left text-muted">
                  <tr>
                    <th className="py-1 pr-2 font-medium">Symbol</th>
                    <th className="py-1 pr-2 font-medium">Product</th>
                    <th className="py-1 pr-2 text-right font-medium">Qty</th>
                    <th className="py-1 text-right font-medium">Avg price</th>
                  </tr>
                </thead>
                <tbody>
                  {test.positions.map((p) => (
                    <tr key={`${p.exchange}:${p.tradingsymbol}:${p.product}`} className="border-t border-border">
                      <td className="py-1 pr-2">
                        {p.tradingsymbol} <span className="text-muted">{p.exchange}</span>
                      </td>
                      <td className="py-1 pr-2">{p.product}</td>
                      <td className="py-1 pr-2 text-right tabular-nums">{p.quantity}</td>
                      <td className="py-1 text-right tabular-nums">{inr(p.average_price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : (
        <p role="alert" className="text-bad">{test.error ?? "Connection failed."}</p>
      )}
      {test.notes.length > 0 && (
        <ul className="list-disc pl-5 text-xs text-muted">
          {test.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
