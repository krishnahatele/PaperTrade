"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect } from "react";
import { Button, useAction } from "@/components/forms";
import { ReplayReportView } from "@/components/replay/ReplayReportView";
import { ReplayTrades } from "@/components/replay/ReplayTrades";
import { isActive, statusTone } from "@/components/replay/labels";
import { StatusPill } from "@/components/StatusPill";
import { Notice, PageHeader } from "@/components/ui";
import { apiSend } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { ReplayReport, ReplayRun } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function hasReport(r: ReplayRun["report"]): r is ReplayReport {
  return "overall" in r && r.overall !== undefined;
}

export default function ReplayDetailPage() {
  const { id } = useParams<{ id: string }>();
  const api = useApi<ReplayRun>(`/api/v1/replays/${id}`);
  const { reload } = api;
  const run = api.data;
  const active = run ? isActive(run.status) : false;
  const act = useAction();

  // Poll every 2 s while the replay is queued or running.
  useEffect(() => {
    if (!active) return;
    const t = setInterval(reload, 2000);
    return () => clearInterval(t);
  }, [active, reload]);

  async function cancel() {
    if (await act.run(() => apiSend(`/api/v1/replays/${id}/cancel`, "POST"))) reload();
  }

  const p = run?.progress ?? {};
  const total = p.messages ?? 0;
  const done = p.done ?? 0;
  const ratio = total > 0 ? Math.min(1, done / total) : 0;

  return (
    <>
      <PageHeader
        title={run ? run.name || "Replay" : "Replay"}
        description={run ? `Started ${formatDateTime(run.started_at ?? run.created_at)}${run.finished_at ? ` · finished ${formatDateTime(run.finished_at)}` : ""}` : undefined}
        actions={<Link href="/replay" className="text-sm text-accent underline">All replays</Link>}
      />
      {api.error && <Notice tone="error">{api.error}</Notice>}
      {!run && !api.error && <p className="text-sm text-muted">Loading…</p>}
      {run && (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-3">
            <StatusPill tone={statusTone(run.status)}>{run.status}</StatusPill>
            {active && <Button variant="secondary" onClick={cancel}>Cancel</Button>}
            {act.view}
          </div>

          {active && (
            <div className="space-y-1">
              <div
                className="h-2 w-full overflow-hidden rounded-full bg-panel-2"
                role="progressbar"
                aria-label="Replay progress"
                aria-valuemin={0}
                aria-valuemax={total || 100}
                aria-valuenow={total ? done : undefined}
              >
                <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${ratio * 100}%` }} />
              </div>
              <p className="text-xs text-muted">
                {p.stage ?? (run.status === "queued" ? "waiting to start" : "working")}
                {total > 0 && ` · ${done}/${total} messages`}
                {p.signals !== undefined && ` · ${p.signals} signals`}
              </p>
            </div>
          )}

          {run.status === "failed" && <Notice tone="error">Replay failed: {run.error ?? "unknown error"}</Notice>}
          {run.status === "cancelled" && <Notice>This replay was cancelled.</Notice>}

          {run.status === "done" && hasReport(run.report) && (
            <>
              <ReplayReportView run={run} report={run.report} />
              <ReplayTrades runId={run.id} sources={Object.keys(run.report.by_source ?? {})} />
            </>
          )}
          {run.status === "done" && !hasReport(run.report) && <Notice>No report was produced for this replay.</Notice>}
        </div>
      )}
    </>
  );
}
