import { describe, expect, it } from "vitest";
import { fileSize, mergePrefill, postingsQuery, readPostingsQuery } from "./logic";

describe("postingsQuery", () => {
  it("is empty when nothing is set", () => {
    expect(postingsQuery({ q: "  ", source: "", page: 1 })).toBe("");
  });
  it("keeps only what is set", () => {
    expect(postingsQuery({ q: " python dev ", source: "3", page: 2 })).toBe("?q=python+dev&source=3&page=2");
  });
  it("round-trips through the address", () => {
    const state = { q: "c++ & more", source: "12", page: 4 };
    expect(readPostingsQuery(postingsQuery(state))).toEqual(state);
  });
  it("ignores broken values", () => {
    expect(readPostingsQuery("?source=abc&page=-2")).toEqual({ q: "", source: "", page: 1 });
    expect(readPostingsQuery("?page=1.5")).toEqual({ q: "", source: "", page: 1 });
  });
});

describe("fileSize", () => {
  it("speaks in KB and MB", () => {
    expect(fileSize(2 * 1024 * 1024)).toBe("2 MB");
    expect(fileSize(1.5 * 1024 * 1024)).toBe("1.5 MB");
    expect(fileSize(300)).toBe("1 KB");
    expect(fileSize(340 * 1024)).toBe("340 KB");
  });
});

describe("mergePrefill", () => {
  const prefill = { url: "https://x.example.com/1", role: "Dev", company: "Globex", description: "Text" };
  it("fills blanks", () => {
    expect(mergePrefill({ company: "", notes: "n" }, prefill)).toEqual({ company: "Globex", notes: "n", url: prefill.url, role: "Dev", description: "Text" });
  });
  it("never overwrites what was typed", () => {
    expect(mergePrefill({ company: "Mine", role: "Boss" }, prefill)).toMatchObject({ company: "Mine", role: "Boss", description: "Text" });
  });
  it("skips what the link did not give", () => {
    expect(mergePrefill({}, { ...prefill, company: "" })).not.toHaveProperty("company");
  });
});
