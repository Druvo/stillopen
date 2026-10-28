import { describe, expect, it } from "vitest";
import { acceptAll, applyCards, canFill, initialDecisions, pendingCount, startStep, summaryText, type ImportCard } from "./importlogic";
import { emptyAnswers } from "./quality";

const card = (key: string, step: number, found: boolean, patch: object = {}): ImportCard => ({ key, label: key, step, found, preview: found ? ["x"] : [], more: 0, patch });
const cards = [
  card("contact", 0, true, { name: "Priya", email: "p@example.com", links: [] }),
  card("experience", 2, true, { roles: [{ title: "Dev", company: "Acme", location: "", start: "2021", end: "Present", bullets: ["Built"] }] }),
  card("certificates", 7, false, { certificates: "" }),
];

describe("review decisions", () => {
  it("starts with found sections pending and missing ones skipped", () => {
    expect(initialDecisions(cards)).toEqual({ contact: "pending", experience: "pending", certificates: "skip" });
  });
  it("needs every found section decided and at least one taken", () => {
    const d = initialDecisions(cards);
    expect(canFill(d)).toBe(false);
    expect(pendingCount(d)).toBe(2);
    expect(summaryText(d)).toBe("2 sections still to decide");
    expect(canFill({ ...d, contact: "skip", experience: "skip" })).toBe(false);
    expect(canFill({ ...d, contact: "accept", experience: "edit" })).toBe(true);
  });
  it("accepts everything that was found", () => {
    const d = acceptAll(cards);
    expect(d).toEqual({ contact: "accept", experience: "accept", certificates: "skip" });
    expect(summaryText(d)).toBe("2 sections will fill the builder");
  });
});

describe("applyCards", () => {
  it("puts in only the taken sections and keeps the rest of the draft", () => {
    const base = { ...emptyAnswers(), summary: "kept" };
    const out = applyCards(base, cards, { contact: "accept", experience: "skip", certificates: "skip" });
    expect(out.name).toBe("Priya");
    expect(out.summary).toBe("kept");
    expect(out.roles[0].title).toBe("");
  });
  it("keeps the lists the builder shows non-empty and gives each job room for three bullets", () => {
    const out = applyCards(emptyAnswers(), cards, acceptAll(cards));
    expect(out.links).toEqual([""]);
    expect(out.roles[0].bullets).toEqual(["Built", "", ""]);
    expect(out.education.length).toBe(1);
  });
  it("does not shorten a job that has more than three bullets", () => {
    const many = card("experience", 2, true, { roles: [{ title: "a", company: "b", location: "", start: "2020", end: "", bullets: ["1", "2", "3", "4", "5"] }] });
    expect(applyCards(emptyAnswers(), [many], { experience: "accept" }).roles[0].bullets).toHaveLength(5);
  });
});

describe("startStep", () => {
  it("opens at the first section to edit, or at the start", () => {
    expect(startStep(cards, { contact: "accept", experience: "edit", certificates: "skip" })).toBe(2);
    expect(startStep(cards, acceptAll(cards))).toBe(0);
  });
});
