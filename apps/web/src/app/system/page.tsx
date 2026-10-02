"use client";

import { Card, Notice, PageHeader } from "@/components/ui";
import { StatusPill, toneForState } from "@/components/StatusPill";
import { API_URL, type Readiness, type SystemInfo } from "@/lib/api";
import { adapterLabel } from "@/lib/format";
import { useApi } from "@/lib/useApi";

export default function SystemPage() {
  const info = useApi<SystemInfo>("/api/v1/system/info", 10_000);
  const ready = useApi<Readiness>("/health/ready", 10_000);

  return (
    <>
      <PageHeader title="Health" description="Backend, database and integration status." />
      {ready.error && <Notice tone="error">API unreachable at {API_URL}: {ready.error}</Notice>}
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Readiness checks">
          <ul className="space-y-2 text-sm">
            {ready.data?.checks.map((c) => (
              <li key={c.name} className="flex items-center justify-between">
                <span className="capitalize">{c.name}</span>
                <StatusPill tone={c.ok ? "good" : "bad"}>{c.ok ? "ok" : (c.detail ?? "failed")}</StatusPill>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Adapters">
          <ul className="space-y-3 text-sm">
            {info.data &&
              Object.entries(info.data.adapters).map(([key, a]) => (
                <li key={key}>
                  <div className="flex items-center justify-between">
                    <span>{adapterLabel(key)}</span>
                    <StatusPill tone={toneForState(a.state)}>{a.state.replace("_", " ")}</StatusPill>
                  </div>
                  {a.detail && <p className="mt-0.5 text-xs text-muted">{a.detail}</p>}
                </li>
              ))}
          </ul>
        </Card>
        <Card title="API" className="md:col-span-2">
          <p className="text-sm">
            Base URL <code className="font-mono">{API_URL}</code> ·{" "}
            <a className="text-accent underline" href={`${API_URL}/docs`} target="_blank" rel="noreferrer">
              OpenAPI docs
            </a>
          </p>
        </Card>
      </div>
    </>
  );
}
