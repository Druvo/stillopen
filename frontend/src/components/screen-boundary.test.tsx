import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ScreenBoundary } from "./screen-boundary";

afterEach(cleanup);

let explode = true;
function Bomb() {
  if (explode) throw new Error("boom");
  return <p>fine</p>;
}

describe("ScreenBoundary", () => {
  it("shows a plain message instead of crashing the page, and Try again recovers once the cause is gone", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    explode = true;
    render(
      <ScreenBoundary resetKey="/a">
        <Bomb />
      </ScreenBoundary>,
    );
    expect(screen.getByRole("alert").textContent).toContain("could not be shown");
    explode = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(screen.getByText("fine")).toBeTruthy();
  });

  it("clears the error when the person moves to another screen", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    explode = true;
    const { rerender } = render(
      <ScreenBoundary resetKey="/a">
        <Bomb />
      </ScreenBoundary>,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    explode = false;
    rerender(
      <ScreenBoundary resetKey="/b">
        <Bomb />
      </ScreenBoundary>,
    );
    expect(screen.getByText("fine")).toBeTruthy();
  });
});
