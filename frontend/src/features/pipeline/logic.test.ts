import { describe, expect, it } from "vitest";
import { dayLabel, formatMoney, jobFromSearch, whenLabel } from "./logic";

describe("formatMoney", () => {
  it("keeps the currency it was given", () => {
    expect(formatMoney("100000.00", "USD")).toContain("100,000");
    expect(formatMoney("5000", "MYR")).toContain("5,000");
  });
  it("falls back to plain text for a code it does not know or a bad number", () => {
    expect(formatMoney("1200", "ZZZZ")).toBe("1,200 ZZZZ");
    expect(formatMoney("abc", "USD")).toBe("abc USD");
  });
});

describe("dates", () => {
  it("returns what it cannot read and nothing for blank", () => {
    expect(whenLabel("soon")).toBe("soon");
    expect(dayLabel("")).toBe("");
    expect(dayLabel("2026-11-03")).toContain("2026");
  });
});

describe("jobFromSearch", () => {
  const jobs = [{ id: 4 }, { id: 9 }];
  it("accepts only one of the person's own jobs", () => {
    expect(jobFromSearch("?job=9", jobs)).toBe("9");
    expect(jobFromSearch("?job=5", jobs)).toBe("");
    expect(jobFromSearch("", jobs)).toBe("");
  });
});
