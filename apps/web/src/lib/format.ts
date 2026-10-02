export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "medium" });
}

export function formatNumber(v: string | number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "number" ? v : Number(v);
  if (Number.isNaN(n)) return String(v);
  return n.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function shortId(id: string | null | undefined): string {
  return id ? id.slice(0, 8) : "—";
}

const ADAPTER_LABELS: Record<string, string> = {
  broker: "Broker",
  market_data: "Market data",
  telegram: "Telegram",
  llm: "LLM",
};

export function adapterLabel(key: string): string {
  return ADAPTER_LABELS[key] ?? key;
}
