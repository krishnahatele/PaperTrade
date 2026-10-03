"use client";

import { useState } from "react";
import { DataTable } from "@/components/DataTable";
import { Button, Toggle, useAction } from "@/components/forms";
import { StatusPill } from "@/components/StatusPill";
import { apiSend } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { NewsItem } from "@/lib/types";

type RefreshResult = { fetched: number; new: number; alerts: number };

export function HeadlinesTab() {
  const [draft, setDraft] = useState("");
  const [q, setQ] = useState("");
  const [matchedOnly, setMatchedOnly] = useState(false);
  const [version, setVersion] = useState(0);
  const act = useAction();

  async function fetchNow() {
    act.setMessage(null);
    try {
      const r = await apiSend<RefreshResult>("/api/v1/news/refresh", "POST");
      act.setMessage({ tone: "ok", text: `Checked ${r.fetched} headlines: ${r.new} new, ${r.alerts} alerts.` });
    } catch (e) {
      act.setMessage({ tone: "error", text: e instanceof Error ? e.message : String(e) });
    }
    setVersion((v) => v + 1);
  }

  let query = "";
  if (q) query += `&q=${encodeURIComponent(q)}`;
  if (matchedOnly) query += "&matched_only=true";

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <form
          role="search"
          className="flex min-w-0 flex-1 gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setQ(draft.trim());
          }}
        >
          <label className="min-w-0 flex-1 text-sm">
            <span className="sr-only">Search headlines</span>
            <input
              type="search"
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                if (e.target.value === "") setQ("");
              }}
              placeholder="Search headlines (e.g. RBI, Reliance)"
              maxLength={100}
              className="w-full rounded-md border border-border bg-bg px-3 py-1.5 outline-none focus:border-accent"
            />
          </label>
          <Button type="submit" variant="secondary">Search</Button>
        </form>
        <Button onClick={fetchNow}>Fetch now</Button>
      </div>
      <div className="max-w-md">
        <Toggle label="Only headlines with my keywords" checked={matchedOnly} onChange={setMatchedOnly} />
      </div>
      {act.view}
      <DataTable<NewsItem>
        key={`${query}:${version}`}
        path="/api/v1/news"
        query={query}
        emptyText={q || matchedOnly ? "No headlines match." : "No headlines yet. Press “Fetch now” or check your feeds in Settings."}
        columns={[
          {
            key: "title",
            header: "Headline",
            render: (n) => (
              <div className="max-w-2xl whitespace-normal">
                <a href={n.url} target="_blank" rel="noreferrer" className="font-medium text-accent hover:underline">{n.title}</a>
                {n.matched.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1" aria-label="Matched keywords">
                    {n.matched.map((k) => (
                      <StatusPill key={k} tone="accent">{k}</StatusPill>
                    ))}
                  </div>
                )}
              </div>
            ),
          },
          {
            key: "dir",
            header: "Tone",
            render: (n) =>
              n.direction === "up" ? (
                <span className="text-good">▲ up</span>
              ) : n.direction === "down" ? (
                <span className="text-bad">▼ down</span>
              ) : (
                <span className="text-muted">—</span>
              ),
          },
          { key: "src", header: "Source", render: (n) => <span className="text-xs text-muted">{n.source}</span> },
          { key: "at", header: "Published", render: (n) => <span className="text-xs text-muted">{formatDateTime(n.published_at)}</span> },
        ]}
      />
    </div>
  );
}
