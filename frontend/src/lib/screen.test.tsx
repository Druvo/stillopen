import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { useScreenAnnouncer } from "./screen";
import { Toasts } from "./toast";

afterEach(() => {
  cleanup();
  document.title = "";
});

function Harness({ path, heading, site = "StillOpen" }: { path: string | null; heading: string | null; site?: string }) {
  const main = useRef<HTMLElement>(null);
  useScreenAnnouncer(main, path, site);
  return (
    <>
      <button type="button">Somewhere else</button>
      <main ref={main} tabIndex={-1}>
        {heading ? <h1>{heading}</h1> : <p>Loading</p>}
      </main>
      <Toasts />
    </>
  );
}

describe("a new screen", () => {
  it("sets the tab title from the screen's heading and the site title", () => {
    render(<Harness path="/cv" heading="Your CVs" />);
    expect(document.title).toBe("Your CVs - StillOpen");
  });

  it("calls the dashboard 'Dashboard', not by its greeting", () => {
    render(<Harness path="/" heading="Good evening, Alice" />);
    expect(document.title).toBe("Dashboard - StillOpen");
  });

  it("uses the site's own title once it is known", () => {
    const { rerender } = render(<Harness path="/cv" heading="Your CVs" />);
    rerender(<Harness path="/cv" heading="Your CVs" site="Job Hub" />);
    expect(document.title).toBe("Your CVs - Job Hub");
  });

  it("does not take focus on the first load", () => {
    render(<Harness path="/" heading="Hello" />);
    expect(document.activeElement).toBe(document.body);
    expect(screen.getByTestId("announcer").textContent).toBe("");
  });

  it("moves focus to the heading and says its name once after a move to another screen", async () => {
    const { rerender } = render(<Harness path="/" heading="Hello" />);
    screen.getByRole("button", { name: "Somewhere else" }).focus();
    rerender(<Harness path="/cv" heading="Your CVs" />);
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Your CVs" })));
    expect(document.activeElement?.getAttribute("tabindex")).toBe("-1");
    expect(screen.getByTestId("announcer").textContent).toContain("Your CVs");
    expect(document.title).toBe("Your CVs - StillOpen");
  });

  it("waits for a screen that is still loading, then focuses its heading when it appears", async () => {
    const { rerender } = render(<Harness path="/" heading="Hello" />);
    rerender(<Harness path="/offers" heading={null} />);
    expect(document.activeElement).toBe(document.body);
    expect(document.title).toBe("StillOpen");
    await act(async () => rerender(<Harness path="/offers" heading="Offers" />));
    await waitFor(() => expect(document.activeElement?.textContent).toBe("Offers"));
    expect(document.title).toBe("Offers - StillOpen");
  });

  it("leaves focus alone when the path is the same (only the query string or hash changed)", async () => {
    const { rerender } = render(<Harness path="/cv" heading="Your CVs" />);
    const other = screen.getByRole("button", { name: "Somewhere else" });
    other.focus();
    rerender(<Harness path="/cv" heading="Your CVs" />);
    await act(async () => undefined);
    expect(document.activeElement).toBe(other);
  });
});
