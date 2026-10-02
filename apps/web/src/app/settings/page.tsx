"use client";

import { KiteCard } from "@/components/settings/KiteCard";
import { LLMCard } from "@/components/settings/LLMCard";
import { PasswordCard } from "@/components/settings/PasswordCard";
import { TelegramCard } from "@/components/settings/TelegramCard";
import { TradingCard } from "@/components/settings/TradingCard";
import { Notice, PageHeader } from "@/components/ui";
import type { SystemInfo } from "@/lib/api";
import type { Integrations, RuntimeSettings } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function SettingsPage() {
  const integrations = useApi<Integrations>("/api/v1/integrations");
  const runtime = useApi<RuntimeSettings>("/api/v1/settings");
  const info = useApi<SystemInfo>("/api/v1/system/info");

  const error = integrations.error ?? runtime.error;
  const reload = () => {
    integrations.reload();
    runtime.reload();
  };

  return (
    <>
      <PageHeader title="Settings" description="Integrations, credentials and trading controls. Credentials are encrypted at rest." />
      {error && <Notice tone="error">{error}</Notice>}
      {integrations.data && runtime.data && (
        <div className="grid gap-4 xl:grid-cols-2">
          <TradingCard key={JSON.stringify(runtime.data.trading)} trading={runtime.data.trading} liveAllowed={Boolean(info.data?.live_trading_enabled)} onChange={reload} />
          <TelegramCard data={integrations.data.telegram} onChange={reload} />
          <KiteCard data={integrations.data.kite} onChange={reload} />
          <LLMCard key={runtime.data.parsing.llm_model} data={integrations.data.llm} parsing={runtime.data.parsing} onChange={reload} />
          <PasswordCard />
        </div>
      )}
    </>
  );
}
