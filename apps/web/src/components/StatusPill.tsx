type Tone = "good" | "warn" | "bad" | "neutral" | "accent";

const TONES: Record<Tone, string> = {
  good: "text-good border-good/40 bg-good/10",
  warn: "text-warn border-warn/40 bg-warn/10",
  bad: "text-bad border-bad/40 bg-bad/10",
  accent: "text-accent border-accent/40 bg-accent/10",
  neutral: "text-muted border-border bg-panel-2",
};

export function StatusPill({ tone = "neutral", children }: { tone?: Tone; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}>
      {children}
    </span>
  );
}

export function toneForState(state: string): Tone {
  switch (state) {
    case "ready":
    case "ok":
    case "filled":
    case "executed":
    case "validated":
    case "parsed":
      return "good";
    case "disabled":
    case "not_configured":
    case "pending":
    case "new":
    case "open":
    case "submitted":
    case "partially_filled":
      return "warn";
    case "error":
    case "degraded":
    case "rejected":
    case "failed":
      return "bad";
    default:
      return "neutral";
  }
}
