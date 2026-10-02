"use client";

import { useState } from "react";
import { Button, TextField, useAction } from "@/components/forms";
import { StatusPill } from "@/components/StatusPill";
import { Card } from "@/components/ui";
import { apiSend } from "@/lib/api";
import type { Integrations } from "@/lib/types";
import { SecretStatus } from "./SecretStatus";

export function KiteCard({ data, onChange }: { data: Integrations["kite"]; onChange: () => void }) {
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const save = useAction();

  async function submit() {
    const body: Record<string, string> = {};
    if (apiKey) body.api_key = apiKey.trim();
    if (apiSecret) body.api_secret = apiSecret.trim();
    if (!Object.keys(body).length) return;
    if (await save.run(() => apiSend("/api/v1/integrations/kite", "PUT", body), "Saved (encrypted).")) {
      setApiKey("");
      setApiSecret("");
      onChange();
    }
  }

  return (
    <Card title="Zerodha Kite">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm">Market data, instrument list and (optionally) live order routing.</p>
        <StatusPill tone={data.session_active ? "good" : "warn"}>{data.session_active ? `session · ${data.user_id ?? ""}` : "no session"}</StatusPill>
      </div>
      <div className="space-y-1.5">
        <SecretStatus label="API key" field={data.api_key} />
        <SecretStatus label="API secret" field={data.api_secret} />
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <TextField label="API key" value={apiKey} onChange={setApiKey} placeholder={data.api_key.set ? "unchanged" : "from developers.kite.trade"} />
        <TextField label="API secret" value={apiSecret} onChange={setApiSecret} type="password" placeholder={data.api_secret.set ? "unchanged" : ""} />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button onClick={submit}>Save</Button>
        <Button
          variant="secondary"
          onClick={async () => {
            if (!confirm("Remove Kite credentials and session?")) return;
            if (await save.run(() => apiSend("/api/v1/integrations/kite", "DELETE"), "Removed.")) onChange();
          }}
        >
          Remove
        </Button>
        {save.view}
      </div>
    </Card>
  );
}
