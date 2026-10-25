import { describe, expect, it } from "vitest";
import { diffCounts, diffSummary, findingText, parseBlocks, parseInline, type DiffRow } from "./logic";

describe("parseBlocks", () => {
  it("reads headings, bullets, rules and paragraphs and skips blank lines", () => {
    const blocks = parseBlocks("# Jane\n\n## Skills\n- C#\n* SQL\n---\nPlain line");
    expect(blocks.map((b) => b.kind)).toEqual(["h1", "h2", "li", "li", "hr", "p"]);
    expect(blocks[3].text).toBe("SQL");
  });
  it("keeps markup-looking text as plain text", () => {
    expect(parseBlocks("<script>alert(1)</script>")).toEqual([{ kind: "p", text: "<script>alert(1)</script>" }]);
  });
});

describe("parseInline", () => {
  it("finds bold, italic and web links", () => {
    expect(parseInline("a **b** *c* [d](https://example.com/x) e")).toEqual([
      { kind: "text", text: "a " },
      { kind: "strong", text: "b" },
      { kind: "text", text: " " },
      { kind: "em", text: "c" },
      { kind: "text", text: " " },
      { kind: "link", text: "d", href: "https://example.com/x" },
      { kind: "text", text: " e" },
    ]);
  });
  it("never makes a link out of a javascript address", () => {
    expect(parseInline("[x](javascript:alert(1))")).toEqual([{ kind: "text", text: "[x](javascript:alert(1))" }]);
  });
});

describe("diff helpers", () => {
  const rows: DiffRow[] = [
    { tag: "same", text: "a" },
    { tag: "del", text: "b" },
    { tag: "add", text: "c" },
    { tag: "add", text: "d" },
  ];
  it("counts and describes", () => {
    expect(diffCounts(rows)).toEqual({ added: 2, removed: 1, same: 1 });
    expect(diffSummary(rows)).toBe("2 lines added, 1 line removed.");
    expect(diffSummary([{ tag: "same", text: "a" }])).toBe("These two versions are the same.");
  });
});

describe("findingText", () => {
  it("speaks plainly", () => {
    expect(findingText({ kind: "number", text: "500", line: 1 })).toBe("Number 500");
    expect(findingText({ kind: "gap", text: "AWS", line: 0 })).toContain("never mentions");
  });
});
