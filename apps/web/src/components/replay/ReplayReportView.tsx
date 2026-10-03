import { Card } from "@/components/ui";
import { formatDateTime, formatNumber, inr, pnlClass } from "@/lib/format";
import type { ReplayBrief, ReplayReport, ReplayRun } from "@/lib/types";
import { BreakdownTable } from "./BreakdownTable";
import { EquityChart } from "./EquityChart";
import { exitLabel, pct, segmentLabel } from "./labels";

function Tile({ label, value, sub, valueClass = "" }: { label: string; value: React.ReactNode; sub?: React.ReactNode; valueClass?: string }) {
  return (
    <div className="rounded-lg border border-border bg-panel p-3">
      <p className="text-xs text-muted">{label}</p>
      <p className={`mt-1 text-lg font-semibold tabular-nums ${valueClass}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-muted">{sub}</p>}
    </div>
  );
}

const SKIPPED = [
  { key: "entry_not_hit", label: "Entry not hit", why: "The entry price was never reached in time." },
  { key: "no_data", label: "No price data", why: "No historical prices for that contract (expired weekly options need Dhan's data plan)." },
  { key: "unresolved", label: "Symbol not found", why: "Couldn't match the symbol to a contract." },
  { key: "incomplete", label: "No stop-loss", why: "The message had no stop-loss." },
] as const;

function TradeList({ title, rows }: { title: string; rows: ReplayBrief[] }) {
  return (
    <Card title={title}>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">None.</p>
      ) : (
        <ul className="divide-y divide-border text-sm">
          {rows.map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-3 py-2">
              <div className="min-w-0">
                <p className="truncate font-medium">{t.symbol ?? "—"}</p>
                <p className="truncate text-xs text-muted">
                  {t.source} · {formatDateTime(t.message_at)} · {exitLabel(t.exit_reason)}
                </p>
              </div>
              <span className={`shrink-0 font-mono tabular-nums ${pnlClass(t.net_pnl)}`}>{inr(t.net_pnl)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

const SETTING_LABELS: Record<string, string> = {
  capital: "capital",
  risk_per_trade_pct: "risk/trade %",
  exit_mode: "exit",
  trail_mode: "trail",
  trail_value: "trail value",
};

function paramsSummary(params: Record<string, unknown>): string {
  const parts: string[] = [];
  const from = typeof params.date_from === "string" ? params.date_from : null;
  const to = typeof params.date_to === "string" ? params.date_to : null;
  if (from) parts.push(from === to || !to ? `Day ${from}` : `${from} to ${to}`);
  const ids = Array.isArray(params.source_ids) ? params.source_ids.length : 0;
  parts.push(ids ? `${ids} group${ids === 1 ? "" : "s"}` : "all groups");
  if (typeof params.messages === "string") parts.push(`messages: ${params.messages}`);
  if (params.use_ai === true) parts.push("AI on");
  if (typeof params.entry_window_minutes === "number") parts.push(`entry window ${params.entry_window_minutes} min`);
  if (params.square_off === false) parts.push("no session-end square-off");
  if (params.same_candle === "target_first") parts.push("target-first on same candle");
  const s = params.settings;
  if (s && typeof s === "object" && !Array.isArray(s)) {
    const entries = Object.entries(s as Record<string, unknown>).filter(([, v]) => v !== null && v !== "");
    parts.push(
      entries.length ? `risk overrides: ${entries.map(([k, v]) => `${SETTING_LABELS[k] ?? k} ${String(v)}`).join(", ")}` : "risk: paper account settings",
    );
  }
  return parts.join(" · ");
}

export function ReplayReportView({ run, report }: { run: ReplayRun; report: ReplayReport }) {
  const o = report.overall;
  const origin = report.message_origin;
  const sources = Object.entries(report.data_sources ?? {});
  const targets = Object.entries(report.targets_hit ?? {});

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
        <Tile label="Trades taken" value={o.traded} sub={`of ${o.signals} signals · ${report.messages_scanned} messages`} />
        <Tile label="Won / lost" value={`${o.wins} / ${o.losses}`} sub={`${o.breakeven} breakeven`} />
        <Tile label="Win rate" value={pct(o.win_rate)} />
        <Tile label="Signal accuracy" value={pct(o.accuracy_t1)} sub="TP1 reached before stop" />
        <Tile label="Net P&L" value={inr(o.net_pnl)} valueClass={pnlClass(o.net_pnl)} sub="after charges" />
        <Tile
          label="Return"
          value={pct(report.return_pct)}
          valueClass={pnlClass(report.return_pct)}
          sub={`${inr(report.capital_start)} → ${inr(report.capital_end)}`}
        />
        <Tile label="Max drawdown" value={inr(report.max_drawdown)} sub={pct(report.max_drawdown_pct)} />
        <Tile label="Profit factor" value={formatNumber(o.profit_factor)} sub="won ₹ ÷ lost ₹" />
        <Tile label="Avg win / avg loss" value={<span className="text-base">{inr(o.avg_win)} / {inr(o.avg_loss)}</span>} />
        <Tile label="Expectancy" value={inr(o.expectancy)} valueClass={pnlClass(o.expectancy)} sub="per trade" />
        <Tile label="Avg R" value={formatNumber(o.avg_r)} sub="profit in units of risk" />
        <Tile label="Max losing streak" value={report.max_consecutive_losses} />
        <Tile label="Avg holding time" value={report.avg_holding_minutes === null ? "—" : `${formatNumber(report.avg_holding_minutes, 0)} min`} />
      </div>

      <Card title="Equity curve">
        <EquityChart curve={report.equity_curve} />
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Didn't trade">
          <ul className="space-y-2 text-sm">
            {SKIPPED.map((s) => (
              <li key={s.key} className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{s.label}</p>
                  <p className="text-xs text-muted">{s.why}</p>
                </div>
                <span className="font-mono tabular-nums">{o[s.key]}</span>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Targets hit">
          {targets.length === 0 ? (
            <p className="text-sm text-muted">No target was reached.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th scope="col" className="py-1 font-medium">Target</th>
                  <th scope="col" className="py-1 text-right font-medium">Trades</th>
                  <th scope="col" className="py-1 text-right font-medium">Of trades taken</th>
                </tr>
              </thead>
              <tbody>
                {targets.map(([k, v]) => (
                  <tr key={k} className="border-t border-border">
                    <th scope="row" className="py-1.5 text-left font-medium">{k}</th>
                    <td className="py-1.5 text-right font-mono tabular-nums">{v.count}</td>
                    <td className="py-1.5 text-right font-mono tabular-nums">{pct(v.pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <div className="space-y-4">
        <BreakdownTable title="By group" nameHeader="Group" rows={report.by_source} sort="pnl" />
        <BreakdownTable title="Equity / F&O / Commodity" nameHeader="Segment" rows={report.by_segment} label={segmentLabel} />
        <div className="grid gap-4 xl:grid-cols-2">
          <BreakdownTable title="By exit reason" nameHeader="Exit" rows={report.by_exit_reason} label={exitLabel} />
          <BreakdownTable title="Buy vs sell" nameHeader="Side" rows={report.by_side} />
          <BreakdownTable title="By day" nameHeader="Day" rows={report.by_day} />
          <BreakdownTable title="By hour (IST)" nameHeader="Hour" rows={report.by_hour} />
        </div>
        <BreakdownTable title="By underlying" nameHeader="Underlying" rows={report.by_underlying} sort="traded" limit={15} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <TradeList title="Best trades" rows={report.best_trades ?? []} />
        <TradeList title="Worst trades" rows={report.worst_trades ?? []} />
      </div>

      <p className="text-xs text-muted">
        Messages from: {origin === "telegram" ? "Telegram history" : origin === "stored" ? "messages MarketOS stored" : origin ?? "—"}
        {" · "}Prices from: {sources.length ? sources.map(([k, v]) => `${k} (${v})`).join(", ") : "—"}
        {" · "}
        {paramsSummary(run.params)}
        {" · "}Report made {formatDateTime(report.generated_at)}
      </p>
    </div>
  );
}
