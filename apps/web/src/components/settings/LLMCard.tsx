"use client";

import { useMemo, useState } from "react";
import { Button, TextField, useAction } from "@/components/forms";
import { StatusPill } from "@/components/StatusPill";
import { Card } from "@/components/ui";
import { apiSend } from "@/lib/api";
import type { LLMProviderInfo, ParsePreview, ParsingRuntime } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const MODES: { value: ParsingRuntime["mode"]; label: string }[] = [
  { value: "rules_then_llm", label: "Rules first, AI only for unclear messages (recommended)" },
  { value: "rules_only", label: "Rules only — free, no AI" },
  { value: "llm_only", label: "AI for every message" },
];

const OTHER = "__other__";

export function LLMCard({ parsing, onChange }: { parsing: ParsingRuntime; onChange: () => void }) {
  const providers = useApi<LLMProviderInfo[]>("/api/v1/llm/providers");
  const [provider, setProvider] = useState(parsing.llm_provider);
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState(parsing.llm_base_url ?? "");
  const [model, setModel] = useState(parsing.llm_model);
  const [customModel, setCustomModel] = useState("");
  const [test, setTest] = useState<ParsePreview | null>(null);
  const act = useAction();

  const info = providers.data?.find((p) => p.id === provider);
  const needsUrl = provider === "custom" || provider === "ollama";
  const canList = Boolean(info && (!info.needs_key || info.key_set));

  // Live model list from the provider (only once its key is saved).
  const modelList = useApi<{ provider: string; models: string[] }>(
    canList ? `/api/v1/llm/models?provider=${provider}&k=${info?.key_set ? 1 : 0}` : null,
  );
  const models = useMemo(
    () => (canList && modelList.data?.provider === provider ? modelList.data.models : []),
    [canList, modelList.data, provider],
  );
  const loadingModels = canList && modelList.data?.provider !== provider && !modelList.error;
  const modelsError = canList ? modelList.error : null;

  const options = useMemo(() => {
    const set = new Set([...(info?.suggested_models ?? []), ...models]);
    if (provider === parsing.llm_provider && parsing.llm_model) set.add(parsing.llm_model);
    return [...set];
  }, [info, models, provider, parsing]);

  const selected = options.includes(model) ? model : OTHER;
  const finalModel = selected === OTHER ? customModel.trim() : model;

  async function save() {
    const ok = await act.run(async () => {
      if (apiKey) await apiSend("/api/v1/integrations/llm", "PUT", { provider, api_key: apiKey.trim() });
      if (!finalModel) throw new Error("Choose a model.");
      await apiSend("/api/v1/settings/parsing", "PATCH", {
        llm_provider: provider,
        llm_model: finalModel,
        ...(needsUrl ? { llm_base_url: baseUrl.trim() || null } : {}),
      });
    }, "Saved.");
    if (ok) {
      setApiKey("");
      providers.reload();
      onChange();
    }
  }

  return (
    <Card title="AI signal parsing">
      <label className="block text-sm">
        <span className="text-muted">When to use AI</span>
        <select
          value={parsing.mode}
          onChange={(e) => act.run(() => apiSend("/api/v1/settings/parsing", "PATCH", { mode: e.target.value }), "Saved.").then(onChange)}
          className="mt-1 w-full rounded-md border border-border bg-bg px-3 py-1.5"
        >
          {MODES.map((m) => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>
      </label>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="text-muted">Provider</span>
          <select
            value={provider}
            onChange={(e) => {
              setProvider(e.target.value);
              setModel("");
              setCustomModel("");
              setTest(null);
            }}
            className="mt-1 w-full rounded-md border border-border bg-bg px-3 py-1.5"
          >
            {providers.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}{p.active ? " (active)" : ""}{p.key_set ? " ✓" : ""}
              </option>
            ))}
          </select>
          {info && <span className="mt-1 block text-xs text-muted">{info.note}</span>}
        </label>
        {info?.needs_key !== false || provider === "custom" ? (
          <TextField
            label={`API key ${info?.key_set ? "(saved)" : ""}`}
            value={apiKey}
            onChange={setApiKey}
            type="password"
            placeholder={info?.key_set ? "unchanged" : info?.key_hint}
          />
        ) : (
          <div className="text-sm text-muted sm:pt-6">No API key needed.</div>
        )}
      </div>

      {needsUrl && (
        <div className="mt-3">
          <TextField label="Base URL" value={baseUrl} onChange={setBaseUrl} placeholder={info?.base_url ?? "https://your-server/v1"} hint="OpenAI-compatible endpoint (…/v1)." />
        </div>
      )}

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="text-muted">Model</span>
          <select
            value={selected}
            onChange={(e) => setModel(e.target.value === OTHER ? "" : e.target.value)}
            className="mt-1 w-full rounded-md border border-border bg-bg px-3 py-1.5"
          >
            {options.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
            <option value={OTHER}>Other… (type a model name)</option>
          </select>
          <span className="mt-1 block text-xs text-muted">
            {loadingModels
              ? "Loading models from the provider…"
              : modelsError
                ? `Couldn't load model list: ${modelsError}`
                : !canList
                  ? "Save the API key to load the provider's model list."
                  : `${models.length} models available.`}
          </span>
        </label>
        {selected === OTHER && <TextField label="Model name" value={customModel} onChange={setCustomModel} placeholder="e.g. llama-3.3-70b-versatile" />}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button onClick={save}>Save</Button>
        <Button
          variant="secondary"
          disabled={!info?.active}
          onClick={() => act.run(async () => setTest(await apiSend<ParsePreview>("/api/v1/llm/test", "POST", {})))}
        >
          Test active model
        </Button>
        {info?.key_set && (
          <Button
            variant="secondary"
            onClick={async () => {
              if (!confirm(`Remove the ${info.label} API key?`)) return;
              if (await act.run(() => apiSend(`/api/v1/integrations/llm?provider=${provider}`, "DELETE"), "Removed.")) {
                providers.reload();
                onChange();
              }
            }}
          >
            Remove key
          </Button>
        )}
        {act.view}
      </div>
      {test && (
        <p className="mt-2 text-sm">
          <StatusPill tone={test.is_signal ? "good" : "warn"}>{test.is_signal ? "works" : "answered"}</StatusPill>{" "}
          {test.is_signal
            ? `Read: ${test.side} ${test.symbol_text} @ ${test.entry_low} SL ${test.stop_loss} TGT ${test.targets.join("/")}`
            : test.reason}
        </p>
      )}
    </Card>
  );
}
