import { describe, expect, it } from "vitest";
import { availableEntries, ENTRIES, filterEntries, GO_TO, isTyping, readKey } from "./palette";

const key = (k: string, extra: Partial<{ metaKey: boolean; ctrlKey: boolean; altKey: boolean; target: EventTarget | null }> = {}) => ({ key: k, metaKey: false, ctrlKey: false, altKey: false, target: null, ...extra });

describe("filtering the palette", () => {
  it("shows everything for an empty word", () => {
    expect(filterEntries(ENTRIES, "  ")).toHaveLength(ENTRIES.length);
  });
  it("finds a screen by the start of a word, in any case", () => {
    expect(filterEntries(ENTRIES, "INT").map((e) => e.id)).toContain("interviews");
    expect(filterEntries(ENTRIES, "ques")[0].id).toBe("questions");
  });
  it("finds a screen by an extra word", () => {
    expect(filterEntries(ENTRIES, "resume").map((e) => e.id)).toContain("cv");
  });
  it("needs every word, and finds nothing for a word that matches nothing", () => {
    expect(filterEntries(ENTRIES, "job sources").map((e) => e.id)).toContain("sources");
    expect(filterEntries(ENTRIES, "zzzz")).toEqual([]);
  });
  it("puts a label that starts with the word before one that only mentions it", () => {
    const ids = filterEntries(ENTRIES, "ai").map((e) => e.id);
    expect(ids.indexOf("ai")).toBeLessThan(ids.indexOf("usage"));
  });
  it("leaves out what the admin switched off, but shows everything until /me has answered", () => {
    expect(availableEntries({ prep_enabled: false, assistant_enabled: true }).some((e) => e.id === "prep")).toBe(false);
    expect(availableEntries({ prep_enabled: false }).some((e) => e.id === "assistant")).toBe(true);
    expect(availableEntries(undefined)).toHaveLength(ENTRIES.length);
  });
  it("offers the safe actions and every screen asked for", () => {
    const labels = ENTRIES.map((e) => e.label);
    for (const l of ["Add job", "Search for jobs now", "Dashboard", "All postings", "CVs", "Interviews", "Contacts", "Offers", "Insights", "Companies", "Question bank", "Prep plans", "Notifications", "Your profile", "AI settings", "Help"]) {
      expect(labels).toContain(l);
    }
  });
});

describe("keys", () => {
  it("opens the palette with Ctrl/Cmd+K even while typing, and with /", () => {
    const input = document.createElement("input");
    expect(readKey(key("k", { ctrlKey: true, target: input }), false, false)).toEqual({ open: "palette" });
    expect(readKey(key("K", { metaKey: true }), false, false)).toEqual({ open: "palette" });
    expect(readKey(key("/"), false, false)).toEqual({ open: "palette" });
  });
  it("opens the help with ?", () => {
    expect(readKey(key("?"), false, false)).toEqual({ open: "shortcuts" });
  });
  it("never reacts to a letter typed into a field, or with a dialog open", () => {
    const area = document.createElement("textarea");
    expect(readKey(key("?", { target: area }), false, false)).toBeNull();
    expect(readKey(key("g", { target: area }), false, false)).toBeNull();
    expect(readKey(key("?"), false, true)).toBeNull();
    expect(isTyping(document.createElement("div"))).toBe(false);
  });
  it("g then a letter goes to a screen; anything else is ignored", () => {
    expect(readKey(key("g"), false, false)).toEqual({ waitForGo: true });
    expect(readKey(key("d"), true, false)).toEqual({ go: "/" });
    expect(readKey(key("c"), true, false)).toEqual({ go: "/cv" });
    expect(readKey(key("x"), true, false)).toBeNull();
    expect(Object.keys(GO_TO)).toEqual(expect.arrayContaining(["d", "j", "c", "i"]));
  });
  it("ignores browser shortcuts such as Ctrl+G", () => {
    expect(readKey(key("g", { ctrlKey: true }), false, false)).toBeNull();
  });
});
