import { describe, expect, it } from "vitest";
import { calendarTo, funnelSentence, goalLine, goalPercent, heatLevel, heatText, heatWeeks, monthGrid, moveDay, shiftMonth, stageShare, streakLine } from "./viz-logic";

describe("funnel text", () => {
  it("shares only against a stage that has people", () => {
    expect(stageShare(3, 10)).toBe("3 of 10 (30%)");
    expect(stageShare(0, 0)).toBe("0");
    expect(stageShare(5, null)).toBe("5");
  });
  it("says it in a sentence per period", () => {
    const f = { since: null, stages: [{ key: "a", label: "", count: 1 }, { key: "b", label: "", count: 1 }, { key: "c", label: "", count: 0 }, { key: "d", label: "", count: 0 }] };
    expect(funnelSentence(f, "30")).toBe("Of 1 application sent in the last 30 days, 1 heard back, 0 reached an interview and 0 got an offer.");
    expect(funnelSentence(f, "all")).toContain("sent so far");
  });
});

describe("heatmap", () => {
  it("scales colour steps to the busiest day and keeps one as at least step 1", () => {
    expect(heatLevel(0, 8)).toBe(0);
    expect(heatLevel(1, 8)).toBe(1);
    expect(heatLevel(8, 8)).toBe(4);
    expect(heatLevel(3, 0)).toBe(0);
  });
  it("lays days out in Monday-first weeks, blank outside the range", () => {
    // 2026-10-25 is a Sunday; 2026-10-26 a Monday
    const weeks = heatWeeks({ start: "2026-10-22", end: "2026-10-27", days: { "2026-10-25": { applied: 2, interviews: 1 } } });
    expect(weeks).toHaveLength(2);
    expect(weeks[0].map((c) => c?.date ?? null)).toEqual([null, null, null, "2026-10-22", "2026-10-23", "2026-10-24", "2026-10-25"]);
    expect(weeks[0][6]).toMatchObject({ total: 3, level: 4 });
    expect(weeks[1][0]?.date).toBe("2026-10-26");
    expect(weeks[1][2]).toBeNull();
  });
  it("handles an empty year", () => {
    const weeks = heatWeeks({ start: "2026-01-01", end: "2026-01-07", days: {} });
    expect(weeks.flat().every((c) => c === null || c.level === 0)).toBe(true);
  });
  it("describes a day as text", () => {
    expect(heatText({ date: "2026-10-25", applied: 1, interviews: 2 })).toBe("2026-10-25: 1 application, 2 interviews");
  });
});

describe("goals", () => {
  it("never passes 100 and is off without a target", () => {
    expect(goalPercent(1, 4)).toBe(25);
    expect(goalPercent(9, 4)).toBe(100);
    expect(goalPercent(3, 0)).toBe(0);
  });
  it("uses plain, kind words", () => {
    expect(goalLine(2, 3, "Today")).toBe("Today: 2 of 3.");
    expect(goalLine(3, 3, "Today")).toContain("Goal reached");
    expect(goalLine(1, 0, "Today")).toBe("");
    expect(streakLine({ current_streak: 0, best_streak: 0 })).toContain("starts");
    expect(streakLine({ current_streak: 1, best_streak: 4 })).toBe("Current streak: 1 day in a row. Best: 4 days.");
    expect(streakLine({ current_streak: 0, best_streak: 4 })).not.toMatch(/lost|broke|missed/i);
  });
});

describe("calendar", () => {
  it("builds Monday-first rows", () => {
    const rows = monthGrid({ first: "2026-10-01", last: "2026-10-31", weekday_of_first: 3 });
    expect(rows[0]).toEqual([null, null, null, "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]);
    expect(rows.at(-1)?.[5]).toBe("2026-10-31");
    expect(rows.every((r) => r.length === 7)).toBe(true);
  });
  it("moves between months and across the year", () => {
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
  });
  it("moves with the arrow keys and stays inside the month", () => {
    expect(moveDay("2026-10-10", "ArrowRight", "2026-10-01", "2026-10-31")).toBe("2026-10-11");
    expect(moveDay("2026-10-10", "ArrowDown", "2026-10-01", "2026-10-31")).toBe("2026-10-17");
    expect(moveDay("2026-10-01", "ArrowLeft", "2026-10-01", "2026-10-31")).toBe("2026-10-01");
    expect(moveDay("2026-10-30", "ArrowDown", "2026-10-01", "2026-10-31")).toBe("2026-10-30");
    expect(moveDay("2026-10-10", "x", "2026-10-01", "2026-10-31")).toBe("2026-10-10");
  });
  it("links each kind to its place", () => {
    const base = { date: "", when: "", label: "", company: "", role: "", job_id: 7 };
    expect(calendarTo({ ...base, kind: "interview" })).toBe("/interviews");
    expect(calendarTo({ ...base, kind: "offer" })).toBe("/offers");
    expect(calendarTo({ ...base, kind: "followup" })).toBe("/jobs/7/apply");
  });
});
