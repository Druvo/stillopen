import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Job, Me, ScanStatus } from "@/lib/types";

vi.mock("./api", () => ({
  dashboardApi: { scanLog: vi.fn(), scanStatus: vi.fn(), startScan: vi.fn(), importTracker: vi.fn(), followupDone: vi.fn(), followupSnooze: vi.fn(), sendToPaperless: vi.fn() },
  useMe: vi.fn(),
}));

import { ActionMenu } from "@/components/menu";
import { dashboardApi } from "./api";
import { FilterPanel } from "./filters";
import { JobCard, type CardExtras } from "./job-card";
import { DEFAULT_FILTERS } from "./logic";
import { AsideCard, LastSearchBody, NextStepBody, StaffBanners, StatTiles, YourSearchBody } from "./panels";
import { StageTabs, Toolbar, type Tab } from "./toolbar";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const withQuery = (ui: ReactNode) => <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>;

const scan = (over: Partial<ScanStatus>): ScanStatus => ({
  running: false, done: 0, total: 0, error: "", found: 0, added: 0, note: "", started_at: null, finished_at: null, phase: "done", entries_count: 0, ...over,
});

describe("the last search", () => {
  it("shows progress and the hint while a search runs, and fetches no log until it is opened", () => {
    render(withQuery(<LastSearchBody canScan starting={false} scan={scan({ running: true, phase: "reading", done: 2, total: 5, note: "Only the best were added", entries_count: 2 })} />));
    expect(screen.getByText("Reading job sources… 2/5")).toBeTruthy();
    expect(screen.getByRole("progressbar", { name: "Search progress" }).getAttribute("aria-valuenow")).toBe("40");
    expect(screen.getByText(/Usually about a minute/)).toBeTruthy();
    expect(screen.getByText("Only the best were added")).toBeTruthy();
    expect(dashboardApi.scanLog).not.toHaveBeenCalled();
  });

  it("loads the per-source log when the log is opened", async () => {
    vi.mocked(dashboardApi.scanLog).mockResolvedValue({
      ...scan({ found: 10, added: 2, entries_count: 2 }),
      entries: [
        { source: "Acme", connector: "Greenhouse", found: 5, matched: 3, added: 2, duplicates: 1, outside: 1, error: "" },
        { source: "Broken", connector: "Lever", found: 0, matched: 0, added: 0, duplicates: 0, outside: 0, error: "HTTP 500" },
      ],
    });
    render(withQuery(<LastSearchBody canScan starting={false} scan={scan({ found: 10, added: 2, started_at: new Date().toISOString(), entries_count: 2 })} />));
    expect(screen.getByText(/looked through 10 openings, 2 new for you/)).toBeTruthy();
    expect(screen.queryByRole("progressbar")).toBeNull();
    const details = screen.getByText(/Scan log -- where it searched/).closest("details") as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event("toggle"));
    await waitFor(() => expect(screen.getByText("5 found, 3 matched, 2 new, 1 already tracked, 1 outside your areas")).toBeTruthy());
    expect(screen.getByText("HTTP 500").className).toContain("text-bad");
    expect(dashboardApi.scanLog).toHaveBeenCalledTimes(1);
  });

  it("says what to do when no search has run, and shows a start the moment one begins", () => {
    const { rerender } = render(withQuery(<LastSearchBody canScan starting={false} scan={null} />));
    expect(screen.getByText(/Press Search for jobs/)).toBeTruthy();
    rerender(withQuery(<LastSearchBody canScan starting scan={null} />));
    expect(screen.getByText("Starting the search…")).toBeTruthy();
  });
});

describe("the next step", () => {
  it("scrolls to a card instead of leaving the page", () => {
    const onCard = vi.fn();
    render(<NextStepBody step={{ headline: "See how well Acme fits you", body: "Press it.", label: "Take me there", url: "#job-4" }} onCard={onCard} />);
    fireEvent.click(screen.getByRole("link", { name: "Take me there" }));
    expect(onCard).toHaveBeenCalledWith("job-4");
  });

  it("uses the app address for a link into the app", () => {
    render(<NextStepBody step={{ headline: "h", body: "b", label: "Add places", url: "/app/profile#areas" }} onCard={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Add places" }).getAttribute("href")).toBe("/app/profile#areas");
  });

  it("has no button when there is nothing to press", () => {
    render(<NextStepBody step={{ headline: "We are searching", body: "b", label: "", url: "" }} onCard={vi.fn()} />);
    expect(screen.queryByRole("link")).toBeNull();
  });
});

describe("the tiles", () => {
  it("says what to do when there is no average yet, and names the urgent window", () => {
    render(<StatTiles data={{ stats: { total: 3, submitted: 1, average_match: null, urgent: 2 }, urgent_days: 5 }} />);
    expect(screen.getByText("Average fit (check a job first)")).toBeTruthy();
    expect(screen.getByText("Closing within 5 days")).toBeTruthy();
  });

  it("shows nothing for an empty tracker", () => {
    const { container } = render(<StatTiles data={{ stats: { total: 0, submitted: 0, average_match: null, urgent: 0 }, urgent_days: 5 }} />);
    expect(container.textContent).toBe("");
  });
});

describe("Your search", () => {
  it("lists what drives the matches with a Change link to the right place, and Add where something is missing", () => {
    render(
      <YourSearchBody
        summary={{ roles: ["Backend Engineer"], places: [{ place: "Malaysia", mode: "hybrid" }], remote: "", salary_floor: "", alerts_on: false, alerts_available: true, has_cv: false, ai: "keyword" }}
      />,
    );
    expect(screen.getByText("Backend Engineer")).toBeTruthy();
    expect(screen.getByText("Malaysia (hybrid)")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Your search: change roles" }).getAttribute("href")).toBe("/app/profile");
    expect(screen.getByRole("link", { name: "Your search: change places" }).getAttribute("href")).toBe("/app/profile#areas");
    expect(screen.getByRole("link", { name: "Your search: change how fit is judged" }).getAttribute("href")).toBe("/app/profile/ai");
    expect(screen.getByRole("link", { name: "Your search: add CV" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Your search: add minimum pay" })).toBeTruthy();
    expect(screen.getByText("Quick keyword check")).toBeTruthy();
    expect(screen.getByText("Off")).toBeTruthy();
  });
});

describe("a side card below the wide layout", () => {
  it("folds into a disclosure that opens and closes, closed unless asked", () => {
    render(
      <>
        <AsideCard title="Coming up">
          <p>content A</p>
        </AsideCard>
        <AsideCard title="Your next step" defaultOpen>
          <p>content B</p>
        </AsideCard>
      </>,
    );
    const a = screen.getByRole("button", { name: /Coming up/ });
    expect(a.getAttribute("aria-expanded")).toBe("false");
    expect(screen.getByText("content A").closest("[hidden]")).toBeTruthy();
    fireEvent.click(a);
    expect(a.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("content A").closest("[hidden]")).toBeNull();
    expect(screen.getByRole("button", { name: /Your next step/ }).getAttribute("aria-expanded")).toBe("true");
  });
});

describe("the stage tabs", () => {
  const tabs: Tab[] = [
    { key: "", label: "All", description: "", count: 3 },
    { key: "new", label: "New", description: "Just found", count: 2 },
    { key: "active", label: "Active", description: "", count: 1 },
  ];

  it("are real ARIA tabs with only the chosen one in the tab order", () => {
    render(<StageTabs tabs={tabs} active="new" onChange={vi.fn()} />);
    expect(screen.getByRole("tablist", { name: "Show jobs by stage" })).toBeTruthy();
    const all = screen.getAllByRole("tab");
    expect(all.map((t) => t.getAttribute("aria-selected"))).toEqual(["false", "true", "false"]);
    expect(all.map((t) => t.tabIndex)).toEqual([-1, 0, -1]);
    expect(screen.getByRole("tab", { name: "All 3" })).toBeTruthy();
  });

  it("move and choose with the arrow keys, Home and End", () => {
    const onChange = vi.fn();
    render(<StageTabs tabs={tabs} active="new" onChange={onChange} />);
    const chosen = screen.getByRole("tab", { name: "New 2" });
    fireEvent.keyDown(chosen, { key: "ArrowRight" });
    expect(onChange).toHaveBeenLastCalledWith("active");
    fireEvent.keyDown(chosen, { key: "ArrowLeft" });
    expect(onChange).toHaveBeenLastCalledWith("");
    fireEvent.keyDown(chosen, { key: "End" });
    expect(onChange).toHaveBeenLastCalledWith("active");
    fireEvent.keyDown(chosen, { key: "Home" });
    expect(onChange).toHaveBeenLastCalledWith("");
    fireEvent.click(screen.getByRole("tab", { name: "Active 1" }));
    expect(onChange).toHaveBeenLastCalledWith("active");
  });
});

describe("the toolbar", () => {
  const props = { filters: DEFAULT_FILTERS, set: vi.fn(), onToggle: vi.fn(), panelId: "panel", activeCount: 0, view: "list" as const, onView: vi.fn(), open: false };

  it("has a Filters button that says whether the panel is open and what it controls", () => {
    const { rerender } = render(<Toolbar {...props} />);
    const button = screen.getByRole("button", { name: "Filters" });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(button.getAttribute("aria-controls")).toBe("panel");
    fireEvent.click(button);
    expect(props.onToggle).toHaveBeenCalled();
    rerender(<Toolbar {...props} open />);
    expect(screen.getByRole("button", { name: "Filters" }).getAttribute("aria-expanded")).toBe("true");
  });

  it("shows how many filters are on, in words as well as a number", () => {
    render(<Toolbar {...props} activeCount={2} />);
    expect(screen.getByRole("button", { name: /Filters.*2 on/ })).toBeTruthy();
  });

  it("switches between list and board, and reports search and sort changes", () => {
    render(<Toolbar {...props} />);
    expect(screen.getByRole("button", { name: "List" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Board" }));
    expect(props.onView).toHaveBeenCalledWith("board");
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "acme" } });
    expect(props.set).toHaveBeenCalledWith({ q: "acme" });
    fireEvent.change(screen.getByLabelText("Sort by"), { target: { value: "oldest" } });
    expect(props.set).toHaveBeenCalledWith({ sort: "oldest" });
  });
});

describe("the filter panel", () => {
  const jobs = [{ id: 1, bucket_key: "new", country: "MY", country_name: "Malaysia" }, { id: 2, bucket_key: "active", country: "", country_name: "" }] as Job[];

  it("has the six filters and the count line", () => {
    render(<FilterPanel id="p" filters={DEFAULT_FILTERS} set={vi.fn()} reset={vi.fn()} jobs={jobs} bandLabels={["Strong", "A stretch"]} inStage={2} shown={2} />);
    for (const label of ["Fits your places", "How well you match", "Work", "Country", "Posting", "Found"]) expect(screen.getByLabelText(label)).toBeTruthy();
    expect(screen.getByText("Showing all 2")).toBeTruthy();
    expect(screen.queryByText("Clear filters")).toBeNull();
    expect(screen.getByRole("option", { name: "Not checked yet" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "Malaysia" })).toBeTruthy();
  });

  it("reports changes, and offers to clear them once something is set", () => {
    const set = vi.fn();
    const reset = vi.fn();
    render(<FilterPanel id="p" filters={{ ...DEFAULT_FILTERS, work: "remote" }} set={set} reset={reset} jobs={jobs} bandLabels={[]} inStage={2} shown={1} />);
    expect(screen.getByText("Showing 1 of 2")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Posting"), { target: { value: "expired" } });
    expect(set).toHaveBeenCalledWith({ live: "expired" });
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(reset).toHaveBeenCalled();
  });
});

describe("the action menu", () => {
  it("opens a list of actions, moves with the arrow keys and closes with Escape back on its button", async () => {
    const onSelect = vi.fn();
    render(<ActionMenu label="More actions for X" items={[{ key: "a", label: "First", onSelect }, { key: "b", label: "Second", to: "/profile" }]} />);
    const button = screen.getByRole("button", { name: "More actions for X" });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    const menu = screen.getByRole("menu");
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["First", "Second"]);
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("menuitem", { name: "First" })));
    fireEvent.keyDown(menu, { key: "ArrowDown" });
    expect(document.activeElement).toBe(screen.getByRole("menuitem", { name: "Second" }));
    fireEvent.keyDown(menu, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(button);
    fireEvent.click(button);
    fireEvent.click(screen.getByRole("menuitem", { name: "First" }));
    expect(onSelect).toHaveBeenCalled();
    expect(screen.queryByRole("menu")).toBeNull();
  });
});

describe("a job card", () => {
  const job = (over: Partial<Job>): Job =>
    ({
      id: 1, company: "Acme", role: "Backend Engineer", url: "https://x.example/1", status_id: 1, bucket_key: "new", percent: null, band: null, decision: "", risk: "", summary: "",
      next_action: "", notes: "", source: "Greenhouse", advertised_pay: "", location: "Kuala Lumpur", country: "MY", country_name: "Malaysia", arrangement: "", found_date: "2026-10-01",
      applied_date: null, applied_channel: "", applied_cv: null, follow_up_date: null, counts_as_applied: false, deadline: null, days_left: null, urgent: false, overdue: false,
      live_state: "unknown", live_detail: "", strengths: [], gaps: [], fit_level: "", fit_text: "", fit_badge: null, has_cv: false, cv: null, repost: null, skill_matched: false,
      evaluated: false, ai_evaluated: false, ai_method: "", has_description: true, documents: [], ...over,
    }) as Job;
  const statuses = [{ id: 1, name: "Saved", bucket_key: "new", color: "#000", counts_as_applied: false }];
  const extras: CardExtras = { judgeLabel: "Quick keyword check", prepEnabled: false, paperlessUrl: "", refresh: vi.fn() };
  const card = (j: Job, onCheckFit = vi.fn()) => render(<JobCard job={j} statuses={statuses} extras={extras} onMove={vi.fn()} onCheckFit={onCheckFit} checking={false} />);

  it("offers Check my fit as the one main action until the fit is checked, with the rest under More", () => {
    const onCheckFit = vi.fn();
    card(job({}), onCheckFit);
    fireEvent.click(screen.getByRole("button", { name: /^Check my fit for / }));
    expect(onCheckFit).toHaveBeenCalled();
    expect(screen.getByText("Not checked yet")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Get ready to apply" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /More actions/ }));
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Get ready to apply", "Tailor my CV", "Edit details", "View the posting"]);
  });

  it("offers Get ready to apply once it is checked, and Check again moves under More", () => {
    card(job({ ai_evaluated: true, percent: 82, band: { label: "Strong", color: "#0a0" } }));
    expect(screen.queryByRole("button", { name: /^Check my fit/ })).toBeNull();
    expect(screen.getByRole("link", { name: "Get ready to apply" }).getAttribute("href")).toBe("/app/jobs/1/apply");
    expect(screen.getByRole("img", { name: "82% match, Strong" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /More actions/ }));
    expect(screen.getByRole("menuitem", { name: "Check again" })).toBeTruthy();
  });

  it("has no Check my fit or Tailor my CV when there is nothing to read", () => {
    card(job({ has_description: false, url: "" }));
    expect(screen.queryByRole("button", { name: /^Check my fit/ })).toBeNull();
    expect(screen.getByRole("link", { name: "Get ready to apply" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /More actions/ }));
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Edit details"]);
  });

  it("keeps the details closed until asked, and puts the applied line inside", () => {
    card(job({ applied_date: "2026-10-05", counts_as_applied: true, applied_channel: "Email", notes: "Call back Friday" }));
    const details = screen.getByText("Details").closest("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(details.textContent).toContain("via Email");
    expect(details.textContent).toContain("Call back Friday");
  });
});

// ---- the banners only a site admin sees (ported from the Jooble nudge added on main) --------------------------------------------------

const staffMe = (over: Partial<Me>): Me =>
  ({
    id: 1, name: "Pat", email: "pat@example.com", is_staff: true, greeting: "Good morning, Pat", site_title: "StillOpen", prep_enabled: false, assistant_enabled: false,
    email_unverified_signups: false, legal_has_blanks: false, jooble_sources_dormant: false, usajobs_sources_dormant: false, ...over,
  }) as Me;

describe("the staff-only banners", () => {
  it("shows nothing for an ordinary user, even with every flag true", () => {
    render(<StaffBanners me={staffMe({ is_staff: false, email_unverified_signups: true, legal_has_blanks: true, jooble_sources_dormant: true })} />);
    expect(screen.queryByText(/jooble.org\/api\/about/)).toBeNull();
    expect(screen.queryByText(/EMAIL_HOST/)).toBeNull();
  });

  it("nudges staff to add a Jooble key when a site-wide source is dormant", () => {
    render(<StaffBanners me={staffMe({ jooble_sources_dormant: true })} />);
    expect(screen.getByText(/silently finds nothing on every search/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "jooble.org/api/about" }).getAttribute("href")).toBe("https://jooble.org/api/about");
  });

  it("says it once when no search key is set at all, even if a Jooble source is also dormant", () => {
    render(<StaffBanners me={staffMe({ no_search_keys: true, jooble_sources_dormant: true })} />);
    expect(screen.queryByText(/silently finds nothing on every search/)).toBeNull();
    expect(screen.getByText(/Jooble or Adzuna key/)).toBeTruthy();
  });

  it("nudges staff to add a USAJobs key when a site-wide source is dormant", () => {
    render(<StaffBanners me={staffMe({ usajobs_sources_dormant: true })} />);
    expect(screen.getByText(/no key \(or no registered email\)/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "developer.usajobs.gov/apirequest" }).getAttribute("href")).toBe("https://developer.usajobs.gov/apirequest");
  });

  it("shows nothing when no flag is set", () => {
    render(<StaffBanners me={staffMe({})} />);
    expect(screen.queryByText(/jooble.org\/api\/about/)).toBeNull();
    expect(screen.queryByText(/EMAIL_HOST/)).toBeNull();
    expect(screen.queryByText(/bracketed parts/)).toBeNull();
  });
});
