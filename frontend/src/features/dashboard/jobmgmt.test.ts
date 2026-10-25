import { describe, expect, it } from "vitest";
import type { Job, StatusInfo } from "@/lib/types";
import { DEFAULT_FILTERS, filtersFromPrefs, hiddenWeakCount, isFiltered, isWeak, patchFromFilters, visibleJobs, activeFilterCount } from "./logic";
import { DEFAULT_PREFERENCES } from "@/lib/preferences";
import {
  allSelected, movedText, notForMeStatus, pruneSelection, removedText, selectAllIn, selectedText, statusLabel, toggleId, undoText, weakLine,
} from "./jobmgmt";

const job = (id: number, percent: number | null, extra: Partial<Job> = {}): Job =>
  ({ id, company: "Acme", role: `Role ${id}`, percent, bucket_key: "apply", location: "", country_name: "", country: "", arrangement: "", found_date: "2026-10-20", live_state: "unknown", fit_level: "", deadline: null, band: null, ...extra }) as Job;

const status = (id: number, name: string, extra: Partial<StatusInfo> = {}): StatusInfo => ({ id, name, bucket_key: "closed", color: "#000", counts_as_applied: false, ...extra });

describe("hide weak matches", () => {
  const list = [job(1, 90), job(2, 39), job(3, 40), job(4, null), job(5, 0)];
  it("a weak match is under 40 and an unchecked job is never weak", () => {
    expect(list.map(isWeak)).toEqual([false, true, false, false, true]);
  });
  it("leaves them out only when switched on, and always keeps unchecked jobs", () => {
    expect(visibleJobs(list, DEFAULT_FILTERS).map((j) => j.id)).toEqual([1, 2, 3, 4, 5]);
    expect(visibleJobs(list, { ...DEFAULT_FILTERS, hideWeak: true }).map((j) => j.id)).toEqual([1, 3, 4]);
  });
  it("counts what it hides, together with the other filters", () => {
    expect(hiddenWeakCount(list, { ...DEFAULT_FILTERS, hideWeak: true })).toBe(2);
    expect(hiddenWeakCount(list, DEFAULT_FILTERS)).toBe(0);
    expect(hiddenWeakCount(list, { ...DEFAULT_FILTERS, hideWeak: true, q: "role 2" })).toBe(1);
  });
  it("is saved with the preferences and counts as a filter that is on", () => {
    expect(patchFromFilters({ hideWeak: true }, DEFAULT_FILTERS)).toEqual({ hide_weak: true });
    expect(filtersFromPrefs({ ...DEFAULT_PREFERENCES, hide_weak: true }).hideWeak).toBe(true);
    expect(filtersFromPrefs(DEFAULT_PREFERENCES).hideWeak).toBe(false);
    expect(isFiltered({ ...DEFAULT_FILTERS, hideWeak: true })).toBe(true);
    expect(activeFilterCount({ ...DEFAULT_FILTERS, hideWeak: true })).toBe(1);
  });
  it("says how many are hidden", () => {
    expect(weakLine(0)).toBe("");
    expect(weakLine(1)).toBe("1 weak match is hidden (under 40%).");
    expect(weakLine(5)).toBe("5 weak matches are hidden (under 40%).");
  });
});

describe("choosing several jobs", () => {
  it("toggles one without touching the others", () => {
    const a = new Set([1]);
    expect([...toggleId(a, 2)]).toEqual([1, 2]);
    expect([...toggleId(new Set([1, 2]), 1)]).toEqual([2]);
    expect([...a]).toEqual([1]);
  });
  it("selects all of the list, not only what is drawn", () => {
    const list = [job(1, 1), job(2, 2), job(3, 3)];
    expect([...selectAllIn(list)]).toEqual([1, 2, 3]);
    expect(allSelected(new Set([1, 2, 3]), list)).toBe(true);
    expect(allSelected(new Set([1, 2]), list)).toBe(false);
    expect(allSelected(new Set(), [])).toBe(false);
  });
  it("forgets jobs that left the list", () => {
    expect([...pruneSelection(new Set([1, 2, 9]), [job(1, 1), job(2, 2)])]).toEqual([1, 2]);
  });
  it("words", () => {
    expect(selectedText(0)).toBe("Choose the jobs you want to act on.");
    expect(selectedText(3)).toBe("3 selected");
    expect(movedText(1, "Not for me", "Backend Engineer")).toBe("Moved Backend Engineer to Not for me.");
    expect(movedText(3, "Not for me")).toBe("Moved 3 jobs to Not for me.");
    expect(undoText(1, "Not for me", "Dev")).toBe("Dev is now Not for me.");
    expect(undoText(3, "Applied")).toBe("3 jobs are now Applied.");
    expect(removedText(1, "Dev")).toBe("Removed Dev.");
    expect(removedText(2)).toBe("Removed 2 jobs.");
  });
});

describe("the not-for-me status and labels", () => {
  it("is found by name, with the old name as a fallback", () => {
    expect(notForMeStatus([status(1, "Skipped"), status(2, "Not for me")])?.id).toBe(2);
    expect(notForMeStatus([status(1, "Skipped"), status(3, "Discarded")])?.id).toBe(3);
    expect(notForMeStatus([status(1, "Evaluated", { bucket_key: "apply" })])).toBeUndefined();
  });
  it("shows the friendly label when there is one", () => {
    expect(statusLabel({ name: "Evaluated", label: "Checked" })).toBe("Checked");
    expect(statusLabel({ name: "Applied" })).toBe("Applied");
    expect(statusLabel(undefined)).toBe("its new status");
  });
});
