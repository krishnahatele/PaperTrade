"use client";

import { useState } from "react";
import { Button, TextField, Toggle, useAction } from "@/components/forms";
import { Card } from "@/components/ui";
import { apiSend } from "@/lib/api";
import type { TradingRuntime } from "@/lib/types";

export function TradingCard({ trading, liveAllowed, onChange }: { trading: TradingRuntime; liveAllowed: boolean; onChange: () => void }) {
  const act = useAction();
  const [minConf, setMinConf] = useState(trading.min_confidence);
  const [ttl, setTtl] = useState(String(trading.signal_ttl_minutes));

  const patch = (changes: Partial<TradingRuntime>) =>
    act.run(() => apiSend("/api/v1/settings/trading", "PATCH", changes), "Saved.").then(onChange);

  return (
    <Card title="Trading controls">
      <div className="divide-y divide-border">
        <Toggle label="Kill switch" description="Immediately blocks all new orders, paper and live." checked={trading.kill_switch} onChange={(v) => patch({ kill_switch: v })} danger />
        <Toggle label="Auto-execute signals" description="Place orders automatically for validated signals on accounts that allow it." checked={trading.auto_execute} onChange={(v) => patch({ auto_execute: v })} />
        <Toggle
          label="Live trading armed"
          description={liveAllowed ? "Allows orders on LIVE accounts. Real money." : "Disabled by the server (MARKETOS_LIVE_TRADING_ENABLED=false)."}
          checked={trading.live_armed}
          disabled={!liveAllowed && !trading.live_armed}
          onChange={(v) => {
            if (v && !confirm("Arm LIVE trading? Orders on live accounts will use real money.")) return;
            void patch({ live_armed: v });
          }}
          danger
        />
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <TextField label="Minimum confidence (0–1)" value={minConf} onChange={setMinConf} inputMode="decimal" hint="Signals below this are not auto-executed." />
        <TextField label="Signal expiry (minutes)" value={ttl} onChange={setTtl} inputMode="numeric" hint="Unexecuted signals expire after this." />
      </div>
      <div className="mt-3 flex items-center gap-2">
        <Button onClick={() => patch({ min_confidence: minConf, signal_ttl_minutes: Number(ttl) })}>Save</Button>
        {act.view}
      </div>
    </Card>
  );
}
