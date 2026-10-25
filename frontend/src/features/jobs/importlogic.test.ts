import { describe, expect, it } from "vitest";
import type { EmailPreview, EmailRow } from "./api";
import { blockedNote, careerPageLine, doneMessage, fileCountsLine, hostOfPage, initiallyOff, isLinkedinFile, LINKEDIN_BLOCKED_NOTE, previewHeadline, rowNotes, ticked } from "./importlogic";

const row = (index: number, extra: Partial<EmailRow> = {}): EmailRow => ({
  index, title: `Role ${index}`, company: "Acme", location: "", salary: "", url: "", problems: [], duplicate: null, importable: true, ...extra,
});
const dup = { id: 3, company: "Acme", role: "Role 1", status: "Saved" };

describe("email import helpers", () => {
  const preview: EmailPreview = { preview: true, found: 3, will_add: 2, problems: [], rows: [row(0), row(1, { duplicate: dup, importable: false }), row(2)] };
  it("leaves tracked jobs unticked and returns the ticked numbers", () => {
    const off = initiallyOff(preview);
    expect([...off]).toEqual([1]);
    expect(ticked(preview.rows, off)).toEqual([0, 2]);
    off.add(2);
    expect(ticked(preview.rows, off)).toEqual([0]);
  });
  it("says what was found in plain words", () => {
    expect(previewHeadline(preview)).toBe("3 jobs found, 1 job you already track.");
    expect(previewHeadline({ ...preview, found: 0, rows: [] })).toBe("We did not find any jobs in that.");
  });
  it("reports what was added", () => {
    expect(doneMessage({ preview: false, added: 1, skipped_count: 2, skipped: [], stopped: "", found: 3, problems: [] })).toBe("Added 1 job, 2 jobs skipped because you already track them.");
    expect(doneMessage({ preview: false, added: 0, skipped_count: 0, skipped: [], stopped: "You have reached the limit of 5 tracked jobs. Delete some first.", found: 3, problems: [] })).toContain("limit of 5");
  });
  it("lists the duplicate first, then the row's own problems", () => {
    expect(rowNotes(row(1, { duplicate: dup, problems: ["No link: you will need to open it on LinkedIn to apply."] }))).toEqual([
      "You already track Role 1 at Acme (Saved).",
      "No link: you will need to open it on LinkedIn to apply.",
    ]);
  });
});

describe("LinkedIn data helpers", () => {
  it("counts per file", () => {
    expect(fileCountsLine({ name: "Saved Jobs.csv", kind: "saved", label: "Saved Jobs", found: 12, new: 10, duplicates: 2, unreadable: 1 })).toBe("Saved Jobs: 12 found, 10 new, 2 already tracked, 1 row could not be read");
  });
  it("accepts the zip or a csv only", () => {
    expect(isLinkedinFile("Complete_LinkedInDataExport.ZIP")).toBe(true);
    expect(isLinkedinFile("Saved Jobs.csv")).toBe(true);
    expect(isLinkedinFile("notes.pdf")).toBe(false);
  });
});

describe("blocked links and careers pages", () => {
  it("uses the server's words, with the plain fallback", () => {
    expect(blockedNote("linkedin", undefined)).toBe(LINKEDIN_BLOCKED_NOTE);
    expect(blockedNote("indeed", "Indeed says no.")).toBe("Indeed says no.");
    expect(blockedNote(undefined, "x")).toBe("");
    expect(LINKEDIN_BLOCKED_NOTE).toContain("select the description, copy and paste it below");
  });
  it("shows the host of a careers page", () => {
    expect(hostOfPage("https://careers.example.com/jobs?x=1")).toBe("careers.example.com");
    expect(careerPageLine("https://careers.example.com/jobs")).toBe("Careers page on careers.example.com");
    expect(hostOfPage("not a url")).toBe("not a url");
  });
});
