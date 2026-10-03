"use client";

import { useState } from "react";
import { Button, TextField, useAction } from "@/components/forms";
import { apiGet, apiSend } from "@/lib/api";
import type { KiteStatus } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export function KiteLogin({ configured, onChange }: { configured: boolean; onChange: () => void }) {
  const status = useApi<KiteStatus>("/api/v1/kite/status");
  const [redirect, setRedirect] = useState("");
  const act = useAction();
  const refresh = () => {
    status.reload();
    onChange();
  };

  return (
    <div className="mt-4 rounded-md border border-border bg-panel-2 p-3 text-sm">
      {status.data?.session_active ? (
        <div className="flex flex-wrap items-center gap-2">
          <span>Logged in as <b>{status.data.user_id}</b>. Live prices are on. (Kite sessions end daily around 6 AM.)</span>
          <Button variant="secondary" onClick={() => act.run(() => apiSend("/api/v1/kite/logout", "POST"), "Logged out.").then(refresh)}>
            Log out
          </Button>
        </div>
      ) : (
        <>
          <p className="mb-2">
            Daily login: <b>1.</b> open Kite login, sign in with Zerodha. <b>2.</b> You’ll land on your app’s redirect URL. Copy the whole address from the browser bar and paste it here.
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <Button
              disabled={!configured}
              onClick={() =>
                act.run(async () => {
                  const r = await apiGet<{ url: string }>("/api/v1/kite/login-url");
                  window.open(r.url, "_blank", "noopener");
                })
              }
            >
              Open Kite login
            </Button>
            <div className="min-w-64 flex-1">
              <TextField label="Redirect URL (or request_token)" value={redirect} onChange={setRedirect} placeholder="https://…?request_token=…" />
            </div>
            <Button
              disabled={!redirect.trim()}
              onClick={async () => {
                if (await act.run(() => apiSend("/api/v1/kite/session", "POST", { request_token: redirect.trim() }), "Kite connected.")) {
                  setRedirect("");
                  refresh();
                }
              }}
            >
              Connect
            </Button>
          </div>
          {!configured && <p className="mt-2 text-xs text-muted">Save the API key and secret first.</p>}
        </>
      )}
      <div className="mt-2">{act.view}</div>
    </div>
  );
}
