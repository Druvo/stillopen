import { describe, expect, it } from "vitest";
import type { ParsedFields } from "@/features/assist/extras-api";
import { fillFromParsed, filledMessage } from "./paste";

const fields = (over: Partial<ParsedFields> = {}): ParsedFields => ({ company: "Gamma", role: "Platform Engineer", location: "Remote within Bangladesh", pay: "$4000 per month", deadline: "2026-11-30", link: "https://g.example/jobs/1", ...over });
const blank = { company: "", role: "", url: "", deadline: "", description: "text", notes: "" };

describe("fillFromParsed", () => {
  it("fills every blank field and keeps place and pay in the notes", () => {
    const { values, filled } = fillFromParsed(blank, fields());
    expect(values).toMatchObject({ company: "Gamma", role: "Platform Engineer", url: "https://g.example/jobs/1", deadline: "2026-11-30" });
    expect(values.notes).toBe("Place: Remote within Bangladesh. Pay: $4000 per month");
    expect(filled).toEqual(["the company", "the role", "the link", "the apply-by date", "the place", "the pay"]);
  });

  it("never replaces what the person already typed", () => {
    const { values, filled } = fillFromParsed({ ...blank, company: "Mine Ltd", notes: "my note" }, fields());
    expect(values.company).toBe("Mine Ltd");
    expect(values.notes).toBe("my note");
    expect(filled).not.toContain("the company");
    expect(filled).not.toContain("the pay");
  });

  it("skips fields the reader left empty and does not touch the description", () => {
    const { values, filled } = fillFromParsed(blank, fields({ company: "", location: "", pay: "", link: "", deadline: "" }));
    expect(values.company).toBe("");
    expect(values.description).toBe("text");
    expect(filled).toEqual(["the role"]);
  });
});

describe("filledMessage", () => {
  it("lists what was filled in plain words and asks for a check", () => {
    expect(filledMessage(["the role"])).toBe("We filled in the role. Please check each one before you save.");
    expect(filledMessage(["the company", "the role", "the pay"])).toContain("the company, the role and the pay");
    expect(filledMessage(["the role"], "Written by AI.")).toContain("Written by AI.");
  });
  it("says what to do when nothing was found", () => {
    expect(filledMessage([])).toContain("Type them in");
  });
});
