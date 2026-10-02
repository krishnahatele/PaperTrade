import { describe, expect, it } from "vitest";
import { formatDateTime, formatNumber, shortId } from "./format";

describe("format", () => {
  it("formats numbers and blanks", () => {
    expect(formatNumber(null)).toBe("—");
    expect(formatNumber("1500.5")).toBe("1,500.50");
    expect(formatNumber("abc")).toBe("abc");
  });
  it("formats dates defensively", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime("not a date")).toBe("—");
  });
  it("shortens ids", () => {
    expect(shortId("0123456789abcdef")).toBe("01234567");
  });
});
