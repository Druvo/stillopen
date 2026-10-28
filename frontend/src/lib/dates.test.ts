import { describe, expect, it } from "vitest";
import { dayText, dayTimeText } from "./dates";

describe("dates", () => {
  it("writes a day the same way everywhere", () => {
    expect(dayText("2026-09-29")).toBe("29 Sep 2026");
    expect(dayText("2026-01-05T23:59:00Z")).toBe("5 Jan 2026");
  });
  it("leaves anything else alone", () => {
    expect(dayText("")).toBe("");
    expect(dayText(null)).toBe("");
    expect(dayText("soon")).toBe("soon");
    expect(dayText("2026-13-01")).toBe("2026-13-01");
    expect(dayTimeText("soon")).toBe("soon");
  });
  it("adds the weekday and the time", () => {
    expect(dayTimeText("2026-11-03T14:30")).toBe("Tue 3 Nov 2026, 14:30");
  });
});
