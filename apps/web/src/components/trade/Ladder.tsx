import { formatNumber } from "@/lib/format";
import type { TradePlan } from "@/lib/types";

export function Ladder({ t }: { t: TradePlan }) {
  const legs = t.targets.filter((l) => l.status !== "cancelled");
  if (legs.length === 0) return <>—</>;
  return (
    <span className="inline-flex gap-1">
      {legs.map((l, i) => (
        <span key={i} className={l.status === "hit" ? "text-good" : ""} title={`${l.quantity} qty`}>
          T{i + 1} {formatNumber(l.price)}
          {l.status === "hit" ? " ✓" : ""}
        </span>
      ))}
    </span>
  );
}
