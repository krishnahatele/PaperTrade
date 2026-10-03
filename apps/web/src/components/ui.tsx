export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {actions}
    </div>
  );
}

export function Card({ title, children, className = "" }: { title?: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={`rounded-lg border border-border bg-panel p-4 ${className}`}>
      {title && <h3 className="mb-3 text-sm font-medium text-muted">{title}</h3>}
      {children}
    </section>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "error"; children: React.ReactNode }) {
  const cls = tone === "error" ? "border-bad/40 bg-bad/10 text-bad" : "border-accent/30 bg-accent/5 text-text";
  return <div className={`rounded-md border px-3 py-2 text-sm ${cls}`}>{children}</div>;
}
