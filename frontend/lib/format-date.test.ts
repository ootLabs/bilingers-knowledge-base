import { describe, expect, it } from "vitest";

import { formatDateTime } from "./format-date";

describe("formatDateTime", () => {
  it("writes a date the way a person reads one", () => {
    const formatted = formatDateTime("2026-09-08T10:30:00Z");

    expect(formatted).toContain("2026");
    expect(formatted).toContain("wrze");
  });

  it("renders nothing rather than 'Invalid Date' for a broken value", () => {
    // A broken timestamp is worth showing nothing for. It must not turn a
    // working list into a screen full of English error text.
    expect(formatDateTime("nie data")).toBe("");
    expect(formatDateTime(null)).toBe("");
    expect(formatDateTime(undefined)).toBe("");
    expect(formatDateTime("")).toBe("");
  });
});
