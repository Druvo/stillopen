import { describe, expect, it } from "vitest";
import { importLines } from "./data-import-logic";

const base = { preview: true, nothing: true, left_out: 0, profile: { filled: [], kept: [] }, cvs: { add: 0, have: 0, left_out: 0, stopped: "" }, covers: { add: 0, have: 0, no_job: 0, stopped: "" }, notes: { add: 0, have: 0, kept: 0, no_job: 0 } };

describe("importLines", () => {
  it("says so when nothing is missing", () => {
    expect(importLines(base)).toEqual(["This file has nothing that is missing from your account."]);
  });
  it("names what would be added and kept", () => {
    const lines = importLines({ ...base, nothing: false, profile: { filled: ["about you"], kept: ["home country"] }, cvs: { ...base.cvs, add: 1 }, notes: { ...base.notes, kept: 2 } });
    expect(lines.join(" ")).toMatch(/about you/);
    expect(lines.join(" ")).toMatch(/1 CV version to add/);
    expect(lines.join(" ")).toMatch(/2 job notes different/);
  });
});
