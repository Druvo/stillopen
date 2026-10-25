import { describe, expect, it } from "vitest";
import { canCompare, compareHint, MAX_COMPARE, toggleOffer } from "./compare-logic";
import { defaultReferralJob } from "./referral";

describe("toggleOffer", () => {
  it("adds, removes and stops at four", () => {
    expect(toggleOffer([], 1)).toEqual([1]);
    expect(toggleOffer([1, 2], 1)).toEqual([2]);
    const four = [1, 2, 3, 4];
    expect(four.length).toBe(MAX_COMPARE);
    expect(toggleOffer(four, 5)).toEqual(four);
    expect(toggleOffer(four, 4)).toEqual([1, 2, 3]);
  });
});

describe("canCompare and compareHint", () => {
  it("needs two to four and says what to do next", () => {
    expect([0, 1, 2, 3, 4, 5].map((n) => canCompare(Array.from({ length: n }, (_, i) => i)))).toEqual([false, false, true, true, true, false]);
    expect(compareHint(0)).toContain("Tick two to four");
    expect(compareHint(1)).toContain("one more");
    expect(compareHint(2)).toBe("2 offers ticked.");
    expect(compareHint(4)).toContain("most");
  });
});

describe("defaultReferralJob", () => {
  const jobs = [
    { id: 7, label: "A" },
    { id: 9, label: "B" },
  ];
  const ref = (id: number) => ({ id: 1, job: { id, role: "r", company: "c" }, status: "asked", status_label: "Asked", note: "" });
  it("opens with the job of the contact's referral, else the first job, else nothing", () => {
    expect(defaultReferralJob({ referrals: [ref(9)] }, jobs)).toBe("9");
    expect(defaultReferralJob({ referrals: [ref(99)] }, jobs)).toBe("7");
    expect(defaultReferralJob({ referrals: [] }, jobs)).toBe("7");
    expect(defaultReferralJob({ referrals: [] }, [])).toBe("");
  });
});
