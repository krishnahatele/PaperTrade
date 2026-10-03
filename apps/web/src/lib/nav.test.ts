import { describe, expect, it } from "vitest";
import { ALL_NAV_ITEMS, findNavItem, isActive } from "./nav";

describe("nav", () => {
  it("has unique hrefs", () => {
    const hrefs = ALL_NAV_ITEMS.map((i) => i.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });

  it("matches the dashboard only at root", () => {
    expect(isActive("/", "/")).toBe(true);
    expect(isActive("/signals", "/")).toBe(false);
  });

  it("matches nested routes", () => {
    expect(isActive("/signals/abc", "/signals")).toBe(true);
    expect(isActive("/signalsx", "/signals")).toBe(false);
  });

  it("finds the current item", () => {
    expect(findNavItem("/orders")?.label).toBe("Orders");
    expect(findNavItem("/")?.label).toBe("Dashboard");
    expect(findNavItem("/nope")).toBeUndefined();
  });
});
