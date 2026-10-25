import type { Bucket, Dashboard, Job, PreferencePatch, Preferences, PrefFilters, Repost, ScanEntry, ScanStatus, SearchSummary, SortKey, StatusInfo } from "@/lib/types";

/** The status a card gets when it is dropped on a column: the column's first status, in the order the admin set. */
export function statusForColumn(statuses: StatusInfo[], bucketKey: string): StatusInfo | undefined {
  return statuses.find((s) => s.bucket_key === bucketKey);
}

/** Move a job in a cached dashboard without waiting for the server (the caller rolls back if the server refuses). */
export function applyMove(data: Dashboard, jobId: number, status: StatusInfo): Dashboard {
  return {
    ...data,
    jobs: data.jobs.map((j) => (j.id === jobId ? { ...j, status_id: status.id, bucket_key: status.bucket_key } : j)),
  };
}

export function jobsByBucket(jobs: Job[], buckets: Bucket[]): Record<string, Job[]> {
  const out: Record<string, Job[]> = Object.fromEntries(buckets.map((b) => [b.key, []]));
  for (const job of jobs) (out[job.bucket_key] ??= []).push(job);
  return out;
}

// ---- filters and sorting (the classic dashboard's rules, in one place) ----------------------------------------------

export type Sort = SortKey;

export type Filters = {
  stage: string;
  q: string;
  fit: "" | "fits" | "check" | "unknown";
  band: string;
  work: string;
  country: string;
  live: string;
  found: "" | "today" | "week";
  sort: Sort;
};

export const DEFAULT_FILTERS: Filters = { stage: "", q: "", fit: "", band: "", work: "", country: "", live: "", found: "", sort: "best" };

export const NOT_STATED = "__none";
export const COUNTRY_NOT_STATED = "?";

export const SORT_OPTIONS: { value: Sort; label: string }[] = [
  { value: "best", label: "Best match first" },
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "company", label: "Company A to Z" },
  { value: "deadline", label: "Closing soonest" },
];

/** The six saved filters (the filter panel's dropdowns). */
const PANEL_FILTERS = ["fit", "band", "work", "country", "live", "found"] as const;

/** How many of the six panel filters are set: the badge on the Filters button. The stage tab, the search box and the sort order are not counted. */
export function activeFilterCount(filters: Filters): number {
  return PANEL_FILTERS.filter((k) => filters[k] !== "").length;
}

/** Whether the search box or any panel filter narrows the list (the "Clear filters" button and the "Showing N of M" wording). */
export function isFiltered(filters: Filters): boolean {
  return filters.q.trim() !== "" || activeFilterCount(filters) > 0;
}

/** "Fits your places" for filtering: every job has one, even when the person has named no places (the badge itself is hidden then). */
export function fitValue(job: Job): "fits" | "check" | "unknown" {
  return job.fit_level === "ok" ? "fits" : job.fit_level === "warn" ? "check" : "unknown";
}

/** A calendar day as YYYY-MM-DD in the person's own time zone, `offset` days back from `now`. */
export function localDay(now: Date, offset = 0): string {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - offset);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function matches(job: Job, f: Filters, words: string[], today: string, weekAgo: string): boolean {
  if (f.stage && job.bucket_key !== f.stage) return false;
  if (words.length) {
    const text = `${job.company} ${job.role} ${job.location} ${job.country_name}`.toLowerCase();
    if (!words.every((w) => text.includes(w))) return false;
  }
  if (f.fit && fitValue(job) !== f.fit) return false;
  if (f.band && (f.band === NOT_STATED ? job.percent !== null : job.band?.label !== f.band)) return false;
  if (f.work && (f.work === NOT_STATED ? job.arrangement !== "" : job.arrangement !== f.work)) return false;
  if (f.country && (f.country === COUNTRY_NOT_STATED ? job.country !== "" : job.country !== f.country)) return false;
  if (f.live && job.live_state !== f.live) return false;
  if (f.found === "today" && job.found_date !== today) return false;
  if (f.found === "week" && !(job.found_date !== "" && job.found_date >= weekAgo)) return false;
  return true;
}

/** The jobs the filters keep, in the chosen order. "Best" is the server's order (urgent first, then best match). */
export function visibleJobs(jobs: Job[], filters: Filters, now: Date = new Date()): Job[] {
  const words = filters.q.toLowerCase().split(/\s+/).filter(Boolean);
  const today = localDay(now);
  const weekAgo = localDay(now, 7);
  const order = new Map(jobs.map((j, i) => [j.id, i]));
  const byOrder = (a: Job, b: Job) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0);
  const sorters: Record<Sort, (a: Job, b: Job) => number> = {
    best: byOrder,
    newest: (a, b) => b.found_date.localeCompare(a.found_date) || b.id - a.id,
    oldest: (a, b) => (a.found_date || "9999").localeCompare(b.found_date || "9999") || a.id - b.id,
    company: (a, b) => a.company.toLowerCase().localeCompare(b.company.toLowerCase()) || byOrder(a, b),
    deadline: (a, b) => (a.deadline ?? "9999").localeCompare(b.deadline ?? "9999") || byOrder(a, b),
  };
  return jobs.filter((j) => matches(j, filters, words, today, weekAgo)).sort(sorters[filters.sort] ?? sorters.best);
}

/** Stage chips: "All (n)" first, then one per column with how many jobs it holds (before any other filter). */
export function stageChips(jobs: Job[], buckets: Bucket[]): { key: string; label: string; description: string; count: number }[] {
  const counts = jobsByBucket(jobs, buckets);
  return [
    { key: "", label: "All", description: "", count: jobs.length },
    ...buckets.map((b) => ({ key: b.key, label: b.label, description: b.description, count: counts[b.key]?.length ?? 0 })),
  ];
}

/** The countries the person's own jobs name, by name, for the Country filter. */
export function countryOptions(jobs: Job[]): { code: string; name: string }[] {
  const seen = new Map<string, string>();
  for (const j of jobs) if (j.country) seen.set(j.country, j.country_name || j.country);
  return [...seen].map(([code, name]) => ({ code, name })).sort((a, b) => a.name.localeCompare(b.name));
}

/** The saved preferences as the dashboard's filters. `q` is the search text (never saved: it comes from the header search box or the address). */
export function filtersFromPrefs(prefs: Preferences, q = "", countries: string[] = [], bands: string[] = [], stages: string[] = []): Filters {
  const f = prefs.filters;
  let state: Filters = {
    stage: prefs.tab === "all" ? "" : prefs.tab,
    q,
    fit: f.fit === "fits" || f.fit === "check" || f.fit === "unknown" ? f.fit : "",
    band: f.match,
    work: f.work,
    country: f.country,
    live: f.posting,
    found: f.found === "today" || f.found === "week" ? f.found : "",
    sort: SORT_OPTIONS.some((o) => o.value === prefs.sort) ? prefs.sort : "best",
  };
  if (state.stage && stages.length && !stages.includes(state.stage)) state = { ...state, stage: "" };
  if (state.country && state.country !== COUNTRY_NOT_STATED && countries.length && !countries.includes(state.country)) state = { ...state, country: "" };
  if (state.band && state.band !== NOT_STATED && bands.length && !bands.includes(state.band)) state = { ...state, band: "" };
  return state;
}

/** The change to save for a change of filters (`q` is not saved, so it makes no patch). */
export function patchFromFilters(patch: Partial<Filters>, current: Filters): PreferencePatch {
  const next = { ...current, ...patch };
  const out: PreferencePatch = {};
  if ("stage" in patch) out.tab = next.stage === "" ? "all" : next.stage;
  if ("sort" in patch) out.sort = next.sort;
  if (PANEL_FILTERS.some((k) => k in patch)) {
    const filters: PrefFilters = { fit: next.fit, match: next.band, work: next.work, country: next.country, posting: next.live, found: next.found };
    out.filters = filters;
  }
  return out;
}

/** The sentence a screen reader hears after the list changes (a filter, a stage tab, the layout). */
export function resultsText(shown: number, inStage: number, stageLabel: string, view: "list" | "board", filtered: boolean): string {
  const count = filtered ? `Showing ${shown} of ${inStage}` : `Showing all ${inStage}`;
  return `${stageLabel}, ${view} view. ${count}.`;
}

/** The tab that arrow keys, Home and End move to (the tabs wrap around). */
export function nextTabIndex(key: string, index: number, length: number): number | null {
  if (length === 0) return null;
  if (key === "ArrowRight") return (index + 1) % length;
  if (key === "ArrowLeft") return (index - 1 + length) % length;
  if (key === "Home") return 0;
  if (key === "End") return length - 1;
  return null;
}

// ---- the "Your search" card -------------------------------------------------------------------------------------------------

export type SummaryRow = { key: string; label: string; value: string; empty: boolean; to: string; action: string };

/** One row per thing that drives the matches, each with where to change it. An empty row says what to add. */
export function searchRows(s: SearchSummary): SummaryRow[] {
  const roles = s.roles.length > 3 ? `${s.roles.slice(0, 3).join(", ")} and ${s.roles.length - 3} more` : s.roles.join(", ");
  const places = s.places.map((p) => (p.mode ? `${p.place} (${p.mode})` : p.place)).join(", ");
  const alerts = s.alerts_on ? (s.alerts_available ? "On" : "On, but nothing is sent yet: the site owner has not switched emails on") : "Off";
  return [
    { key: "roles", label: "Roles you want", value: roles || "None yet", empty: !roles, to: "/profile", action: "roles" },
    { key: "places", label: "Where you would work", value: places || "None yet", empty: !places, to: "/profile#areas", action: "places" },
    { key: "remote", label: "Remote work", value: s.remote || "Not set", empty: !s.remote, to: "/profile#areas", action: "remote preference" },
    { key: "pay", label: "Minimum pay", value: s.salary_floor || "Not set", empty: !s.salary_floor, to: "/profile", action: "minimum pay" },
    { key: "alerts", label: "Job alerts by email", value: alerts, empty: !s.alerts_on, to: "/profile", action: "job alerts" },
    { key: "cv", label: "Your CV", value: s.has_cv ? "Added" : "Missing. Add it so we can judge fit", empty: !s.has_cv, to: "/profile", action: "CV" },
    { key: "ai", label: "How fit is judged", value: s.ai === "keyword" ? "Quick keyword check" : s.ai, empty: false, to: "/profile/ai", action: "how fit is judged" },
  ];
}

// ---- words and dates, the classic wording ----------------------------------------------------------------------------

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function parseDay(iso: string): { y: number; m: number; d: number } | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? { y: Number(m[1]), m: Number(m[2]), d: Number(m[3]) } : null;
}

/** "2026-10-25" as "25 Oct" (or "25 Oct 2026" with `year`). Anything else comes back unchanged. */
export function shortDate(iso: string, year = false): string {
  const p = parseDay(iso);
  if (!p) return iso;
  return `${p.d} ${MONTHS[p.m - 1]}${year ? ` ${p.y}` : ""}`;
}

/** "Mon 5 Oct, 14:30" in the person's own time zone. */
export function interviewWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** "3 hours", "2 days": the biggest whole unit between then and now (like the classic "N ago"). */
export function timeAgo(iso: string, now: Date = new Date()): string {
  const seconds = Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / 1000));
  const units: [string, number][] = [["year", 31536000], ["month", 2592000], ["week", 604800], ["day", 86400], ["hour", 3600], ["minute", 60]];
  for (const [name, size] of units) {
    const n = Math.floor(seconds / size);
    if (n >= 1) return `${n} ${name}${n === 1 ? "" : "s"}`;
  }
  return "a moment";
}

/** The line under the greeting. */
export function subtitle(total: number, checkedAt: string | null, now: Date = new Date()): string {
  if (!total) return "Your job search, in one calm place.";
  return checkedAt ? `We last looked at which jobs are still open ${timeAgo(checkedAt, now)} ago.` : "We have not yet looked at which of your jobs are still open.";
}

/** The one line of counts under the greeting, then when the open/closed check last ran. */
export function headerLine(stats: Dashboard["stats"], urgentDays: number, checkedAt: string | null, now: Date = new Date()): string {
  if (!stats.total) return subtitle(0, checkedAt, now);
  const jobs = `${stats.total} ${stats.total === 1 ? "job" : "jobs"}`;
  const parts = [jobs, `${stats.submitted} applied`];
  if (stats.urgent > 0) parts.push(`${stats.urgent} closing within ${urgentDays} days`);
  return `${parts.join(" · ")}. ${subtitle(stats.total, checkedAt, now)}`;
}

/** "Deadline 5 Nov 2026 (in 3 days)", with the words the classic card used. */
export function deadlineText(job: Pick<Job, "deadline" | "overdue" | "days_left">): string {
  if (!job.deadline) return "";
  const when = job.overdue ? "(it has passed)" : job.days_left === 0 ? "(today)" : job.days_left === 1 ? "(tomorrow)" : `(in ${job.days_left} days)`;
  return `Deadline ${shortDate(job.deadline, true)} ${when}`;
}

/** Django's `truncatechars`: at most n characters, the last one an ellipsis. */
export function truncate(text: string, n: number): string {
  return text.length <= n ? text : `${text.slice(0, Math.max(0, n - 1))}…`;
}

export function repostTitle(r: Repost): string {
  return `Seen as ${r.distinct_urls} different postings on ${r.distinct_dates} separate days at this company, same title -- an observation, not a verdict. First seen ${shortDate(r.first_seen)}, last ${shortDate(r.last_seen)}.`;
}

export const SKILL_MATCH_TITLE = "Found by overlap with your own CV's skills, not a listed target role -- see Details below for which terms matched.";

export function livingBadge(state: Job["live_state"]): { text: string; tone: "good" | "bad" | "warn" } | null {
  if (state === "active") return { text: "Open", tone: "good" };
  if (state === "expired") return { text: "Closed", tone: "bad" };
  if (state === "uncertain") return { text: "Unclear", tone: "warn" };
  return null;
}

export const FIT_BADGE_TEXT = { fits: "Fits", check: "Check fit", unknown: "Fit unknown" } as const;

export function cvBadgeText(cv: { label: string; flagged: boolean; approved: boolean }): string {
  return `${cv.label}${cv.flagged && !cv.approved ? " · review" : ""}`;
}

/** "Applied 5 Oct 2026 via Email · sent CV v3 · follow up 12 Oct" pieces, in order. */
export function appliedParts(job: Job): { text: string; cv?: { id: number; label: string } }[] {
  if (!job.applied_date || !job.counts_as_applied) return [];
  const parts: { text: string; cv?: { id: number; label: string } }[] = [{ text: `Applied ${shortDate(job.applied_date, true)}${job.applied_channel ? ` via ${job.applied_channel}` : ""}` }];
  if (job.applied_cv) parts.push({ text: "sent", cv: job.applied_cv });
  if (job.follow_up_date) parts.push({ text: `follow up ${shortDate(job.follow_up_date)}` });
  return parts;
}

// ---- the search card ------------------------------------------------------------------------------------------------------

export function scanPercent(s: Pick<ScanStatus, "running" | "done" | "total" | "phase">): number {
  if (s.phase === "sorting") return 100;
  return s.total ? Math.min(100, Math.round((100 * s.done) / s.total)) : 0;
}

export function scanTitle(s: ScanStatus, now: Date = new Date()): string {
  if (s.running) {
    if (s.phase === "sorting") return "Sorting out the best matches for you…";
    return s.total ? `Reading job sources… ${s.done}/${s.total}` : "Starting the search…";
  }
  const when = s.started_at ? `${timeAgo(s.started_at, now)} ago` : "a while ago";
  return `Last search: ${when} — looked through ${s.found} openings, ${s.added} new for you`;
}

/** The words on the "Search jobs" button while a run is going. */
export function scanButtonText(s: ScanStatus | null, starting: boolean): string {
  if (starting && !s?.running) return "Starting…";
  if (!s?.running) return "Search for jobs";
  if (s.phase === "sorting") return "Sorting…";
  return s.total ? `Reading ${s.done}/${s.total}` : "Starting…";
}

export function entryText(e: ScanEntry): string {
  if (e.error) return e.error;
  return `${e.found} found, ${e.matched} matched, ${e.added} new, ${e.duplicates} already tracked${e.outside ? `, ${e.outside} outside your areas` : ""}`;
}

export function checkButtonText(running: boolean, starting: boolean, done: number, total: number): string {
  if (running) return `Checking ${done}/${total}…`;
  return starting ? "Starting…" : "Check which are still open";
}

// ---- empty states, the next-step link, and the import result -----------------------------------------------------------

export type EmptyKind = "searching" | "nothing-matched" | "no-jobs" | "nothing-here" | "no-matches" | "stage-empty";

/** Which empty message the list shows (the classic page's variants); null when there is something to show. */
/** `inStage` is how many jobs the chosen stage tab holds (default all): an empty stage is not a failed filter. */
export function emptyKind(total: number, shown: number, scan: Pick<ScanStatus, "running" | "added"> | null, inStage: number = total): EmptyKind | null {
  if (shown > 0) return null;
  if (total > 0) return inStage === 0 ? "stage-empty" : "no-matches";
  if (scan?.running) return "searching";
  if (scan && !scan.added) return "nothing-matched";
  return "no-jobs";
}

/** Where a next-step button goes: inside the app, to a card on this page, or to another address. */
export function nextStepTarget(url: string): { kind: "app"; to: string } | { kind: "card"; id: string } | { kind: "other"; href: string } {
  if (url.startsWith("#job-")) return { kind: "card", id: url.slice(1) };
  if (url === "/app" || url.startsWith("/app/") || url.startsWith("/app?") || url.startsWith("/app#")) return { kind: "app", to: url.slice(4) || "/" };
  return { kind: "other", href: url };
}

export function importMessage(r: { created?: number; updated?: number; message?: string }): string {
  return r.message ?? `Imported: ${r.created ?? 0} new, ${r.updated ?? 0} refreshed`;
}

/** The link to a document inside Paperless. */
export function paperlessDocumentUrl(base: string, id: number): string {
  return `${base.replace(/\/+$/, "")}/documents/${id}/details`;
}
