import { afterEach, describe, expect, it } from "vitest";
import { describedBy, firstHeading, focusableIn, nextTrapIndex, problemsText, screenTitle, trapTab } from "./a11y";

afterEach(() => {
  document.body.innerHTML = "";
});

describe("the focus trap", () => {
  it("wraps from the last item to the first and from the first back to the last", () => {
    expect(nextTrapIndex(4, 3, false)).toBe(0);
    expect(nextTrapIndex(4, 0, true)).toBe(3);
  });

  it("lets the browser step normally in the middle, and pulls focus in from outside", () => {
    expect(nextTrapIndex(4, 1, false)).toBeNull();
    expect(nextTrapIndex(4, 2, true)).toBeNull();
    expect(nextTrapIndex(4, -1, false)).toBe(0);
    expect(nextTrapIndex(4, -1, true)).toBe(3);
  });

  it("keeps Tab inside an element with nothing to focus", () => {
    expect(nextTrapIndex(0, -1, false)).toBe(-1);
  });

  it("moves real focus from the last link to the first, and skips hidden and disabled things", () => {
    document.body.innerHTML = `<div id="d"><a href="#a" id="a">A</a><button id="off" disabled>x</button><div hidden><a href="#h">h</a></div><a href="#b" id="b">B</a></div>`;
    const root = document.getElementById("d")!;
    expect(focusableIn(root).map((e) => e.id || e.textContent)).toEqual(["a", "b"]);
    document.getElementById("b")!.focus();
    let prevented = false;
    expect(trapTab({ key: "Tab", shiftKey: false, preventDefault: () => (prevented = true) }, root)).toBe(true);
    expect(prevented).toBe(true);
    expect(document.activeElement?.id).toBe("a");
    expect(trapTab({ key: "Tab", shiftKey: true, preventDefault: () => undefined }, root)).toBe(true);
    expect(document.activeElement?.id).toBe("b");
    expect(trapTab({ key: "Enter", shiftKey: false, preventDefault: () => undefined }, root)).toBe(false);
  });
});

describe("the screen title", () => {
  it("is the screen's name first, then the site", () => {
    expect(screenTitle("Add a job", "StillOpen")).toBe("Add a job - StillOpen");
    expect(screenTitle("Add a job", "Job Hub")).toBe("Add a job - Job Hub");
  });

  it("is just the site while a screen is loading", () => {
    expect(screenTitle("", "StillOpen")).toBe("StillOpen");
    expect(screenTitle(null, "StillOpen")).toBe("StillOpen");
    expect(screenTitle("StillOpen", "StillOpen")).toBe("StillOpen");
  });

  it("reads the first h1 as plain, tidy text", () => {
    document.body.innerHTML = `<main><h2>Side</h2><h1>  Your   <span>CVs</span> </h1></main>`;
    expect(firstHeading(document.querySelector("main"))).toBe("Your CVs");
    expect(firstHeading(null)).toBe("");
    document.body.innerHTML = `<main><p>Loading</p></main>`;
    expect(firstHeading(document.querySelector("main"))).toBe("");
  });
});

describe("small helpers", () => {
  it("says how many problems a refused form has", () => {
    expect(problemsText(1)).toBe("1 problem to fix");
    expect(problemsText(3)).toBe("3 problems to fix");
  });

  it("joins only the ids that exist", () => {
    expect(describedBy("a", false, undefined, "b")).toBe("a b");
    expect(describedBy(false, null)).toBeUndefined();
  });
});
