"use client";

import { useState } from "react";
import type { Page } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Notice } from "./ui";

export type Column<T> = {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  align?: "left" | "right";
};

const PAGE_SIZE = 25;

export function DataTable<T extends { id: string }>({
  path,
  columns,
  emptyText = "Nothing here yet.",
  query = "",
}: {
  path: string;
  columns: Column<T>[];
  emptyText?: string;
  query?: string;
}) {
  const [offset, setOffset] = useState(0);
  const sep = path.includes("?") ? "&" : "?";
  const { data, error, loading } = useApi<Page<T>>(`${path}${sep}limit=${PAGE_SIZE}&offset=${offset}${query}`);

  if (error) return <Notice tone="error">Could not load data: {error}</Notice>;

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-panel">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-panel-2 text-left text-xs uppercase tracking-wide text-muted">
            <tr>
              {columns.map((c) => (
                <th key={c.key} className={`whitespace-nowrap px-3 py-2 font-medium ${c.align === "right" ? "text-right" : ""}`}>
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && !data && (
              <tr>
                <td colSpan={columns.length} className="px-3 py-6 text-center text-muted">
                  Loading…
                </td>
              </tr>
            )}
            {data?.items.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-3 py-6 text-center text-muted">
                  {emptyText}
                </td>
              </tr>
            )}
            {data?.items.map((row) => (
              <tr key={row.id} className="border-t border-border">
                {columns.map((c) => (
                  <td key={c.key} className={`whitespace-nowrap px-3 py-2 ${c.align === "right" ? "text-right font-mono tabular-nums" : ""}`}>
                    {c.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data && data.total > PAGE_SIZE && (
        <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs text-muted">
          <span>
            {offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)} of {data.total}
          </span>
          <div className="flex gap-2">
            <button type="button" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))} className="rounded border border-border px-2 py-1 disabled:opacity-40">
              Previous
            </button>
            <button type="button" disabled={offset + PAGE_SIZE >= data.total} onClick={() => setOffset((o) => o + PAGE_SIZE)} className="rounded border border-border px-2 py-1 disabled:opacity-40">
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
