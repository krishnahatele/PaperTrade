"use client";

import { Notice } from "@/components/ui";
import { formatNumber } from "@/lib/format";
import type { WatchState } from "@/lib/types";
import { useApi } from "@/lib/useApi";

/** Live tiles for the instruments watched for big moves. Refreshes every minute. */
export function WatchTiles() {
  const { data, error } = useApi<WatchState[]>("/api/v1/market/watch", 60_000);

  if (error) return <Notice tone="error">Could not load market watch: {error}</Notice>;
  if (!data) return <p className="text-sm text-muted">Loading market watch…</p>;
  if (data.length === 0) {
    return <p className="text-sm text-muted">No instruments watched. Add some in Settings → News &amp; market alerts.</p>;
  }

  return (
    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5" aria-label="Market watch">
      {data.map((w) => (
        <li key={w.symbol} className="rounded-lg border border-border bg-panel p-3">
          <p className="truncate text-xs text-muted" title={w.tradingsymbol ?? w.symbol}>{w.label}</p>
          <WatchBody w={w} />
        </li>
      ))}
    </ul>
  );
}

function WatchBody({ w }: { w: WatchState }) {
  if (!w.tradingsymbol) return <p className="mt-1 text-xs text-warn">not found — sync instruments</p>;
  if (w.ltp === null) return <p className="mt-1 text-xs text-muted">no price (log in to Kite / connect Dhan)</p>;
  const ch = w.change_pct === null ? null : Number(w.change_pct);
  return (
    <>
      <p className="mt-1 font-mono text-lg font-semibold tabular-nums">{formatNumber(w.ltp)}</p>
      {ch === null || Number.isNaN(ch) ? (
        <p className="text-xs text-muted">change not known yet</p>
      ) : (
        <p className={`text-xs font-medium ${ch > 0 ? "text-good" : ch < 0 ? "text-bad" : "text-muted"}`}>
          <span aria-hidden="true">{ch > 0 ? "▲" : ch < 0 ? "▼" : "•"}</span> {ch > 0 ? "+" : ""}
          {formatNumber(ch)}% <span className="font-normal text-muted">in {w.window_minutes} min</span>
        </p>
      )}
    </>
  );
}
