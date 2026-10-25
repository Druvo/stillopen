import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const me = vi.hoisted(() => ({ data: { contact_email: "" } as { contact_email?: string } }));
vi.mock("@/lib/me", () => ({ useMe: () => me }));

import { FAQ, SECTIONS } from "./content";
import { HelpPage } from "./help";
import { contactAddress } from "./logic";

afterEach(() => {
  cleanup();
  me.data = { contact_email: "" };
});

const page = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <HelpPage />
    </QueryClientProvider>,
  );

describe("the help content", () => {
  it("has every section the page promises and about a dozen real questions", () => {
    const titles = SECTIONS.map((s) => s.title);
    for (const wanted of ["Get started in five steps", "Get your LinkedIn jobs in", "How your match score works", "What the AI does and does not do", "The ATS check", "Keyboard shortcuts", "Your data", "About reminders and emails"]) {
      expect(titles).toContain(wanted);
    }
    expect(SECTIONS[0].steps).toHaveLength(5);
    expect(FAQ.length).toBeGreaterThanOrEqual(12);
    for (const f of FAQ) expect(f.answer.length).toBeGreaterThan(30);
  });
  it("uses no harsh label", () => {
    const text = JSON.stringify([SECTIONS, FAQ]).toLowerCase();
    expect(text).not.toMatch(/\bweak\b/);
    expect(text).not.toContain("n/a");
  });
});

describe("HelpPage", () => {
  it("has a heading for every section, as disclosures, with the first open", () => {
    page();
    expect(screen.getByRole("heading", { level: 1, name: "Help" })).toBeTruthy();
    for (const s of SECTIONS) expect(screen.getByRole("heading", { level: 2, name: s.title })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 2, name: "Questions people ask" })).toBeTruthy();
    expect((document.getElementById(SECTIONS[0].id) as HTMLDetailsElement).open).toBe(true);
    expect((document.getElementById(SECTIONS[1].id) as HTMLDetailsElement).open).toBe(false);
  });
  it("opens and closes everything", () => {
    page();
    fireEvent.click(screen.getByRole("button", { name: "Open all" }));
    expect((document.getElementById(SECTIONS[2].id) as HTMLDetailsElement).open).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Close all" }));
    expect((document.getElementById(SECTIONS[0].id) as HTMLDetailsElement).open).toBe(false);
  });
  it("shows Still stuck only when the site has a contact address", () => {
    page();
    expect(screen.queryByText(/Still stuck/)).toBeNull();
    cleanup();
    me.data = { contact_email: "help@example.org" };
    page();
    expect(screen.getByText(/Still stuck\? Write to/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "help@example.org" }).getAttribute("href")).toBe("mailto:help@example.org");
  });
});

describe("contactAddress", () => {
  it("accepts an address and refuses anything else", () => {
    expect(contactAddress(" help@example.org ")).toBe("help@example.org");
    expect(contactAddress("")).toBe("");
    expect(contactAddress(undefined)).toBe("");
    expect(contactAddress("not an address")).toBe("");
    expect(contactAddress("a@b")).toBe("");
  });
});
