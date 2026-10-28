import { describe, expect, it } from "vitest";
import { companyPath } from "./depth-api";

describe("companyPath", () => {
  it("encodes names so slashes and ampersands stay in one segment", () => {
    expect(companyPath("A/B & Co")).toBe("/companies/A%2FB%20%26%20Co");
  });
});
