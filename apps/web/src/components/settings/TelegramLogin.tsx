"use client";

import { useState } from "react";
import { Button, TextField, useAction } from "@/components/forms";
import { apiSend } from "@/lib/api";
import type { TelegramStatus } from "@/lib/types";
import { useApi } from "@/lib/useApi";

type Step = "code" | "password" | "done";

export function TelegramLogin({ canLogin, onChange }: { canLogin: boolean; onChange: () => void }) {
  const status = useApi<TelegramStatus>("/api/v1/telegram/status");
  const [step, setStep] = useState<Step | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const act = useAction();

  const current: Step | null = step ?? status.data?.login_step ?? null;
  const done = () => {
    setStep(null);
    setCode("");
    setPassword("");
    status.reload();
    onChange();
  };

  if (status.data?.authorized) {
    return (
      <div className="mt-4 rounded-md border border-border bg-panel-2 p-3 text-sm">
        <p>
          Logged in. {status.data.listening ? `Listening to ${status.data.channels} channel(s).` : "Add channels on the Sources page."}
          {status.data.messages_received > 0 && ` ${status.data.messages_received} message(s) received since start.`}
        </p>
        <div className="mt-2 flex items-center gap-2">
          <Button
            variant="secondary"
            onClick={async () => {
              if (!confirm("Log out of Telegram on this workstation?")) return;
              if (await act.run(() => apiSend("/api/v1/telegram/logout", "POST"), "Logged out.")) done();
            }}
          >
            Log out
          </Button>
          {act.view}
        </div>
      </div>
    );
  }

  return (
    <div className="mt-4 rounded-md border border-border bg-panel-2 p-3 text-sm">
      {status.data?.last_error && <p className="mb-2 text-bad">{status.data.last_error}</p>}
      {current === null && (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            disabled={!canLogin}
            onClick={async () => {
              if (await act.run(() => apiSend("/api/v1/telegram/login/start", "POST"), "Code sent. Check your Telegram app (or SMS).")) setStep("code");
            }}
          >
            Log in to Telegram
          </Button>
          {!canLogin && <span className="text-xs text-muted">Save API ID, API hash and phone number first.</span>}
        </div>
      )}
      {current === "code" && (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            await act.run(async () => {
              const r = await apiSend<{ step: Step }>("/api/v1/telegram/login/code", "POST", { code });
              if (r.step === "done") done();
              else setStep(r.step);
            });
          }}
        >
          <div className="w-40">
            <TextField label="Login code" value={code} onChange={setCode} inputMode="numeric" autoComplete="one-time-code" placeholder="12345" />
          </div>
          <Button type="submit">Verify</Button>
          <Button variant="secondary" onClick={() => setStep(null)}>
            Cancel
          </Button>
        </form>
      )}
      {current === "password" && (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            await act.run(async () => {
              const r = await apiSend<{ step: Step }>("/api/v1/telegram/login/password", "POST", { password });
              if (r.step === "done") done();
            });
          }}
        >
          <div className="w-56">
            <TextField label="Two-step verification password" type="password" value={password} onChange={setPassword} autoComplete="current-password" />
          </div>
          <Button type="submit">Submit</Button>
        </form>
      )}
      <div className="mt-2">{act.view}</div>
    </div>
  );
}
