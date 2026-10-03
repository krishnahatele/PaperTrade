import { formatNumber, inr, pnlClass } from "@/lib/format";
import type { ReplayStats } from "@/lib/types";
import { pct } from "./labels";

/** One table per breakdown (by group, segment, exit reason, ...). */
export function BreakdownTable({
  title,
  rows,
  nameHeader = "Name",
  label,
  sort,
  limit,
}: {
  title: string;
  rows: Record<string, ReplayStats> | undefined;
  nameHeader?: string;
  label?: (key: string) => string;
  sort?: "pnl" | "traded";
  limit?: number;
}) {
  let entries = Object.entries(rows ?? {});
  if (sort === "pnl") entries.sort((a, b) => Number(b[1].net_pnl) - Number(a[1].net_pnl));
  if (sort === "traded") entries.sort((a, b) => b[1].traded - a[1].traded);
  const total = entries.length;
  if (limit) entries = entries.slice(0, limit);

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-panel">
      <h3 className="px-4 pt-3 text-sm font-medium text-muted">
        {title}
        {limit && total > limit && <span className="font-normal"> (top {limit} of {total})</span>}
      </h3>
      {entries.length === 0 ? (
        <p className="px-4 py-3 text-sm text-muted">Nothing to show.</p>
      ) : (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-panel-2 text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">{nameHeader}</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Signals</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Traded</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Won</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Lost</th>
                <th scope="col" className="whitespace-nowrap px-3 py-2 text-right font-medium">Win rate</th>
                <th scope="col" className="whitespace-nowrap px-3 py-2 text-right font-medium" title="TP1 reached before stop">Accuracy (TP1)</th>
                <th scope="col" className="whitespace-nowrap px-3 py-2 text-right font-medium">Net P&amp;L</th>
                <th scope="col" className="whitespace-nowrap px-3 py-2 text-right font-medium">Profit factor</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(([k, s]) => (
                <tr key={k} className="border-t border-border">
                  <th scope="row" className="max-w-[16rem] truncate px-3 py-2 text-left font-medium" title={k}>{label ? label(k) : k}</th>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">{s.signals}</td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">{s.traded}</td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">{s.wins}</td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">{s.losses}</td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">{pct(s.win_rate)}</td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">{pct(s.accuracy_t1)}</td>
                  <td className={`whitespace-nowrap px-3 py-2 text-right font-mono tabular-nums ${pnlClass(s.net_pnl)}`}>{inr(s.net_pnl)}</td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">{formatNumber(s.profit_factor)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
