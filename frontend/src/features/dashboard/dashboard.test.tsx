import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_PREFERENCES } from "@/lib/preferences";
import { resetSaver } from "@/lib/prefs-store";
import type { Dashboard as DashboardData, Job, Me, Preferences } from "@/lib/types";

const state = vi.hoisted(() => ({ calls: [] as { method: string; path: string; body?: unknown }[], me: null as unknown, dashboard: null as unknown }));
const calls = state.calls;
let me: Me;
let dashboard: DashboardData;

vi.mock("@/lib/api", async (original) => {
  const real = await original<typeof import("@/lib/api")>();
  const request = vi.fn(async (method: string, path: string, body?: unknown) => {
    calls.push({ method, path, body });
    if (path === "/me") return structuredClone(state.me);
    if (path === "/preferences" && method === "PUT") return { ...(state.me as Me).preferences, ...(body as object) };
    if (path === "/liveness/status") return { running: false, done: 0, total: 0, error: "" };
    throw new Error(`unexpected ${method} ${path}`);
  });
  return { ...real, request, api: { ...real.api, dashboard: async () => structuredClone(state.dashboard), livenessStatus: () => request("GET", "/liveness/status"), savePreferences: (patch: object) => request("PUT", "/preferences", patch) } };
});

import { Dashboard } from "./dashboard";

const job = (id: number, over: Partial<Job>): Job =>
  ({
    id, company: `Co${id}`, role: `Role${id}`, url: "", status_id: 1, bucket_key: "new", percent: null, band: null, decision: "", risk: "", summary: "", next_action: "", notes: "",
    source: "", advertised_pay: "", location: "", country: "", country_name: "", arrangement: "", found_date: "2026-10-01", applied_date: null, applied_channel: "", applied_cv: null,
    follow_up_date: null, counts_as_applied: false, deadline: null, days_left: null, urgent: false, overdue: false, live_state: "unknown", live_detail: "", strengths: [], gaps: [],
    fit_level: "", fit_text: "", fit_badge: null, has_cv: false, cv: null, repost: null, skill_matched: false, evaluated: false, ai_evaluated: false, ai_method: "",
    has_description: false, documents: [], ...over,
  }) as Job;

function setup(prefs: Partial<Preferences> = {}) {
  me = { id: 1, name: "Al", email: "a@x", is_staff: false, greeting: "", site_title: "", prep_enabled: false, assistant_enabled: false, email_unverified_signups: false, legal_has_blanks: false, jooble_sources_dormant: false, usajobs_sources_dormant: false, preferences: { ...DEFAULT_PREFERENCES, ...prefs } };
  dashboard = {
    greeting: "Good morning, Al", buckets: [{ key: "new", label: "To apply", description: "", is_closed: false }, { key: "active", label: "Applied", description: "", is_closed: false }],
    statuses: [{ id: 1, name: "Saved", bucket_key: "new", color: "#000", counts_as_applied: false }, { id: 2, name: "Applied", bucket_key: "active", color: "#000", counts_as_applied: true }],
    band_labels: ["Strong"], jobs: [job(1, { role: "Backend" }), job(2, { role: "Designer", status_id: 2, bucket_key: "active", arrangement: "remote" })],
    stats: { total: 2, submitted: 1, average_match: null, urgent: 0 }, followups: [], upcoming_interviews: [], next_step: null, can_scan: false, checked_at: null, has_areas: true, urgent_days: 5,
    prep_enabled: false, judge_label: "Quick keyword check", paperless_on: false, paperless_url: "", can_import: false, scan: null,
    search_summary: { roles: ["Backend"], places: [], remote: "", salary_floor: "", alerts_on: false, alerts_available: true, has_cv: true, ai: "keyword" },
    ai_prompt: { show: false },
  };
  state.me = me;
  state.dashboard = dashboard;
  calls.length = 0;
  resetSaver();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 60_000 } } })}>
      <Dashboard />
    </QueryClientProvider>,
  );
}

beforeEach(() => window.history.replaceState(null, "", "/app/"));
afterEach(cleanup);

describe("the dashboard", () => {
  it("opens as a list with stage tabs, and the filter panel hidden", async () => {
    setup();
    expect(await screen.findByRole("article", { name: "Backend at Co1" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "All 2" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("button", { name: "List" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Filters" }).getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByLabelText("Fits your places")).toBeNull();
    expect(screen.queryByText("Showing all 2")).toBeNull();
  });

  it("shows the panel from the Filters button, saves that, and counts the filters that are on", async () => {
    setup();
    await screen.findByRole("article", { name: "Backend at Co1" });
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    expect(await screen.findByText("Showing all 2")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Filters" }).getAttribute("aria-expanded")).toBe("true");
    fireEvent.change(screen.getByLabelText("Work"), { target: { value: "remote" } });
    expect(await screen.findByText("Showing 1 of 2")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Filters.*1 on/ })).toBeTruthy();
    expect(screen.queryByRole("article", { name: "Backend at Co1" })).toBeNull();
    // Both changes go to the server together, once, after the person pauses.
    await waitFor(() => expect(calls.filter((c) => c.method === "PUT")).toHaveLength(1), { timeout: 2000 });
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ filters_open: true, filters: { fit: "", match: "", work: "remote", country: "", posting: "", found: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(await screen.findByText("Showing all 2")).toBeTruthy();
    await waitFor(() => expect(calls.filter((c) => c.method === "PUT")).toHaveLength(2), { timeout: 2000 }); // the clearing is saved too
  });

  it("narrows to one stage from a tab, and the tab is saved", async () => {
    setup();
    await screen.findByRole("article", { name: "Backend at Co1" });
    fireEvent.click(screen.getByRole("tab", { name: "Applied 1" }));
    await waitFor(() => expect(screen.queryByRole("article", { name: "Backend at Co1" })).toBeNull());
    expect(screen.getByRole("article", { name: "Designer at Co2" })).toBeTruthy();
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ tab: "active" }), { timeout: 2000 });
  });

  it("uses the saved choices: the board, a stage and an open panel", async () => {
    setup({ view: "board", tab: "active", filters_open: true, filters: { ...DEFAULT_PREFERENCES.filters, work: "remote" } });
    expect(await screen.findByRole("tab", { name: "Applied 1" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Applied 1" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("button", { name: "Board" }).getAttribute("aria-pressed")).toBe("true");
    expect((screen.getByLabelText("Work") as HTMLSelectElement).value).toBe("remote");
    expect(await screen.findByRole("button", { name: /Drag Designer at Co2/ })).toBeTruthy(); // the board is loaded on demand
  });

  it("puts a saved stage that no longer exists back to All", async () => {
    setup({ tab: "gone" });
    expect(await screen.findByRole("tab", { name: "All 2" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "All 2" }).getAttribute("aria-selected")).toBe("true");
  });

  it("has the Your search card with a link to change it", async () => {
    setup();
    await screen.findByRole("article", { name: "Backend at Co1" });
    fireEvent.click(screen.getByRole("button", { name: /Your search/ })); // folded below the wide layout
    expect(screen.getByRole("link", { name: "Change roles" }).getAttribute("href")).toBe("/app/profile");
  });
});
