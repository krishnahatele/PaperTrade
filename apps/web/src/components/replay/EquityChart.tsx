"use client";

import { useEffect, useRef, useState } from "react";
import { formatDateTime, inr, pnlClass } from "@/lib/format";
import type { ReplayReport } from "@/lib/types";

type Point = ReplayReport["equity_curve"][number];

const HEIGHT = 240;
const M = { top: 12, right: 16, bottom: 28, left: 76 };

function niceTicks(min: number, max: number, count = 4): number[] {
  if (min === max) {
    const pad = Math.max(Math.abs(min) * 0.01, 1);
    min -= pad;
    max += pad;
  }
  const raw = (max - min) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const start = Math.floor(min / step) * step;
  const end = Math.ceil(max / step) * step;
  const out: number[] = [];
  for (let v = start; v <= end + step / 2; v += step) out.push(Number(v.toFixed(6)));
  return out;
}

function compactInr(v: number): string {
  const a = Math.abs(v);
  const sign = v < 0 ? "−" : "";
  if (a >= 1e7) return `${sign}₹${(a / 1e7).toLocaleString("en-IN", { maximumFractionDigits: 2 })} Cr`;
  if (a >= 1e5) return `${sign}₹${(a / 1e5).toLocaleString("en-IN", { maximumFractionDigits: 2 })} L`;
  return `${sign}₹${a.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function shortTime(t: string | null): string {
  if (!t) return "Start";
  const d = new Date(t);
  return d.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** Equity after each closed trade (exit order). Single series: accent line, no legend. */
export function EquityChart({ curve }: { curve: Point[] }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [hover, setHover] = useState<number | null>(null);
  const [showTable, setShowTable] = useState(false);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) setWidth(Math.max(280, Math.round(w)));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const values = curve.map((p) => Number(p.equity));
  const n = values.length;
  const ticks = niceTicks(Math.min(...values), Math.max(...values));
  const yMin = ticks[0];
  const yMax = ticks[ticks.length - 1];
  const innerW = width - M.left - M.right;
  const innerH = HEIGHT - M.top - M.bottom;
  const x = (i: number) => M.left + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const y = (v: number) => M.top + innerH - ((v - yMin) / (yMax - yMin || 1)) * innerH;
  const path = values.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const start = values[0] ?? 0;

  function indexAt(clientX: number, rect: DOMRect): number {
    const rel = ((clientX - rect.left) / rect.width) * width - M.left;
    const i = Math.round((rel / innerW) * (n - 1));
    return Math.min(n - 1, Math.max(0, i));
  }

  function onKey(e: React.KeyboardEvent<SVGSVGElement>) {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      const d = e.key === "ArrowRight" ? 1 : -1;
      setHover((h) => Math.min(n - 1, Math.max(0, (h ?? (d > 0 ? -1 : n)) + d)));
    } else if (e.key === "Home") setHover(0);
    else if (e.key === "End") setHover(n - 1);
    else if (e.key === "Escape") setHover(null);
  }

  const hp = hover !== null ? curve[hover] : null;
  const hv = hover !== null ? values[hover] : null;
  const tipLeft = hover !== null ? Math.min(Math.max(x(hover) + 10, 0), width - 180) : 0;

  return (
    <div ref={wrap}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs text-muted">Account value after each closed trade (in exit order). Dashed line = starting capital.</p>
        <button type="button" onClick={() => setShowTable((s) => !s)} className="shrink-0 rounded border border-border px-2 py-1 text-xs" aria-pressed={showTable}>
          {showTable ? "Show chart" : "Show table"}
        </button>
      </div>
      {n < 2 ? (
        <p className="py-6 text-center text-sm text-muted">No closed trades, so there is no equity curve.</p>
      ) : showTable ? (
        <div className="max-h-80 overflow-auto rounded border border-border">
          <table className="w-full text-sm">
            <caption className="sr-only">Equity after each trade</caption>
            <thead className="sticky top-0 bg-panel-2 text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">#</th>
                <th scope="col" className="px-3 py-2 font-medium">Time</th>
                <th scope="col" className="px-3 py-2 font-medium">Symbol</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Trade P&amp;L</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Equity</th>
              </tr>
            </thead>
            <tbody>
              {curve.map((p, i) => {
                const delta = i === 0 ? null : values[i] - values[i - 1];
                return (
                  <tr key={i} className="border-t border-border">
                    <td className="px-3 py-1.5 font-mono tabular-nums text-muted">{i}</td>
                    <td className="whitespace-nowrap px-3 py-1.5">{p.t ? formatDateTime(p.t) : "Start"}</td>
                    <td className="px-3 py-1.5">{p.symbol ?? "—"}</td>
                    <td className={`px-3 py-1.5 text-right font-mono tabular-nums ${pnlClass(delta)}`}>{delta === null ? "—" : inr(delta.toFixed(2))}</td>
                    <td className="px-3 py-1.5 text-right font-mono tabular-nums">{inr(p.equity)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative w-full">
          <svg
            width={width}
            height={HEIGHT}
            viewBox={`0 0 ${width} ${HEIGHT}`}
            className="block max-w-full touch-none outline-none focus-visible:ring-2 focus-visible:ring-accent"
            role="img"
            aria-label={`Equity curve: ${inr(curve[0].equity)} to ${inr(curve[n - 1].equity)} over ${n - 1} trades. Use arrow keys to read each point.`}
            tabIndex={0}
            onKeyDown={onKey}
            onBlur={() => setHover(null)}
            onPointerMove={(e) => setHover(indexAt(e.clientX, e.currentTarget.getBoundingClientRect()))}
            onPointerLeave={() => setHover(null)}
          >
            {ticks.map((t) => (
              <g key={t}>
                <line x1={M.left} x2={width - M.right} y1={y(t)} y2={y(t)} stroke="var(--border)" strokeWidth={1} />
                <text x={M.left - 8} y={y(t)} textAnchor="end" dominantBaseline="middle" fontSize={11} fill="var(--muted)">
                  {compactInr(t)}
                </text>
              </g>
            ))}
            <line x1={M.left} x2={width - M.right} y1={y(start)} y2={y(start)} stroke="var(--muted)" strokeWidth={1} strokeDasharray="4 4" opacity={0.6} />
            <text x={M.left} y={HEIGHT - 8} fontSize={11} fill="var(--muted)">{shortTime(curve[1].t)}</text>
            <text x={width - M.right} y={HEIGHT - 8} textAnchor="end" fontSize={11} fill="var(--muted)">{shortTime(curve[n - 1].t)}</text>
            <path d={path} fill="none" stroke="var(--accent)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
            {hover === null && (
              <circle cx={x(n - 1)} cy={y(values[n - 1])} r={4} fill="var(--accent)" stroke="var(--panel)" strokeWidth={2} />
            )}
            {hover !== null && hv !== null && (
              <g pointerEvents="none">
                <line x1={x(hover)} x2={x(hover)} y1={M.top} y2={M.top + innerH} stroke="var(--muted)" strokeWidth={1} />
                <circle cx={x(hover)} cy={y(hv)} r={4.5} fill="var(--accent)" stroke="var(--panel)" strokeWidth={2} />
              </g>
            )}
          </svg>
          {hp && hv !== null && hover !== null && (
            <div
              role="status"
              className="pointer-events-none absolute z-10 w-[170px] rounded-md border border-border bg-panel px-2.5 py-1.5 text-xs shadow-md"
              style={{ left: tipLeft, top: Math.max(0, y(hv) - 64) }}
            >
              <p className="font-mono text-sm font-semibold tabular-nums text-text">{inr(hp.equity)}</p>
              <p className="text-muted">{hp.t ? formatDateTime(hp.t) : "Starting capital"}</p>
              {hp.symbol && <p className="truncate text-muted">after {hp.symbol}</p>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
