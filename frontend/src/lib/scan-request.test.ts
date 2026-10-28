import { describe, expect, it } from "vitest";
import { requestScan, takeScanRequest } from "./scan-request";

describe("a search asked for from the palette", () => {
  it("is taken once", () => {
    requestScan(1000);
    expect(takeScanRequest(2000)).toBe(true);
    expect(takeScanRequest(2000)).toBe(false);
  });
  it("is dropped when it is old", () => {
    requestScan(1000);
    expect(takeScanRequest(1000 + 20_000)).toBe(false);
  });
  it("is false when nobody asked", () => {
    expect(takeScanRequest(5)).toBe(false);
  });
});
