import { describe, expect, it } from "vitest";
import { allZones, canonicalZone, effectiveZone, isZoneName, shouldSuggestZone, withoutTimezone } from "./timezone";

describe("time zone helpers", () => {
  it("knows real zone names and refuses made-up ones", () => {
    expect(isZoneName("Asia/Dhaka")).toBe(true);
    expect(isZoneName("America/Los_Angeles")).toBe(true);
    expect(isZoneName("Mars/Olympus")).toBe(false);
    expect(isZoneName("")).toBe(false);
  });

  it("puts the common zones first and adds the rest once", () => {
    const zones = allZones(["Asia/Dhaka", "UTC"]);
    expect(zones.slice(0, 2)).toEqual(["Asia/Dhaka", "UTC"]);
    expect(zones.filter((z) => z === "Asia/Dhaka")).toHaveLength(1);
  });

  it("uses the person's zone, else the site's", () => {
    expect(effectiveZone("Asia/Tokyo", "Asia/Dhaka")).toBe("Asia/Tokyo");
    expect(effectiveZone("", "Asia/Dhaka")).toBe("Asia/Dhaka");
  });

  it("suggests the device zone only when it really differs", () => {
    const base = { device: "America/Los_Angeles", saved: "", site: "Asia/Dhaka", dismissed: false };
    expect(shouldSuggestZone(base)).toBe(true);
    expect(shouldSuggestZone({ ...base, dismissed: true })).toBe(false);
    expect(shouldSuggestZone({ ...base, saved: "America/Los_Angeles" })).toBe(false);
    expect(shouldSuggestZone({ ...base, device: "Asia/Dhaka" })).toBe(false);
    expect(shouldSuggestZone({ ...base, device: "" })).toBe(false);
    expect(shouldSuggestZone({ ...base, device: "Not/AZone" })).toBe(false);
  });

  it("treats two spellings of the same place as the same zone", () => {
    expect(canonicalZone("Asia/Calcutta")).toBe(canonicalZone("Asia/Kolkata"));
    expect(shouldSuggestZone({ device: "Asia/Calcutta", saved: "Asia/Kolkata", site: "Asia/Dhaka", dismissed: false })).toBe(false);
  });

  it("leaves the zone out of the profile form's payload", () => {
    expect(withoutTimezone({ about: "hi", timezone: "Asia/Dhaka" })).toEqual({ about: "hi" });
  });
});
