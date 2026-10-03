export type NavItem = {
  href: string;
  label: string;
  description: string;
};

export type NavSection = {
  title: string;
  items: NavItem[];
};

export const NAV: NavSection[] = [
  {
    title: "Overview",
    items: [{ href: "/", label: "Dashboard", description: "System status and activity at a glance" }],
  },
  {
    title: "Signals",
    items: [
      { href: "/signals", label: "Signals", description: "Structured trade ideas" },
      { href: "/sources", label: "Sources", description: "Telegram channels and other signal sources" },
    ],
  },
  {
    title: "Trading",
    items: [
      { href: "/trades", label: "Trades", description: "Managed trades: entry, stop-loss, targets and trailing" },
      { href: "/orders", label: "Orders", description: "Every order placed, paper or live" },
      { href: "/positions", label: "Positions", description: "Net holdings per account" },
      { href: "/instruments", label: "Instruments", description: "Tradable contracts" },
    ],
  },
  {
    title: "Market",
    items: [
      { href: "/news", label: "News & alerts", description: "Headlines, keyword alerts and sharp market moves" },
      { href: "/replay", label: "Replay", description: "Backtest past Telegram signals on historical prices" },
    ],
  },
  {
    title: "System",
    items: [
      { href: "/events", label: "Event log", description: "Audit trail of domain events" },
      { href: "/system", label: "Health", description: "Backend, database and adapter status" },
      { href: "/settings", label: "Settings", description: "Configuration and integrations" },
    ],
  },
];

export const ALL_NAV_ITEMS: NavItem[] = NAV.flatMap((s) => s.items);

export function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function findNavItem(pathname: string): NavItem | undefined {
  return ALL_NAV_ITEMS.find((i) => isActive(pathname, i.href) && (i.href !== "/" || pathname === "/"));
}
