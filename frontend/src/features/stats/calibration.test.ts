import { describe, expect, it } from "vitest";
import { calibrationLine, calibrationWaiting } from "./logic";

describe("match and replies", () => {
  it("says each band in plain words", () => {
    expect(calibrationLine({ label: "Strong", applied: 6, replies: 3, reply_rate: 50 })).toBe("Strong: 6 applied, 3 got a reply (50%).");
    expect(calibrationLine({ label: "Fair", applied: 1, replies: 1, reply_rate: 100 })).toBe("Fair: 1 applied, 1 got a reply (100%).");
    expect(calibrationLine({ label: "A stretch", applied: 4, replies: 0, reply_rate: 0 })).toBe("A stretch: 4 applied, none got a reply (0%).");
    expect(calibrationLine({ label: "Fair", applied: 0, replies: 0, reply_rate: null })).toBe("Fair: you did not apply to any.");
  });
  it("tells the person what to do while there is too little to show", () => {
    const text = calibrationWaiting({ scored: 3, needed: 8 });
    expect(text).toContain("8 jobs");
    expect(text).toContain("You have 3 so far, 5 to go.");
    expect(text).toContain("Check my fit");
  });
});
