import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { announce, notify, Toasts } from "./toast";

afterEach(cleanup);

describe("messages for screen readers", () => {
  it("has its live regions on the page before any message is added", () => {
    render(<Toasts />);
    const polite = screen.getByTestId("toasts-polite");
    const alert = screen.getByTestId("toasts-alert");
    expect(polite.getAttribute("aria-live")).toBe("polite");
    expect(alert.getAttribute("role")).toBe("alert");
    expect(screen.getByTestId("announcer").getAttribute("aria-live")).toBe("polite");
    expect(polite.textContent).toBe("");
    expect(alert.textContent).toBe("");
  });

  it("puts a success message inside the polite region and an error inside the alert region, with no second role on the message", () => {
    render(<Toasts />);
    const polite = screen.getByTestId("toasts-polite");
    const alert = screen.getByTestId("toasts-alert");
    act(() => notify("Saved Acme", "success"));
    act(() => notify("That did not work", "error"));
    expect(polite.textContent).toContain("Saved Acme");
    expect(alert.textContent).toContain("That did not work");
    expect(polite.textContent).not.toContain("That did not work");
    expect(screen.queryAllByRole("status")).toHaveLength(1); // only the invisible announcer; the message is not a second live region
    expect(polite.querySelector("[role]")).toBeNull();
  });

  it("names the dismiss button after its message, and removes the message", () => {
    render(<Toasts />);
    act(() => notify("Saved Acme"));
    fireEvent.click(screen.getByRole("button", { name: "Dismiss the message: Saved Acme" }));
    expect(screen.getByTestId("toasts-polite").textContent).toBe("");
  });

  it("announce() writes into the invisible polite region, also when the same words come twice", () => {
    render(<Toasts />);
    const announcer = screen.getByTestId("announcer");
    act(() => announce("2 problems to fix"));
    const first = announcer.textContent;
    expect(first).toContain("2 problems to fix");
    act(() => announce("2 problems to fix"));
    expect(announcer.textContent).not.toBe(first);
    expect(announcer.className).toContain("sr-only");
  });
});
