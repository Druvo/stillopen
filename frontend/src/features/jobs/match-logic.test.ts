import { describe, expect, it } from "vitest";
import { matchMark, strengthText } from "./match-logic";

describe("match marks", () => {
  it("says it in words as well as a symbol", () => {
    expect(matchMark("covered")).toMatchObject({ icon: "✓", words: "Covered" });
    expect(matchMark("gap").words).toMatch(/not shown/i);
    expect(matchMark("unchecked").words).toMatch(/not checked/i);
  });
  it("reads the strength plainly", () => {
    expect(strengthText(40)).toBe("Your profile is 40% ready for matching.");
  });
});
