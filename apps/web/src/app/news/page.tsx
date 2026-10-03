"use client";

import { useState } from "react";
import { AlertsTab } from "@/components/news/AlertsTab";
import { HeadlinesTab } from "@/components/news/HeadlinesTab";
import { WatchTiles } from "@/components/news/WatchTiles";
import { Notice, PageHeader } from "@/components/ui";

const TABS = [
  { key: "alerts", label: "Alerts" },
  { key: "headlines", label: "Headlines" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export default function NewsPage() {
  const [tab, setTab] = useState<TabKey>("alerts");

  function onKey(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const i = TABS.findIndex((t) => t.key === tab);
    const next = TABS[(i + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length];
    setTab(next.key);
    document.getElementById(`news-tab-${next.key}`)?.focus();
  }

  return (
    <>
      <PageHeader title="News & alerts" description="Market headlines and sharp moves in the instruments you watch." />
      <div className="mb-4">
        <Notice>Keywords, feeds and watched instruments are set in Settings → News &amp; market alerts. Alerts are also sent by the Telegram bot.</Notice>
      </div>
      <section aria-label="Market watch" className="mb-6">
        <WatchTiles />
      </section>
      <div className="mb-3 flex flex-wrap gap-1" role="tablist" aria-label="News sections" onKeyDown={onKey}>
        {TABS.map((t) => (
          <button
            key={t.key}
            id={`news-tab-${t.key}`}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            aria-controls={`news-panel-${t.key}`}
            tabIndex={tab === t.key ? 0 : -1}
            onClick={() => setTab(t.key)}
            className={`rounded-md px-3 py-1 text-sm ${tab === t.key ? "bg-panel-2 font-medium" : "text-muted hover:text-text"}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`news-panel-${tab}`} aria-labelledby={`news-tab-${tab}`}>
        {tab === "alerts" ? <AlertsTab /> : <HeadlinesTab />}
      </div>
    </>
  );
}
