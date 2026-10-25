import { describe, expect, it } from "vitest";
import { countText, emptyAreas, emptyLine, levelWord, searchText, type Coverage, type CoverageArea } from "./coverage-logic";

const area = (over: Partial<CoverageArea>): CoverageArea => ({
  id: 1, place: "Pakistan", label: "Pakistan", known: true, postings: 0, boards: 0, searches: [], searches_ready: 0, searches_waiting: 0, level: "none", tip: "", ...over,
});
const cov = (areas: CoverageArea[]): Coverage => ({ days: 30, areas, has_areas: areas.length > 0, empty_areas: 0, keys: { jooble: false, adzuna: false } });

describe("countText", () => {
  it("says what was counted and from how many sources", () => {
    expect(countText(area({ postings: 12, boards: 3, level: "ok" }), 30)).toBe("12 jobs listed in the last 30 days, from 3 job sources.");
    expect(countText(area({ postings: 1, boards: 1, level: "thin" }), 30)).toBe("1 job listed in the last 30 days, from 1 job source.");
  });
  it("says so when nothing is listed, and never counts a place it could not read", () => {
    expect(countText(area({}), 30)).toBe("No jobs listed in the last 30 days.");
    expect(countText(area({ known: false, level: "unknown" }), 30)).toMatch(/could not tell which country/);
  });
});

describe("searchText", () => {
  it("names the search and what it waits for", () => {
    const s = { name: "Jooble Pakistan", connector: "jooble", connector_label: "Jooble", ready: false, reason: "needs_key" as const };
    expect(searchText(s)).toBe("Jooble: switched off until the site owner adds a free key");
    expect(searchText({ ...s, reason: "needs_roles" })).toMatch(/add the roles you want/);
    expect(searchText({ ...s, ready: true, reason: "" })).toBe("Jooble: searches here with your next job search");
  });
});

describe("emptyLine", () => {
  it("is null when every place has something or the place is unknown", () => {
    expect(emptyLine(undefined)).toBeNull();
    expect(emptyLine(cov([area({ postings: 40, level: "ok" }), area({ id: 2, known: false, level: "unknown" }), area({ id: 3, postings: 3, level: "thin" })]))).toBeNull();
  });
  it("names one or two empty places and counts more", () => {
    expect(emptyLine(cov([area({})]))).toBe("Nothing lists jobs in Pakistan yet.");
    expect(emptyLine(cov([area({}), area({ id: 2, label: "Kenya" })]))).toBe("Nothing lists jobs in Pakistan or Kenya yet.");
    expect(emptyLine(cov([area({}), area({ id: 2, label: "Kenya" }), area({ id: 3, label: "Egypt" })]))).toBe("Nothing lists jobs in 3 of your places yet.");
    expect(emptyAreas(cov([area({}), area({ id: 2, postings: 50, level: "ok" })]))).toHaveLength(1);
  });
});

describe("levelWord", () => {
  it("uses plain words", () => {
    expect(levelWord(area({}))).toBe("No jobs yet");
    expect(levelWord(area({ level: "thin" }))).toBe("A few jobs");
    expect(levelWord(area({ level: "ok" }))).toBe("Well covered");
  });
});
