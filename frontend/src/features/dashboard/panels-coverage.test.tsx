import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CoverageBody } from "@/features/account/coverage";
import type { Coverage } from "@/features/account/coverage-logic";
import type { Me, SearchSummary } from "@/lib/types";
import { StaffBanners, YourSearchBody } from "./panels";

afterEach(cleanup);

const me = (over: Partial<Me>): Me => ({ is_staff: true, email_unverified_signups: false, legal_has_blanks: false, ...over }) as Me;

describe("the staff banner that asks for a search key", () => {
  it("shows to staff when no key is set, with a link to the admin page", () => {
    render(<StaffBanners me={me({ no_search_keys: true })} />);
    expect(screen.getByText(/Add a free Jooble or Adzuna key to find jobs in more countries/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Job search keys/ }).getAttribute("href")).toBe("/admin/tracker/siteconfig/");
  });
  it("is gone once a key exists, and never shows to anyone else", () => {
    const { container, rerender } = render(<StaffBanners me={me({ no_search_keys: false })} />);
    expect(container.textContent).toBe("");
    rerender(<StaffBanners me={me({ is_staff: false, no_search_keys: true })} />);
    expect(container.textContent).toBe("");
  });
});

const summary: SearchSummary = { roles: ["Backend Engineer"], places: [], remote: "", salary_floor: "", alerts_on: false, alerts_available: true, has_cv: true, ai: "keyword" };

describe("the dashboard's Your search card", () => {
  it("adds one line when a place has no jobs, linking to the explanation", () => {
    render(<YourSearchBody summary={summary} emptyPlaces="Nothing lists jobs in Pakistan yet." />);
    expect(screen.getByText(/Nothing lists jobs in Pakistan yet\./)).toBeTruthy();
    expect(screen.getByRole("link", { name: "See why and what to do" })).toBeTruthy();
  });
  it("adds nothing when every place has jobs", () => {
    render(<YourSearchBody summary={summary} emptyPlaces={null} />);
    expect(screen.queryByText(/Nothing lists jobs/)).toBeNull();
  });
});

describe("the coverage card body", () => {
  const coverage: Coverage = {
    days: 30,
    has_areas: true,
    empty_areas: 1,
    keys: { jooble: false, adzuna: false },
    areas: [
      {
        id: 1, place: "Pakistan", label: "Pakistan", known: true, postings: 0, boards: 0, level: "none", searches_ready: 0, searches_waiting: 1,
        searches: [{ name: "Jooble Pakistan", connector: "jooble", connector_label: "Jooble", ready: false, reason: "needs_key" }],
        tip: "Nothing lists jobs in Pakistan yet. Jooble covers Pakistan but needs a free key.",
      },
      { id: 2, place: "Malaysia", label: "Malaysia", known: true, postings: 41, boards: 6, level: "ok", searches: [], searches_ready: 0, searches_waiting: 0, tip: "" },
    ],
  };
  it("shows per-place numbers, the search state and the tip", () => {
    render(<CoverageBody coverage={coverage} />);
    expect(screen.getByText("41 jobs listed in the last 30 days, from 6 job sources.")).toBeTruthy();
    expect(screen.getByText("No jobs listed in the last 30 days.")).toBeTruthy();
    expect(screen.getByText("Jooble: switched off until the site owner adds a free key")).toBeTruthy();
    expect(screen.getByText(/Jooble covers Pakistan but needs a free key/)).toBeTruthy();
    expect(screen.getByText("Well covered")).toBeTruthy();
  });
  it("asks for a place when there is none", () => {
    render(<CoverageBody coverage={{ ...coverage, has_areas: false, areas: [] }} />);
    expect(screen.getByText(/Tell us where you would work/)).toBeTruthy();
  });
});
