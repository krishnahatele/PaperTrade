"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { NAV, isActive } from "@/lib/nav";

export function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        aria-label="Toggle navigation"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="fixed left-3 top-3 z-40 rounded-md border border-border bg-panel px-2 py-1 text-sm md:hidden"
      >
        ☰
      </button>
      <aside
        className={`fixed inset-y-0 left-0 z-30 w-60 shrink-0 border-r border-border bg-panel transition-transform md:static md:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-14 items-center gap-2 border-b border-border px-5">
          <span className="grid h-7 w-7 place-items-center rounded-md bg-accent text-xs font-bold text-white">M</span>
          <span className="font-semibold tracking-tight">MarketOS</span>
        </div>
        <nav aria-label="Main" className="space-y-5 px-3 py-4">
          {NAV.map((section) => (
            <div key={section.title}>
              <p className="px-2 pb-1 text-[11px] font-medium uppercase tracking-wider text-muted">{section.title}</p>
              <ul className="space-y-0.5">
                {section.items.map((item) => {
                  const active = isActive(pathname, item.href);
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        onClick={() => setOpen(false)}
                        aria-current={active ? "page" : undefined}
                        className={`block rounded-md px-2 py-1.5 text-sm ${
                          active ? "bg-panel-2 font-medium text-text" : "text-muted hover:bg-panel-2 hover:text-text"
                        }`}
                      >
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>
      </aside>
    </>
  );
}
