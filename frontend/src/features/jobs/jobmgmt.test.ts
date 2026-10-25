import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api";
import { confidenceText, duplicateMessage, duplicateOf, importHeadline, moveText, sourceHealthText, statusWord, suggestionButton, troubleLine } from "./jobmgmt";

const NOW = new Date("2026-10-25T12:00:00Z");

describe("the same job twice", () => {
  it("reads the duplicate out of a 409 and nothing else", () => {
    const err = new ApiError("You already track X.", 409, {}, { duplicate: { id: 5, company: "Acme", role: "Dev", status: "Applied" } });
    expect(duplicateOf(err)).toEqual({ id: 5, company: "Acme", role: "Dev", status: "Applied" });
    expect(duplicateOf(new ApiError("no", 400, {}, { duplicate: { id: 5 } }))).toBeNull();
    expect(duplicateOf(new ApiError("no", 409, {}, {}))).toBeNull();
    expect(duplicateOf(new Error("boom"))).toBeNull();
  });
  it("says it in plain words", () => {
    expect(duplicateMessage({ company: "Acme", role: "Senior Backend Engineer", status: "Applied" })).toBe("You already track Senior Backend Engineer at Acme (Applied).");
    expect(duplicateMessage({ company: "Acme", role: "Dev", status: "" })).toBe("You already track Dev at Acme.");
  });
});

describe("statuses and replies", () => {
  it("uses the friendly label when there is one", () => {
    expect(statusWord({ name: "Evaluated", label: "Checked" })).toBe("Checked");
    expect(statusWord({ name: "Applied" })).toBe("Applied");
    expect(suggestionButton({ id: 1, name: "Rejected", label: "Rejected", bucket_key: "closed" })).toBe("Set status to Rejected");
    expect(moveText("Interview")).toBe("Move this job to Interview?");
  });
  it("says how sure the reading is", () => {
    expect(confidenceText("clear")).toMatch(/clear/);
    expect(confidenceText("probably")).toMatch(/probably/);
    expect(confidenceText("unsure")).toMatch(/not sure/);
    expect(confidenceText("clear", true)).toMatch(/two things/);
  });
});

describe("the spreadsheet import", () => {
  it("sums up a preview and a finished import", () => {
    const base = { preview: true, will_add: 3, skipped_count: 0, problem_count: 0 };
    expect(importHeadline(base)).toBe("3 jobs will be added.");
    expect(importHeadline({ ...base, will_add: 1, skipped_count: 2, problem_count: 1 })).toBe("1 job will be added, 2 rows skipped because you already track them, 1 row could not be read.");
    expect(importHeadline({ preview: false, will_add: 3, added: 3, skipped_count: 1, problem_count: 0 })).toBe("Added 3 jobs, 1 row skipped because you already track it.");
  });
});

describe("how a board answered", () => {
  const ok = { state: "ok" as const, checked_at: "2026-10-25T10:00:00Z", last_ok_at: "2026-10-25T10:00:00Z", error: "", since: null };
  it("worked, not answering and unknown", () => {
    expect(sourceHealthText(ok, NOW)).toBe("Worked 2 hours ago.");
    expect(sourceHealthText({ ...ok, state: "error", error: "HTTP 500", since: "2026-10-21T08:00:00Z" }, NOW)).toBe("Not answering since 21 Oct: HTTP 500");
    expect(sourceHealthText({ state: "unknown", checked_at: null, last_ok_at: null, error: "", since: null }, NOW)).toBe("Not searched yet.");
  });
  it("the dashboard line only appears when something went wrong", () => {
    expect(troubleLine({ total: 112, trouble: 2 })).toBe("2 of 112 sources had trouble in the last search.");
    expect(troubleLine({ total: 112, trouble: 0 })).toBe("");
    expect(troubleLine(null)).toBe("");
    expect(troubleLine({ total: 1, trouble: 1 })).toBe("1 of 1 source had trouble in the last search.");
  });
});
