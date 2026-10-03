"use client";

import { useState } from "react";
import { Button, useAction } from "@/components/forms";
import { StatusPill } from "@/components/StatusPill";
import { Card } from "@/components/ui";
import { apiSend } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import type { ParsePreview } from "@/lib/types";

export function ParserPlayground() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<ParsePreview | null>(null);
  const act = useAction();

  return (
    <Card title="Try the parser">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        placeholder="Paste a Telegram message, e.g. BUY NIFTY 24500 CE ABOVE 120 SL 100 TGT 140/160"
        className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
      />
      <div className="mt-2 flex items-center gap-2">
        <Button
          onClick={() =>
            act.run(async () => setResult(await apiSend<ParsePreview>("/api/v1/signals/parse-preview", "POST", { text })))
          }
          disabled={!text.trim()}
        >
          Parse
        </Button>
        <span className="text-xs text-muted">Nothing is saved.</span>
        {act.view}
      </div>
      {result && (
        <div className="mt-3 rounded-md border border-border bg-panel-2 p-3 text-sm">
          {!result.is_signal ? (
            <p>
              <StatusPill tone="neutral">not a signal</StatusPill> <span className="text-muted">{result.reason}</span>
            </p>
          ) : (
            <dl className="grid grid-cols-[8rem_1fr] gap-y-1">
              <dt className="text-muted">Instrument</dt>
              <dd>
                <span className="font-medium">{result.side} {result.symbol_text}</span>{" "}
                {result.instrument_tradingsymbol ? (
                  <StatusPill tone="good">{result.instrument_tradingsymbol}</StatusPill>
                ) : (
                  <StatusPill tone="warn">not in instrument list</StatusPill>
                )}
              </dd>
              <dt className="text-muted">Entry</dt>
              <dd className="font-mono">{result.entry_low === result.entry_high ? formatNumber(result.entry_low) : `${formatNumber(result.entry_low)} – ${formatNumber(result.entry_high)}`}</dd>
              <dt className="text-muted">Stop loss</dt>
              <dd className="font-mono">{formatNumber(result.stop_loss)}</dd>
              <dt className="text-muted">Targets</dt>
              <dd className="font-mono">{result.targets.map((t) => formatNumber(t)).join(", ") || "—"}</dd>
              <dt className="text-muted">Confidence</dt>
              <dd>
                {Math.round(Number(result.confidence) * 100)}% <span className="text-xs text-muted">via {result.parser === "llm" ? "AI" : "rules"}</span>
              </dd>
            </dl>
          )}
          {result.warnings.length > 0 && <p className="mt-2 text-xs text-warn">⚠ {result.warnings.join(" · ")}</p>}
          {result.llm_error && <p className="mt-1 text-xs text-bad">AI parser: {result.llm_error}</p>}
        </div>
      )}
    </Card>
  );
}
