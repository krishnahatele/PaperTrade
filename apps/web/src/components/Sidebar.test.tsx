import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ALL_NAV_ITEMS } from "@/lib/nav";
import { Sidebar } from "./Sidebar";

vi.mock("next/navigation", () => ({ usePathname: () => "/orders" }));

describe("Sidebar", () => {
  it("renders every nav item and marks the active one", () => {
    render(<Sidebar />);
    for (const item of ALL_NAV_ITEMS) {
      expect(screen.getByRole("link", { name: item.label })).toHaveAttribute("href", item.href);
    }
    expect(screen.getByRole("link", { name: "Orders" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Signals" })).not.toHaveAttribute("aria-current");
  });
});
