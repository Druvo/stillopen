import { describe, expect, it } from "vitest";
import { DEFAULT_PREFERENCES } from "@/lib/preferences";
import type { Dashboard, Job, Preferences, PrefFilters, ScanStatus, StatusInfo } from "@/lib/types";
import {
  applyMove, appliedParts, checkButtonText, countryOptions, cvBadgeText, activeFilterCount, DEFAULT_FILTERS, deadlineText, emptyKind, entryText, filtersFromPrefs, fitValue, headerLine, importMessage, nextTabIndex, patchFromFilters, resultsText, searchRows,
  interviewWhen, isFiltered, jobsByBucket, localDay, nextStepTarget, paperlessDocumentUrl, repostTitle, scanButtonText, scanPercent, scanTitle, shortDate, stageChips,
  statusForColumn, subtitle, timeAgo, truncate, visibleJobs, type Filters,
} from "./logic";

const statuses: StatusInfo[] = [
  { id: 1, name: "Saved", bucket_key: "new", color: "#000", counts_as_applied: false },
  { id: 2, name: "Evaluated", bucket_key: "new", color: "#000", counts_as_applied: false },
  { id: 3, name: "Applied", bucket_key: "active", color: "#000", counts_as_applied: true },
];

function job(over: Partial<Job>): Job {
  return {
    id: 1, company: "Acme", role: "Dev", url: "", status_id: 1, bucket_key: "new", percent: null, band: null, decision: "", risk: "", summary: "", next_action: "",
    notes: "", source: "", advertised_pay: "", location: "", country: "", country_name: "", arrangement: "", found_date: "2026-10-01", applied_date: null,
    applied_channel: "", applied_cv: null, follow_up_date: null, counts_as_applied: false, deadline: null, days_left: null, urgent: false, overdue: false,
    live_state: "unknown", live_detail: "", strengths: [], gaps: [], fit_level: "", fit_text: "", fit_badge: null, has_cv: false, cv: null, repost: null, apply_address: "",
    skill_matched: false, tech_skills: [], evaluated: false, ai_evaluated: false, ai_method: "", has_description: false, documents: [], ...over,
  };
}

const filters = (over: Partial<Filters> = {}): Filters => ({ ...DEFAULT_FILTERS, ...over });
const ids = (jobs: Job[]) => jobs.map((j) => j.id);
const NOW = new Date(2026, 9, 25, 12, 0, 0); // 25 Oct 2026, local time

describe("board logic", () => {
  it("drops a card on the first status of the column", () => {
    expect(statusForColumn(statuses, "new")?.name).toBe("Saved");
    expect(statusForColumn(statuses, "active")?.name).toBe("Applied");
    expect(statusForColumn(statuses, "nowhere")).toBeUndefined();
  });

  it("moves only the dragged job, without touching the original data", () => {
    const data = { jobs: [job({ id: 1 }), job({ id: 2 })] } as Dashboard;
    const moved = applyMove(data, 2, statuses[2]);
    expect(moved.jobs.map((j) => [j.id, j.status_id, j.bucket_key])).toEqual([
      [1, 1, "new"],
      [2, 3, "active"],
    ]);
    expect(data.jobs[1].bucket_key).toBe("new");
  });

  it("groups by column and keeps empty columns", () => {
    const grouped = jobsByBucket([job({ id: 1, bucket_key: "new" })], [
      { key: "new", label: "New", description: "", is_closed: false },
      { key: "active", label: "Active", description: "", is_closed: false },
    ]);
    expect(grouped.new).toHaveLength(1);
    expect(grouped.active).toEqual([]);
  });
});

describe("filters", () => {
  const band = (label: string) => ({ label, color: "#000" });
  const jobs = [
    job({ id: 1, company: "Acme", role: "Backend Engineer", country: "MY", country_name: "Malaysia", percent: 90, band: band("Strong"), fit_level: "ok", arrangement: "remote", live_state: "active", found_date: "2026-10-25" }),
    job({ id: 2, company: "Zed", role: "Designer", percent: 40, band: band("A stretch"), fit_level: "warn", arrangement: "onsite", live_state: "expired", found_date: "2026-10-20", bucket_key: "active", deadline: "2026-11-01" }),
    job({ id: 3, company: "beta", role: "Analyst", percent: null, fit_level: "", arrangement: "", country: "", live_state: "unknown", found_date: "2026-09-01", deadline: "2026-10-30" }),
  ];
  const run = (f: Partial<Filters>) => ids(visibleJobs(jobs, filters(f), NOW));

  it("shows everything first, in the server's best-first order", () => {
    expect(run({})).toEqual([1, 2, 3]);
  });

  it("searches every word across company, role and place", () => {
    expect(run({ q: "engineer malaysia" })).toEqual([1]);
    expect(run({ q: "ZED" })).toEqual([2]);
    expect(run({ q: "nobody" })).toEqual([]);
  });

  it("filters by stage", () => {
    expect(run({ stage: "active" })).toEqual([2]);
  });

  it("filters by how the job fits the person's places, treating a blank as unknown", () => {
    expect(fitValue(jobs[2])).toBe("unknown");
    expect(run({ fit: "fits" })).toEqual([1]);
    expect(run({ fit: "check" })).toEqual([2]);
    expect(run({ fit: "unknown" })).toEqual([3]);
  });

  it("filters by match band, including 'not checked yet'", () => {
    expect(run({ band: "Strong" })).toEqual([1]);
    expect(run({ band: "__none" })).toEqual([3]);
  });

  it("filters by work arrangement, including 'not stated'", () => {
    expect(run({ work: "remote" })).toEqual([1]);
    expect(run({ work: "__none" })).toEqual([3]);
  });

  it("filters by country, including 'not stated'", () => {
    expect(run({ country: "MY" })).toEqual([1]);
    expect(run({ country: "?" })).toEqual([2, 3]);
  });

  it("filters by whether the posting is open, closed, unclear or not checked", () => {
    expect(run({ live: "active" })).toEqual([1]);
    expect(run({ live: "expired" })).toEqual([2]);
    expect(run({ live: "unknown" })).toEqual([3]);
    const uncertain = job({ id: 4, live_state: "uncertain" });
    expect(ids(visibleJobs([...jobs, uncertain], filters({ live: "uncertain" }), NOW))).toEqual([4]);
  });

  it("filters by when it was found, in the person's own calendar days", () => {
    expect(run({ found: "today" })).toEqual([1]);
    expect(run({ found: "week" })).toEqual([1, 2]);
    expect(localDay(NOW)).toBe("2026-10-25");
    expect(localDay(NOW, 7)).toBe("2026-10-18");
    expect(ids(visibleJobs(jobs, filters({ found: "week" }), new Date(2026, 9, 30)))).toEqual([1]);
  });

  it("combines filters", () => {
    expect(run({ work: "remote", live: "expired" })).toEqual([]);
    expect(run({ work: "remote", live: "active", fit: "fits" })).toEqual([1]);
  });

  it("sorts: newest, oldest, company A to Z, closing soonest", () => {
    expect(run({ sort: "newest" })).toEqual([1, 2, 3]);
    expect(run({ sort: "oldest" })).toEqual([3, 2, 1]);
    expect(run({ sort: "company" })).toEqual([1, 3, 2]);
    expect(run({ sort: "deadline" })).toEqual([3, 2, 1]);
  });

  it("does not change the list it was given", () => {
    const copy = ids(jobs);
    run({ sort: "oldest" });
    expect(ids(jobs)).toEqual(copy);
  });

  it("knows when anything but the sort order narrows the list", () => {
    expect(isFiltered(filters())).toBe(false);
    expect(isFiltered(filters({ sort: "oldest" }))).toBe(false);
    expect(isFiltered(filters({ q: "x" }))).toBe(true);
    expect(isFiltered(filters({ fit: "fits" }))).toBe(true);
    expect(isFiltered(filters({ stage: "new" }))).toBe(false); // the stage tab is shown by the tabs, not a filter
  });

  it("counts the panel filters for the badge, not the tab, the search box or the sort", () => {
    expect(activeFilterCount(filters())).toBe(0);
    expect(activeFilterCount(filters({ stage: "new", q: "x", sort: "oldest" }))).toBe(0);
    expect(activeFilterCount(filters({ fit: "fits", band: "Strong", work: "remote", country: "MY", live: "active", found: "week" }))).toBe(6);
    expect(activeFilterCount(filters({ work: "remote" }))).toBe(1);
  });

  it("counts jobs per stage chip, with All first", () => {
    const chips = stageChips(jobs, [
      { key: "new", label: "New", description: "d", is_closed: false },
      { key: "active", label: "Active", description: "", is_closed: false },
    ]);
    expect(chips.map((c) => [c.key, c.label, c.count])).toEqual([["", "All", 3], ["new", "New", 2], ["active", "Active", 1]]);
  });

  it("lists the countries of the person's own jobs by name", () => {
    expect(countryOptions([...jobs, job({ id: 9, country: "AE", country_name: "United Arab Emirates" })])).toEqual([
      { code: "MY", name: "Malaysia" },
      { code: "AE", name: "United Arab Emirates" },
    ].sort((a, b) => a.name.localeCompare(b.name)));
  });
});

describe("saved filters", () => {
  const prefs = (over: Partial<Preferences> = {}, filters: Partial<PrefFilters> = {}): Preferences => ({
    ...DEFAULT_PREFERENCES, ...over, filters: { ...DEFAULT_PREFERENCES.filters, ...filters },
  });

  it("starts from the defaults", () => {
    expect(filtersFromPrefs(DEFAULT_PREFERENCES)).toEqual(DEFAULT_FILTERS);
  });

  it("reads the saved tab, sort and the six filters (match is the band, posting is live)", () => {
    expect(filtersFromPrefs(prefs({ tab: "active", sort: "oldest" }, { fit: "fits", match: "Strong", work: "remote", country: "MY", posting: "active", found: "week" }))).toEqual({
      stage: "active", q: "", fit: "fits", band: "Strong", work: "remote", country: "MY", live: "active", found: "week", sort: "oldest", hideWeak: false,
    });
    expect(filtersFromPrefs(prefs({ tab: "all" })).stage).toBe("");
  });

  it("takes the search text as given and ignores junk values", () => {
    expect(filtersFromPrefs(DEFAULT_PREFERENCES, "go lang").q).toBe("go lang");
    expect(filtersFromPrefs(prefs({}, { fit: "bogus", found: "yesterday" }))).toMatchObject({ fit: "", found: "" });
    expect(filtersFromPrefs(prefs({ sort: "sideways" as never })).sort).toBe("best");
  });

  it("drops a stage, country or band that no longer exists", () => {
    const saved = prefs({ tab: "gone" }, { country: "FR", match: "Gone" });
    expect(filtersFromPrefs(saved, "", ["MY"], ["Strong"], ["new"])).toMatchObject({ stage: "", country: "", band: "" });
    const ok = prefs({ tab: "new" }, { country: "MY", match: "Strong" });
    expect(filtersFromPrefs(ok, "", ["MY"], ["Strong"], ["new"])).toMatchObject({ stage: "new", country: "MY", band: "Strong" });
    expect(filtersFromPrefs(prefs({}, { country: "?", match: "__none" }), "", ["MY"], ["Strong"])).toMatchObject({ country: "?", band: "__none" });
  });

  it("turns a change of filters into the patch to save, whole filters object included, and never saves the search text", () => {
    const now = filters({ fit: "fits" });
    expect(patchFromFilters({ q: "x" }, now)).toEqual({});
    expect(patchFromFilters({ stage: "new" }, now)).toEqual({ tab: "new" });
    expect(patchFromFilters({ stage: "" }, now)).toEqual({ tab: "all" });
    expect(patchFromFilters({ sort: "company" }, now)).toEqual({ sort: "company" });
    expect(patchFromFilters({ work: "remote", live: "active" }, now)).toEqual({ filters: { fit: "fits", match: "", work: "remote", country: "", posting: "active", found: "" } });
  });
});

describe("announcements and tabs", () => {
  it("says what is shown after the list changes", () => {
    expect(resultsText(5, 45, "All", "list", true)).toBe("All, list view. Showing 5 of 45.");
    expect(resultsText(45, 45, "Applied", "board", false)).toBe("Applied, board view. Showing all 45.");
  });

  it("moves between tabs with the arrow keys, wrapping, and Home and End", () => {
    expect(nextTabIndex("ArrowRight", 0, 3)).toBe(1);
    expect(nextTabIndex("ArrowRight", 2, 3)).toBe(0);
    expect(nextTabIndex("ArrowLeft", 0, 3)).toBe(2);
    expect(nextTabIndex("Home", 2, 3)).toBe(0);
    expect(nextTabIndex("End", 0, 3)).toBe(2);
    expect(nextTabIndex("a", 0, 3)).toBeNull();
    expect(nextTabIndex("ArrowRight", 0, 0)).toBeNull();
  });

  it("writes the header line of counts", () => {
    expect(headerLine({ total: 0, submitted: 0, average_match: null, urgent: 0 }, 5, null)).toBe("Your job search, in one calm place.");
    expect(headerLine({ total: 12, submitted: 3, average_match: 70, urgent: 2 }, 5, null)).toBe("12 jobs · 3 applied · 2 closing within 5 days. We have not yet looked at which of your jobs are still open.");
    expect(headerLine({ total: 1, submitted: 0, average_match: null, urgent: 0 }, 5, null)).toMatch(/^1 job · 0 applied\. /);
  });
});

describe("the Your search rows", () => {
  const summary = { roles: ["A", "B", "C", "D"], places: [{ place: "Malaysia", mode: "on-site, hybrid" }], remote: "Open to remote", salary_floor: "100,000 BDT/month", alerts_on: true, alerts_available: false, has_cv: true, ai: "keyword" };
  const byKey = (s: typeof summary) => Object.fromEntries(searchRows(s).map((r) => [r.key, r]));

  it("summarises what drives the matches, with where to change each", () => {
    const rows = byKey(summary);
    expect(rows.roles).toMatchObject({ value: "A, B, C and 1 more", to: "/profile", empty: false });
    expect(rows.places).toMatchObject({ value: "Malaysia (on-site, hybrid)", to: "/profile#areas" });
    expect(rows.pay.value).toBe("100,000 BDT/month");
    expect(rows.alerts.value).toMatch(/^On, but nothing is sent yet/);
    expect(rows.cv.value).toBe("Added");
    expect(rows.ai).toMatchObject({ value: "Quick keyword check", to: "/profile/ai" });
  });

  it("says what to add for anything missing", () => {
    const rows = byKey({ ...summary, roles: [], places: [], remote: "", salary_floor: "", alerts_on: false, has_cv: false, ai: "Claude" });
    expect(rows.roles).toMatchObject({ value: "None yet", empty: true });
    expect(rows.places.empty).toBe(true);
    expect(rows.pay).toMatchObject({ value: "Not set", empty: true });
    expect(rows.alerts.value).toBe("Off");
    expect(rows.cv).toMatchObject({ empty: true });
    expect(rows.cv.value).toMatch(/^Missing/);
    expect(rows.ai.value).toBe("Claude");
  });
});

describe("the classic wording", () => {
  it("writes dates short and long", () => {
    expect(shortDate("2026-10-05")).toBe("5 Oct");
    expect(shortDate("2026-10-05", true)).toBe("5 Oct 2026");
    expect(shortDate("soon")).toBe("soon");
  });

  it("says how long ago, in the biggest whole unit", () => {
    const at = (ms: number) => new Date(NOW.getTime() - ms).toISOString();
    expect(timeAgo(at(30_000), NOW)).toBe("a moment");
    expect(timeAgo(at(61_000), NOW)).toBe("1 minute");
    expect(timeAgo(at(3 * 3600_000 + 5000), NOW)).toBe("3 hours");
    expect(timeAgo(at(2 * 86400_000), NOW)).toBe("2 days");
  });

  it("writes the line under the greeting", () => {
    expect(subtitle(0, null)).toBe("Your job search, in one calm place.");
    expect(subtitle(3, null)).toBe("We have not yet looked at which of your jobs are still open.");
    expect(subtitle(3, new Date(NOW.getTime() - 3 * 3600_000).toISOString(), NOW)).toBe("We last looked at which jobs are still open 3 hours ago.");
  });

  it("words the deadline", () => {
    expect(deadlineText({ deadline: null, overdue: false, days_left: null })).toBe("");
    expect(deadlineText({ deadline: "2026-10-20", overdue: true, days_left: -5 })).toBe("Deadline 20 Oct 2026 (it has passed)");
    expect(deadlineText({ deadline: "2026-10-25", overdue: false, days_left: 0 })).toBe("Deadline 25 Oct 2026 (today)");
    expect(deadlineText({ deadline: "2026-10-26", overdue: false, days_left: 1 })).toBe("Deadline 26 Oct 2026 (tomorrow)");
    expect(deadlineText({ deadline: "2026-10-30", overdue: false, days_left: 5 })).toBe("Deadline 30 Oct 2026 (in 5 days)");
  });

  it("shortens like Django's truncatechars", () => {
    expect(truncate("short", 28)).toBe("short");
    expect(truncate("a".repeat(40), 28)).toHaveLength(28);
    expect(truncate("a".repeat(40), 28).endsWith("…")).toBe(true);
  });

  it("explains a repost with the evidence", () => {
    expect(repostTitle({ distinct_urls: 3, distinct_dates: 2, first_seen: "2026-10-01", last_seen: "2026-10-12" })).toBe(
      "Seen as 3 different postings on 2 separate days at this company, same title -- an observation, not a verdict. First seen 1 Oct, last 12 Oct.",
    );
  });

  it("marks a flagged CV that is not approved for review", () => {
    expect(cvBadgeText({ label: "CV v4", flagged: false, approved: false })).toBe("CV v4");
    expect(cvBadgeText({ label: "CV v4", flagged: true, approved: false })).toBe("CV v4 · review");
    expect(cvBadgeText({ label: "CV v4", flagged: true, approved: true })).toBe("CV v4");
  });

  it("writes the applied line only for a job that counts as applied", () => {
    expect(appliedParts(job({ applied_date: "2026-10-05" }))).toEqual([]);
    const parts = appliedParts(job({ applied_date: "2026-10-05", counts_as_applied: true, applied_channel: "Email", applied_cv: { id: 3, label: "CV v3" }, follow_up_date: "2026-10-12" }));
    expect(parts).toEqual([{ text: "Applied 5 Oct 2026 via Email" }, { text: "sent", cv: { id: 3, label: "CV v3" } }, { text: "follow up 12 Oct" }]);
  });

  it("formats an interview time in the person's own time zone", () => {
    expect(interviewWhen(new Date(2026, 9, 5, 14, 30).toISOString())).toBe("Mon 5 Oct, 14:30");
  });

  it("words the import result", () => {
    expect(importMessage({ created: 3, updated: 2 })).toBe("Imported: 3 new, 2 refreshed");
    expect(importMessage({ message: "Imported: 1 new, 0 refreshed" })).toBe("Imported: 1 new, 0 refreshed");
  });

  it("links to a document inside Paperless", () => {
    expect(paperlessDocumentUrl("https://paper.example.com/", 12)).toBe("https://paper.example.com/documents/12/details");
  });
});

describe("the search card", () => {
  const scan = (over: Partial<ScanStatus>): ScanStatus => ({
    running: false, done: 0, total: 0, error: "", found: 0, added: 0, note: "", started_at: null, finished_at: null, phase: "done", entries_count: 0, ...over,
  });

  it("names the phases", () => {
    expect(scanTitle(scan({ running: true, phase: "reading", done: 4, total: 10 }))).toBe("Reading job sources… 4/10");
    expect(scanTitle(scan({ running: true, phase: "reading" }))).toBe("Starting the search…");
    expect(scanTitle(scan({ running: true, phase: "sorting", done: 10, total: 10 }))).toBe("Sorting out the best matches for you…");
    const done = scan({ found: 586, added: 11, started_at: new Date(NOW.getTime() - 2 * 3600_000).toISOString() });
    expect(scanTitle(done, NOW)).toBe("Last search: 2 hours ago — looked through 586 openings, 11 new for you");
  });

  it("fills the bar from the sources read, and completely while sorting", () => {
    expect(scanPercent(scan({ running: true, phase: "reading", done: 5, total: 10 }))).toBe(50);
    expect(scanPercent(scan({ running: true, phase: "reading", done: 0, total: 0 }))).toBe(0);
    expect(scanPercent(scan({ running: true, phase: "sorting", done: 10, total: 10 }))).toBe(100);
  });

  it("words the button while a run goes", () => {
    expect(scanButtonText(null, false)).toBe("Search for jobs");
    expect(scanButtonText(null, true)).toBe("Starting…");
    expect(scanButtonText(scan({ running: true, done: 3, total: 9 }), false)).toBe("Reading 3/9");
    expect(scanButtonText(scan({ running: true, phase: "sorting", done: 9, total: 9 }), false)).toBe("Sorting…");
    expect(scanButtonText(scan({}), false)).toBe("Search for jobs");
    expect(checkButtonText(false, false, 0, 0)).toBe("Check which are still open");
    expect(checkButtonText(false, true, 0, 0)).toBe("Starting…");
    expect(checkButtonText(true, false, 2, 7)).toBe("Checking 2/7…");
  });

  it("writes one line per source", () => {
    const base = { source: "Acme", connector: "Greenhouse", found: 5, matched: 3, added: 2, duplicates: 1, outside: 0, error: "" };
    expect(entryText(base)).toBe("5 found, 3 matched, 2 new, 1 already tracked");
    expect(entryText({ ...base, outside: 4 })).toBe("5 found, 3 matched, 2 new, 1 already tracked, 4 outside your areas");
    expect(entryText({ ...base, error: "HTTP 500" })).toBe("HTTP 500");
  });
});

describe("empty states and links", () => {
  it("picks the classic message", () => {
    expect(emptyKind(3, 2, null)).toBeNull();
    expect(emptyKind(3, 0, null)).toBe("no-matches");
    expect(emptyKind(0, 0, { running: true, added: 0 })).toBe("searching");
    expect(emptyKind(0, 0, { running: false, added: 0 })).toBe("nothing-matched");
    expect(emptyKind(0, 0, { running: false, added: 4 })).toBe("no-jobs");
    expect(emptyKind(0, 0, null)).toBe("no-jobs");
    expect(emptyKind(3, 0, null, 0)).toBe("stage-empty"); // the chosen stage holds nothing: not a filter that is too strict
    expect(emptyKind(3, 0, null, 2)).toBe("no-matches");
  });

  it("sends a next-step button to the right place", () => {
    expect(nextStepTarget("#job-12")).toEqual({ kind: "card", id: "job-12" });
    expect(nextStepTarget("/app/profile?welcome=1")).toEqual({ kind: "app", to: "/profile?welcome=1" });
    expect(nextStepTarget("/app/profile#areas")).toEqual({ kind: "app", to: "/profile#areas" });
    expect(nextStepTarget("/app/jobs/add")).toEqual({ kind: "app", to: "/jobs/add" });
    expect(nextStepTarget("/app/prep/3/today")).toEqual({ kind: "app", to: "/prep/3/today" });
    expect(nextStepTarget("/admin/")).toEqual({ kind: "other", href: "/admin/" });
    expect(nextStepTarget("/application/")).toEqual({ kind: "other", href: "/application/" });
  });
});
