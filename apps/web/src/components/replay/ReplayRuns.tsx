"use client";

import Link from "next/link";
import { useEffect } from "react";
import { Button } from "@/components/forms";
import { StatusPill } from "@/components/StatusPill";
import { Notice } from "@/components/ui";
import { apiSend } from "@/lib/api";
import { formatDateTime, inr, pnlClass } from "@/lib/format";
import type { ReplayRunBrief } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { isActive, pct, statusTone } from "./labels";

export function ReplayRuns() {
  const runsApi = useApi<ReplayRunBrief[]>("/api/v1/replays");
  const { reload } = runsApi;
  const busy = (runsApi.data ?? []).some((r) => isActive(r.status));
  // Poll every 3 s only while something is queued or running.
  useEffect(() => {
    if (!busy) return;
    const id = setInterval(reload, 3000);
    return () => clearInterval(id);
  }, [busy, reload]);
  const runs = runsApi.data;

  async function remove(r: ReplayRunBrief) {
    if (!confirm(`Delete replay “${r.name}”? Its report and trades are removed.`)) return;
    try {
      await apiSend(`/api/v1/replays/${r.id}`, "DELETE");
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
    reload();
  }

  if (runsApi.error) return <Notice tone="error">Could not load replays: {runsApi.error}</Notice>;
  if (!runs) return <p className="text-sm text-muted">Loading…</p>;
  if (runs.length === 0) return <p className="text-sm text-muted">No replays yet. Run one above.</p>;

  return (
    <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-panel">
      {runs.map((r) => {
        const o = r.overall;
        return (
          <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <Link href={`/replay/${r.id}`} className="font-medium text-accent hover:underline">{r.name || "Replay"}</Link>
                <StatusPill tone={statusTone(r.status)}>{r.status}</StatusPill>
              </div>
              <p className="mt-0.5 text-xs text-muted">
                {formatDateTime(r.created_at)}
                {r.progress.messages !== undefined && ` · ${r.progress.done ?? 0}/${r.progress.messages} messages`}
                {isActive(r.status) && r.progress.stage && ` · ${r.progress.stage}`}
              </p>
              {r.status === "failed" && r.error && <p className="mt-1 text-xs text-bad">{r.error}</p>}
            </div>
            <div className="flex items-center gap-4">
              {r.status === "done" && o && (
                <dl className="flex gap-4 text-right text-xs">
                  <div>
                    <dt className="text-muted">Traded</dt>
                    <dd className="font-mono tabular-nums">{o.traded}</dd>
                  </div>
                  <div>
                    <dt className="text-muted">Win rate</dt>
                    <dd className="font-mono tabular-nums">{pct(o.win_rate)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted">Net P&amp;L</dt>
                    <dd className={`font-mono tabular-nums ${pnlClass(o.net_pnl)}`}>{inr(o.net_pnl)}</dd>
                  </div>
                </dl>
              )}
              <Button variant="secondary" onClick={() => remove(r)}>Delete</Button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
