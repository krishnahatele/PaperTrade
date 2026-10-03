import type { ReplayOutcome, ReplayStatus } from "@/lib/types";

export const SEGMENT_LABELS: Record<string, string> = {
  fno: "F&O",
  equity: "Equity",
  commodity: "Commodity",
  currency: "Currency",
  index: "Index",
};

export function segmentLabel(s: string | null | undefined): string {
  if (!s) return "—";
  return SEGMENT_LABELS[s] ?? s;
}

export const OUTCOME_LABELS: Record<ReplayOutcome, string> = {
  win: "won",
  loss: "lost",
  breakeven: "breakeven",
  entry_not_hit: "entry not hit",
  no_data: "no price data",
  unresolved: "symbol not found",
  incomplete: "no stop-loss",
  not_signal: "not a signal",
};

export function outcomeTone(o: ReplayOutcome): "good" | "bad" | "warn" | "neutral" {
  if (o === "win") return "good";
  if (o === "loss") return "bad";
  if (o === "no_data" || o === "unresolved" || o === "incomplete") return "warn";
  return "neutral";
}

export const EXIT_LABELS: Record<string, string> = {
  target: "target",
  stop: "stop-loss",
  trailing_stop: "trailing stop",
  manual: "manual",
  exit_all: "exit all",
  end_of_day: "session end",
  expired: "expired",
  cancelled: "cancelled",
};

export function exitLabel(r: string | null | undefined): string {
  if (!r) return "—";
  return EXIT_LABELS[r] ?? r.replace(/_/g, " ");
}

export function statusTone(s: ReplayStatus): "good" | "bad" | "warn" | "neutral" | "accent" {
  if (s === "done") return "good";
  if (s === "failed") return "bad";
  if (s === "running") return "accent";
  if (s === "queued") return "warn";
  return "neutral";
}

export function pct(v: string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  return `${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 1 })}%`;
}

export function isActive(status: string): boolean {
  return status === "queued" || status === "running";
}
