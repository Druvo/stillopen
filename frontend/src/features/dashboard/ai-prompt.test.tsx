import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AiKeyPrompt } from "./panels";

afterEach(cleanup);

describe("the Google AI Studio key prompt", () => {
  it("sends people to Google AI Studio in a new tab, and to the key box on the AI settings page", () => {
    render(<AiKeyPrompt onDismiss={() => undefined} />);
    const google = screen.getByRole("link", { name: "Create a key in Google AI Studio" });
    expect(google.getAttribute("href")).toBe("https://aistudio.google.com/apikey");
    expect(google.getAttribute("target")).toBe("_blank");
    expect(google.getAttribute("rel")).toContain("noopener");
    expect(screen.getByRole("link", { name: "Add my key" }).getAttribute("href")).toBe("/app/profile/ai?preset=gemini");
  });

  it("says plainly what is sent to Google and that the free check still works", () => {
    render(<AiKeyPrompt onDismiss={() => undefined} />);
    expect(screen.getByText(/free keyword check/)).toBeTruthy();
    expect(screen.getByText(/may use what you send to improve its products/)).toBeTruthy();
  });

  it("lets people say not now", () => {
    const dismiss = vi.fn();
    render(<AiKeyPrompt onDismiss={dismiss} />);
    fireEvent.click(screen.getByRole("button", { name: "Not now" }));
    expect(dismiss).toHaveBeenCalledOnce();
  });
});
