"use client";

import { ReplayForm } from "@/components/replay/ReplayForm";
import { ReplayRuns } from "@/components/replay/ReplayRuns";
import { PageHeader } from "@/components/ui";

export default function ReplayPage() {
  return (
    <>
      <PageHeader
        title="Replay"
        description="Picks messages from your Telegram groups for the chosen days and buys/sells exactly as each signal said, at the message time, using historical 1-minute prices from Kite or Dhan. Your SL, targets and trailing rules are applied and you get the group's accuracy. This is separate from your live paper trading."
      />
      <div className="space-y-6">
        <ReplayForm />
        <section>
          <h3 className="mb-3 text-sm font-medium text-muted">Past replays</h3>
          <ReplayRuns />
        </section>
      </div>
    </>
  );
}
