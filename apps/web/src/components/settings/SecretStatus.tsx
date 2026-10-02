import { StatusPill } from "@/components/StatusPill";
import type { SecretField } from "@/lib/types";

export function SecretStatus({ label, field }: { label: string; field: SecretField }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted">{label}</span>
      {field.set ? (
        <span className="font-mono text-xs">{field.hint ?? "set"}</span>
      ) : (
        <StatusPill tone="neutral">not set</StatusPill>
      )}
    </div>
  );
}
