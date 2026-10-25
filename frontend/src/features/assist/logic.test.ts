import { describe, expect, it } from "vitest";
import type { InterviewPrep, PostingSummary } from "./api";
import { addRole, canAsk, findingsText, hasRole, messageText, prepText, starMissing, statements } from "./logic";

describe("addRole", () => {
  it("adds a role on a new line", () => {
    expect(addRole("Backend Engineer\n", "Data Engineer")).toBe("Backend Engineer\nData Engineer");
    expect(addRole("", "Data Engineer")).toBe("Data Engineer");
  });
  it("does not add a role twice, ignoring case and spaces", () => {
    expect(addRole("Data Engineer", " data engineer ")).toBe("Data Engineer");
    expect(hasRole("A\nB", "b")).toBe(true);
  });
  it("ignores an empty role", () => {
    expect(addRole("A", "  ")).toBe("A");
  });
});

describe("copy texts", () => {
  const prep: InterviewPrep = {
    job: { id: 1, role: "Dev", company: "Acme" }, generated_at: "", notice: "", outline_note: "", dropped_points: 0,
    groups: [
      { key: "role", title: "About the role", questions: [{ id: "role-1", question: "Why us?", testing: "Motivation.", outline: ["Mention the API."], flags: [] }] },
      { key: "probe", title: "Probing", questions: [] },
    ],
  };
  it("lists each group with its questions and skips empty groups", () => {
    const text = prepText(prep);
    expect(text).toContain("About the role");
    expect(text).toContain("What they are really testing: Motivation.");
    expect(text).toContain("- Mention the API.");
    expect(text).not.toContain("Probing");
  });
  it("puts the subject first in a message", () => {
    expect(messageText({ subject: "Hi", body: "Body" })).toBe("Subject: Hi\n\nBody");
  });
});

describe("feedback helpers", () => {
  it("names the missing STAR parts", () => {
    expect(starMissing({ situation: true, task: false, action: true, result: false })).toEqual(["your task", "the result"]);
    expect(starMissing({ situation: true, task: true, action: true, result: true })).toEqual([]);
  });
  it("lists flagged words once", () => {
    expect(findingsText([{ kind: "name", text: "Initech", line: 1 }, { kind: "number", text: "300", line: 1 }, { kind: "name", text: "Initech", line: 2 }])).toBe("Initech, 300");
  });
  it("needs a few words before asking", () => {
    expect(canAsk("one two", 5)).toBe(false);
    expect(canAsk("one two three four five", 5)).toBe(true);
  });
});

describe("statements", () => {
  const summary = { seniority: "Senior", pay: "", visa: "No sponsorship", relocation: "", remote: "Remote", deadline: " " } as PostingSummary;
  it("keeps only what the posting says, in a fixed order", () => {
    expect(statements(summary)).toEqual([
      { label: "Level", text: "Senior" },
      { label: "Visa", text: "No sponsorship" },
      { label: "Where", text: "Remote" },
    ]);
  });
});
