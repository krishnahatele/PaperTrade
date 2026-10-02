export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

export type AdapterHealth = { name: string; state: "ready" | "disabled" | "not_configured" | "error"; detail: string | null };

export type SystemInfo = {
  app_name: string;
  version: string;
  environment: string;
  trading_mode: "disabled" | "paper" | "live";
  live_trading_enabled: boolean;
  phase: string;
  adapters: Record<string, AdapterHealth>;
};

export type Readiness = { status: "ok" | "degraded"; checks: { name: string; ok: boolean; detail: string | null }[] };

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { ...init, headers: { Accept: "application/json", ...init?.headers } });
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const msg =
      (body as { error?: { message?: string } } | null)?.error?.message ??
      (body as { detail?: string } | null)?.detail ??
      res.statusText;
    // Readiness returns a useful body with 503; surface it to callers that want it.
    if (res.status === 503 && body) return body as T;
    throw new ApiError(res.status, String(msg));
  }
  return body as T;
}

export async function apiSend<T>(path: string, method: "POST" | "PUT" | "PATCH" | "DELETE", data?: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  const body: unknown = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    const err = body as { error?: { message?: string }; detail?: unknown } | null;
    const detail = err?.error?.message ?? (typeof err?.detail === "string" ? err.detail : JSON.stringify(err?.detail ?? res.statusText));
    throw new ApiError(res.status, detail);
  }
  return body as T;
}
