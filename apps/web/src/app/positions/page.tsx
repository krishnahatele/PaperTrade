"use client";

import { StatusPill } from "@/components/StatusPill";
import { Notice, PageHeader } from "@/components/ui";
import { formatNumber, inr, pnlClass } from "@/lib/format";
import type { PositionView } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function PositionsPage() {
  const pos = useApi<PositionView[]>("/api/v1/portfolio/positions", 3000);
  return (
    <>
      <PageHeader title="Positions" description="Open holdings with live P&L (refreshes every few seconds)." />
      {pos.error && <Notice tone="error">{pos.error}</Notice>}
      <div className="overflow-x-auto rounded-lg border border-border bg-panel">
        <table className="w-full text-sm">
          <thead className="bg-panel-2 text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              {["Instrument", "Product", "Qty", "Avg", "LTP", "Unrealized", "Realized"].map((h, i) => (
                <th key={h} className={`px-3 py-2 font-medium ${i >= 2 ? "text-right" : ""}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pos.data?.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-6 text-center text-muted">No open positions.</td></tr>
            )}
            {pos.data?.map((p) => (
              <tr key={p.id} className="border-t border-border">
                <td className="px-3 py-2 font-medium">{p.tradingsymbol}</td>
                <td className="px-3 py-2"><StatusPill>{p.product}</StatusPill></td>
                <td className={`px-3 py-2 text-right font-mono ${p.quantity < 0 ? "text-bad" : ""}`}>{p.quantity}</td>
                <td className="px-3 py-2 text-right font-mono">{formatNumber(p.average_price)}</td>
                <td className="px-3 py-2 text-right font-mono">{formatNumber(p.ltp)}</td>
                <td className={`px-3 py-2 text-right font-mono ${pnlClass(p.unrealized_pnl)}`}>{inr(p.unrealized_pnl)}</td>
                <td className={`px-3 py-2 text-right font-mono ${pnlClass(p.realized_pnl)}`}>{inr(p.realized_pnl)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
