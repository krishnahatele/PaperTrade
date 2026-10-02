"use client";

import { useState } from "react";

export function TextField({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  hint,
  autoComplete = "off",
  inputMode,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
  hint?: string;
  autoComplete?: string;
  inputMode?: React.HTMLAttributes<HTMLInputElement>["inputMode"];
}) {
  return (
    <label className="block text-sm">
      <span className="text-muted">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        inputMode={inputMode}
        className="mt-1 w-full rounded-md border border-border bg-bg px-3 py-1.5 outline-none focus:border-accent"
      />
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function Toggle({
  label,
  description,
  checked,
  onChange,
  danger = false,
  disabled = false,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  danger?: boolean;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-2">
      <div>
        <p className="text-sm font-medium">{label}</p>
        {description && <p className="text-xs text-muted">{description}</p>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-40 ${
          checked ? (danger ? "bg-bad" : "bg-accent") : "bg-border"
        }`}
      >
        <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${checked ? "left-[22px]" : "left-0.5"}`} />
      </button>
    </div>
  );
}

export function Button({
  children,
  onClick,
  variant = "primary",
  type = "button",
  disabled,
}: {
  children: React.ReactNode;
  onClick?: () => void | Promise<void>;
  variant?: "primary" | "secondary" | "danger";
  type?: "button" | "submit";
  disabled?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const cls = {
    primary: "bg-accent text-white",
    secondary: "border border-border bg-panel text-text",
    danger: "bg-bad text-white",
  }[variant];
  return (
    <button
      type={type}
      disabled={disabled || busy}
      onClick={
        onClick
          ? async () => {
              setBusy(true);
              try {
                await onClick();
              } finally {
                setBusy(false);
              }
            }
          : undefined
      }
      className={`rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50 ${cls}`}
    >
      {busy ? "…" : children}
    </button>
  );
}

/** Small helper for "run an action, show result or error" UX. */
export function useAction() {
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  async function run(fn: () => Promise<unknown>, success?: string) {
    setMessage(null);
    try {
      await fn();
      if (success) setMessage({ tone: "ok", text: success });
      return true;
    } catch (e) {
      setMessage({ tone: "error", text: e instanceof Error ? e.message : String(e) });
      return false;
    }
  }
  const view = message ? (
    <p role={message.tone === "error" ? "alert" : "status"} className={`text-sm ${message.tone === "error" ? "text-bad" : "text-good"}`}>
      {message.text}
    </p>
  ) : null;
  return { run, view, setMessage };
}
