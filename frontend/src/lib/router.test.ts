import { describe, expect, it } from "vitest";
import { matchRoute, type Route } from "./router";

const routes: Route[] = [
  { pattern: /^\/$/, render: () => "home" },
  { pattern: /^\/prep\/(\d+)$/, render: ([id]) => `plan ${id}` },
  { pattern: /^\/prep\/(\d+)\/today$/, render: ([id]) => `today ${id}` },
];

describe("matchRoute", () => {
  it("finds a screen and passes the ids", () => {
    expect(matchRoute(routes, "/")).toBe("home");
    expect(matchRoute(routes, "/prep/12")).toBe("plan 12");
    expect(matchRoute(routes, "/prep/12/today")).toBe("today 12");
  });
  it("answers nothing for an unknown path", () => {
    expect(matchRoute(routes, "/prep/abc")).toBeUndefined();
    expect(matchRoute(routes, "/nope")).toBeUndefined();
  });
});
