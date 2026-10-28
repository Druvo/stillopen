import { describe, expect, it } from "vitest";
import { checklistSteps, showChecklist } from "./checklist";

type D = Parameters<typeof checklistSteps>[0];
const base = { search_summary: { roles: [], has_cv: false }, jobs: [], scan: null, checked_at: null, stats: { total: 0 } } as unknown as D;
const with_ = (patch: object) => ({ ...base, ...patch }) as D;

describe("getting-started checklist", () => {
  it("starts with nothing done", () => {
    const steps = checklistSteps(base);
    expect(steps.map((s) => s.done)).toEqual([false, false, false, false, false]);
    expect(showChecklist(steps, false)).toBe(true);
  });
  it("ticks each step from the dashboard's own data", () => {
    const steps = checklistSteps(
      with_({ search_summary: { roles: ["Engineer"], has_cv: true }, scan: { finished_at: "2026-01-01" }, jobs: [{ id: 1, evaluated: false, percent: 80 }] }),
    );
    expect(steps.map((s) => [s.key, s.done])).toEqual([["roles", true], ["cv", true], ["search", true], ["job", true], ["fit", true]]);
  });
  it("hides at three done, and when closed", () => {
    const three = checklistSteps(with_({ search_summary: { roles: ["x"], has_cv: true }, jobs: [{ id: 1, evaluated: false, percent: null }] }));
    expect(three.filter((s) => s.done)).toHaveLength(3);
    expect(showChecklist(three, false)).toBe(false);
    expect(showChecklist(checklistSteps(base), true)).toBe(false);
  });
});
