import { getToken, signalUnauthorized } from "./auth";

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

function errorMessage(body: unknown, fallback: string): string {
  const b = body as { error?: { message?: string }; detail?: unknown } | null;
  if (b?.error?.message) return b.error.message;
  if (typeof b?.detail === "string") return b.detail;
  if (Array.isArray(b?.detail)) {
    return (b.detail as { loc?: unknown[]; msg?: string }[])
      .map((d) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg ?? ""}`.replace(/^: /, ""))
      .join("; ");
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}, allow503 = false): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = { Accept: "application/json", ...(init.headers as Record<string, string>) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  const body: unknown = res.status === 204 ? null : await res.json().catch(() => null);
  if (res.status === 401 && !path.startsWith("/api/v1/auth/")) signalUnauthorized();
  if (!res.ok) {
    if (allow503 && res.status === 503 && body) return body as T;
    throw new ApiError(res.status, errorMessage(body, res.statusText));
  }
  return body as T;
}

export function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  // Readiness returns a useful body with 503; surface it to callers that want it.
  return request<T>(path, init, path.startsWith("/health"));
}

export function apiSend<T>(path: string, method: "POST" | "PUT" | "PATCH" | "DELETE", data?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: data === undefined ? {} : { "Content-Type": "application/json" },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
}
