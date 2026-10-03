"use client";

import { useState } from "react";
import { Button, TextField, Toggle, useAction } from "@/components/forms";
import { StatusPill } from "@/components/StatusPill";
import { Card, Notice } from "@/components/ui";
import { apiSend } from "@/lib/api";
import type { BotNotify, BotStatus } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const NOTIFY: { key: keyof BotNotify; label: string; description: string }[] = [
  { key: "signals", label: "New signals", description: "A message with ⚡ Buy now / ✖ Cancel buttons." },
  { key: "trades", label: "Trade updates", description: "Entries, targets, stop-loss hits and exits." },
  { key: "skipped", label: "Skipped signals", description: "Signals that were not traded, with the reason." },
  { key: "news", label: "News alerts", description: "Headlines that match your keywords." },
  { key: "market_moves", label: "Market-move alerts", description: "Sharp moves in the instruments you watch." },
];

export function BotCard() {
  const status = useApi<BotStatus>("/api/v1/bot");
  const [token, setToken] = useState("");
  const [link, setLink] = useState<{ code: string; url: string } | null>(null);
  const act = useAction();
  const bot = status.data;

  async function saveToken() {
    if (!token.trim()) return;
    if (await act.run(() => apiSend("/api/v1/bot/token", "PUT", { token: token.trim() }), "Bot saved.")) {
      setToken("");
      status.reload();
    }
  }

  return (
    <Card title="Telegram bot (alerts & buttons)">
      <div className="mb-3 flex items-start justify-between gap-2">
        <p className="text-sm">
          Your own bot sends new trades with ⚡ Buy now / ✖ Cancel, open trades with Exit 1 lot / Exit all / SL → cost, a pinned status message,
          and a 🛑 EXIT ALL button (asks twice). Only your own chat is obeyed.
        </p>
        {bot && (
          <StatusPill tone={bot.linked ? "good" : bot.configured ? "warn" : "neutral"}>
            {bot.linked ? "linked" : bot.configured ? (bot.running ? "running" : "not running") : "not set up"}
          </StatusPill>
        )}
      </div>

      {status.error && <Notice tone="error">{status.error}</Notice>}
      {!bot && !status.error && <p className="text-sm text-muted">Loading…</p>}

      {bot && !bot.configured && (
        <div className="space-y-3">
          <div className="rounded-md border border-border bg-panel-2 p-3 text-sm">
            <p className="mb-2">
              <b>Option A:</b> we create the bot for you through @BotFather using your Telegram login (log in to Telegram above first).
            </p>
            <Button onClick={() => act.run(() => apiSend<BotStatus>("/api/v1/bot/create", "POST"), "Bot created.").then(status.reload)}>
              Create my bot automatically
            </Button>
          </div>
          <div className="rounded-md border border-border bg-panel-2 p-3 text-sm">
            <p className="mb-2">
              <b>Option B:</b> paste a bot token you made yourself.
            </p>
            <div className="flex flex-wrap items-end gap-2">
              <div className="min-w-56 flex-1">
                <TextField label="Bot token" type="password" value={token} onChange={setToken} placeholder="123456:ABC-…" hint="From @BotFather → /newbot" />
              </div>
              <Button disabled={!token.trim()} onClick={saveToken}>Save</Button>
            </div>
          </div>
        </div>
      )}

      {bot?.configured && !bot.linked && (
        <div className="rounded-md border border-border bg-panel-2 p-3 text-sm">
          <p className="mb-2">
            Bot {bot.username ? <b>@{bot.username}</b> : "saved"}. Now link it to your Telegram so it knows where to send alerts.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={() => act.run(async () => setLink(await apiSend<{ code: string; url: string }>("/api/v1/bot/link", "POST")))}>
              Link my Telegram
            </Button>
            {link && (
              <Button variant="secondary" onClick={status.reload}>
                Check
              </Button>
            )}
          </div>
          {link && (
            <p className="mt-2">
              <a href={link.url} target="_blank" rel="noreferrer" className="text-accent underline">
                Open {link.url.replace(/^https?:\/\//, "")} and press Start
              </a>
              <span className="block text-xs text-muted">
                Code: <code>{link.code}</code>. Then press Check.
              </span>
            </p>
          )}
        </div>
      )}

      {bot?.linked && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <StatusPill tone="good">
            Linked to {bot.owner_name ?? "you"}
            {bot.username ? ` via @${bot.username}` : ""}
          </StatusPill>
          <Button variant="secondary" onClick={() => act.run(() => apiSend("/api/v1/bot/test", "POST"), "Test message sent.")}>
            Send test message
          </Button>
          <Button
            variant="secondary"
            onClick={async () => {
              if (!confirm("Unlink your Telegram from the bot? Alerts stop until you link again.")) return;
              if (await act.run(() => apiSend("/api/v1/bot/unlink", "POST"), "Unlinked.")) {
                setLink(null);
                status.reload();
              }
            }}
          >
            Unlink
          </Button>
        </div>
      )}

      {bot?.configured && (
        <>
          <div className="mt-3 divide-y divide-border">
            {NOTIFY.map((n) => (
              <Toggle
                key={n.key}
                label={n.label}
                description={n.description}
                checked={bot.notify[n.key]}
                onChange={(v) => act.run(() => apiSend("/api/v1/bot/notify", "PATCH", { ...bot.notify, [n.key]: v })).then(status.reload)}
              />
            ))}
          </div>
          <div className="mt-3">
            <Button
              variant="danger"
              onClick={async () => {
                if (!confirm("Remove the bot token? The bot stops sending alerts.")) return;
                if (await act.run(() => apiSend("/api/v1/bot/token", "DELETE"), "Bot removed.")) {
                  setLink(null);
                  status.reload();
                }
              }}
            >
              Remove bot
            </Button>
          </div>
        </>
      )}

      {bot?.last_error && <p className="mt-2 text-sm text-bad">{bot.last_error}</p>}
      {act.view && <div className="mt-2">{act.view}</div>}
    </Card>
  );
}
