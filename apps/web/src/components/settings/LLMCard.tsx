"use client";

import { useState } from "react";
import { Button, TextField, useAction } from "@/components/forms";
import { Card } from "@/components/ui";
import { apiSend } from "@/lib/api";
import type { Integrations, ParsingRuntime } from "@/lib/types";
import { SecretStatus } from "./SecretStatus";

const MODES: { value: ParsingRuntime["mode"]; label: string }[] = [
  { value: "rules_then_llm", label: "Rules first, AI fallback (recommended)" },
  { value: "rules_only", label: "Rules only (no AI)" },
  { value: "llm_only", label: "AI only" },
];

export function LLMCard({ data, parsing, onChange }: { data: Integrations["llm"]; parsing: ParsingRuntime; onChange: () => void }) {
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(parsing.llm_model);
  const act = useAction();

  return (
    <Card title="AI signal parsing">
      <div className="space-y-1.5">
        <SecretStatus label="Anthropic API key" field={data.api_key} />
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <TextField label="Anthropic API key" value={apiKey} onChange={setApiKey} type="password" placeholder={data.api_key.set ? "unchanged" : "sk-ant-…"} />
        <TextField label="Model" value={model} onChange={setModel} />
      </div>
      <label className="mt-3 block text-sm">
        <span className="text-muted">Parsing mode</span>
        <select
          value={parsing.mode}
          onChange={(e) => act.run(() => apiSend("/api/v1/settings/parsing", "PATCH", { mode: e.target.value }), "Saved.").then(onChange)}
          className="mt-1 w-full rounded-md border border-border bg-bg px-3 py-1.5"
        >
          {MODES.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </label>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          onClick={async () => {
            const ok = await act.run(async () => {
              if (apiKey) await apiSend("/api/v1/integrations/llm", "PUT", { api_key: apiKey.trim() });
              if (model !== parsing.llm_model) await apiSend("/api/v1/settings/parsing", "PATCH", { llm_model: model.trim() });
            }, "Saved.");
            if (ok) {
              setApiKey("");
              onChange();
            }
          }}
        >
          Save
        </Button>
        {data.api_key.set && (
          <Button
            variant="secondary"
            onClick={async () => {
              if (await act.run(() => apiSend("/api/v1/integrations/llm", "DELETE"), "Removed.")) onChange();
            }}
          >
            Remove key
          </Button>
        )}
        {act.view}
      </div>
    </Card>
  );
}
