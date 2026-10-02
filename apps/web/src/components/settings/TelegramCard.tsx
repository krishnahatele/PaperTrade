"use client";

import { useState } from "react";
import { Button, TextField, useAction } from "@/components/forms";
import { StatusPill } from "@/components/StatusPill";
import { Card } from "@/components/ui";
import { apiSend } from "@/lib/api";
import type { Integrations } from "@/lib/types";
import { SecretStatus } from "./SecretStatus";

export function TelegramCard({ data, onChange }: { data: Integrations["telegram"]; onChange: () => void }) {
  const [apiId, setApiId] = useState("");
  const [apiHash, setApiHash] = useState("");
  const [phone, setPhone] = useState("");
  const save = useAction();

  async function submit() {
    const body: Record<string, string> = {};
    if (apiId) body.api_id = apiId.trim();
    if (apiHash) body.api_hash = apiHash.trim();
    if (phone) body.phone = phone.replace(/\s/g, "");
    if (!Object.keys(body).length) return;
    const ok = await save.run(() => apiSend("/api/v1/integrations/telegram", "PUT", body), "Saved (encrypted).");
    if (ok) {
      setApiId("");
      setApiHash("");
      setPhone("");
      onChange();
    }
  }

  return (
    <Card title="Telegram">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm">Reads signals from your Telegram channels using your own account.</p>
        <StatusPill tone={data.authorized ? "good" : "warn"}>{data.authorized ? "logged in" : "not logged in"}</StatusPill>
      </div>
      <div className="space-y-1.5">
        <SecretStatus label="API ID" field={data.api_id} />
        <SecretStatus label="API hash" field={data.api_hash} />
        <SecretStatus label="Phone number" field={data.phone} />
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <TextField label="API ID" value={apiId} onChange={setApiId} inputMode="numeric" placeholder={data.api_id.set ? "unchanged" : "1234567"} />
        <TextField label="API hash" value={apiHash} onChange={setApiHash} type="password" placeholder={data.api_hash.set ? "unchanged" : "32 hex characters"} />
        <TextField label="Phone number" value={phone} onChange={setPhone} type="tel" placeholder={data.phone.set ? "unchanged" : "+919876543210"} />
      </div>
      <p className="mt-2 text-xs text-muted">
        Get the API ID and hash at my.telegram.org → API development tools. Values are encrypted at rest and never shown again.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button onClick={submit}>Save</Button>
        <Button
          variant="secondary"
          onClick={async () => {
            if (!confirm("Remove all Telegram credentials and log out?")) return;
            if (await save.run(() => apiSend("/api/v1/integrations/telegram", "DELETE"), "Removed.")) onChange();
          }}
        >
          Remove
        </Button>
        {save.view}
      </div>
    </Card>
  );
}
