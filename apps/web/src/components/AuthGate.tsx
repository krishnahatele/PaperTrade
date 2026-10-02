"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiSend } from "@/lib/api";
import { setToken, UNAUTHORIZED_EVENT } from "@/lib/auth";

type Status = { auth_enabled: boolean; configured: boolean; authenticated: boolean };

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [offline, setOffline] = useState(false);

  const refresh = useCallback(() => {
    apiGet<Status>("/api/v1/auth/status")
      .then((s) => {
        setStatus(s);
        setOffline(false);
      })
      .catch(() => setOffline(true));
  }, []);

  useEffect(() => {
    refresh();
    const onUnauthorized = () => refresh();
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [refresh]);

  useEffect(() => {
    if (!offline) return;
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [offline, refresh]);

  if (offline) {
    return (
      <Centered>
        <h1 className="text-lg font-semibold">Can’t reach the MarketOS API</h1>
        <p className="mt-2 text-sm text-muted">Start the backend and this page will connect automatically.</p>
      </Centered>
    );
  }
  if (!status) return <Centered><p className="text-sm text-muted">Loading…</p></Centered>;
  if (status.authenticated) return <>{children}</>;
  return <LoginForm firstRun={!status.configured} onDone={refresh} />;
}

function Centered({ children }: { children: React.ReactNode }) {
  return <div className="grid min-h-screen place-items-center px-4"><div className="w-full max-w-sm text-center">{children}</div></div>;
}

function LoginForm({ firstRun, onDone }: { firstRun: boolean; onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (firstRun && password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const r = await apiSend<{ token: string }>(firstRun ? "/api/v1/auth/setup" : "/api/v1/auth/login", "POST", { password });
      setToken(r.token);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-lg border border-border bg-panel p-6">
        <div className="mb-5 flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-md bg-accent text-sm font-bold text-white">M</span>
          <span className="text-lg font-semibold">MarketOS</span>
        </div>
        <h1 className="text-base font-semibold">{firstRun ? "Create admin password" : "Sign in"}</h1>
        <p className="mt-1 text-sm text-muted">
          {firstRun ? "First run: choose a password (at least 10 characters) to protect this workstation." : "Enter your admin password."}
        </p>
        <label className="mt-4 block text-sm">
          Password
          <input type="password" autoComplete={firstRun ? "new-password" : "current-password"} value={password} onChange={(e) => setPassword(e.target.value)} required autoFocus className="mt-1 w-full rounded-md border border-border bg-bg px-3 py-2 outline-none focus:border-accent" />
        </label>
        {firstRun && (
          <label className="mt-3 block text-sm">
            Confirm password
            <input type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required className="mt-1 w-full rounded-md border border-border bg-bg px-3 py-2 outline-none focus:border-accent" />
          </label>
        )}
        {error && <p role="alert" className="mt-3 text-sm text-bad">{error}</p>}
        <button type="submit" disabled={busy} className="mt-5 w-full rounded-md bg-accent px-3 py-2 text-sm font-medium text-white disabled:opacity-50">
          {busy ? "…" : firstRun ? "Create password" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
