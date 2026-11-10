// The dashboard's rules in one place (ported from frontend/src/features/dashboard/{logic,jobmgmt,checklist,coming-up}.ts).
import type { Bucket, ComingUpItem, Dashboard, Job, Preferences, PreferencePatch, PrefFilters, ScanEntry, ScanStatus, SortKey, StatusInfo } from "../../api/dashboard";

export type Filters = {
  stage: string;
  q: string;
  fit: "" | "fits" | "check" | "unknown";
  band: string;
  work: string;
  country: string;
  live: string;
  found: "" | "today" | "week";
  sort: SortKey;
  hideWeak: boolean;
};

export const DEFAULT_FILTERS: Filters = { stage: "", q: "", fit: "", band: "", work: "", country: "", live: "", found: "", sort: "best", hideWeak: false };
export const WEAK_BELOW = 40;
export const NOT_STATED = "__none";
export const COUNTRY_NOT_STATED = "?";

export const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "best", label: "Best match first" },
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "company", label: "Company A to Z" },
  { value: "deadline", label: "Closing soonest" },
];

const PANEL_FILTERS = ["fit", "band", "work", "country", "live", "found"] as const;

export const isWeak = (job: Pick<Job, "percent">) => job.percent !== null && job.percent < WEAK_BELOW;
export const activeFilterCount = (f: Filters) => PANEL_FILTERS.filter((k) => f[k] !== "").length + (f.hideWeak ? 1 : 0);
export const isFiltered = (f: Filters) => f.q.trim() !== "" || activeFilterCount(f) > 0;

export function fitValue(job: Job): "fits" | "check" | "unknown" {
  return job.fit_level === "ok" ? "fits" : job.fit_level === "warn" ? "check" : "unknown";
}

export function localDay(now: Date, offset = 0): string {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - offset);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function jobsByBucket(jobs: Job[], buckets: Bucket[]): Record<string, Job[]> {
  const out: Record<string, Job[]> = Object.fromEntries(buckets.map((b) => [b.key, []]));
  for (const job of jobs) (out[job.bucket_key] ??= []).push(job);
  return out;
}

function matches(job: Job, f: Filters, words: string[], today: string, weekAgo: string): boolean {
  if (f.stage && job.bucket_key !== f.stage) return false;
  if (f.hideWeak && isWeak(job)) return false;
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
  const sorters: Record<SortKey, (a: Job, b: Job) => number> = {
    best: byOrder,
    newest: (a, b) => b.found_date.localeCompare(a.found_date) || b.id - a.id,
    oldest: (a, b) => (a.found_date || "9999").localeCompare(b.found_date || "9999") || a.id - b.id,
    company: (a, b) => a.company.toLowerCase().localeCompare(b.company.toLowerCase()) || byOrder(a, b),
    deadline: (a, b) => (a.deadline ?? "9999").localeCompare(b.deadline ?? "9999") || byOrder(a, b),
  };
  return jobs.filter((j) => matches(j, filters, words, today, weekAgo)).sort(sorters[filters.sort] ?? sorters.best);
}

export function hiddenWeakCount(jobs: Job[], filters: Filters, now: Date = new Date()): number {
  if (!filters.hideWeak) return 0;
  return visibleJobs(jobs, { ...filters, hideWeak: false }, now).length - visibleJobs(jobs, filters, now).length;
}

export function stageChips(jobs: Job[], buckets: Bucket[]) {
  const counts = jobsByBucket(jobs, buckets);
  return [{ key: "", label: "All", description: "", count: jobs.length }, ...buckets.map((b) => ({ key: b.key, label: b.label, description: b.description, count: counts[b.key]?.length ?? 0 }))];
}

export function countryOptions(jobs: Job[]): { code: string; name: string }[] {
  const seen = new Map<string, string>();
  for (const j of jobs) if (j.country) seen.set(j.country, j.country_name || j.country);
  return [...seen].map(([code, name]) => ({ code, name })).sort((a, b) => a.name.localeCompare(b.name));
}

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
    hideWeak: prefs.hide_weak === true,
  };
  if (state.stage && stages.length && !stages.includes(state.stage)) state = { ...state, stage: "" };
  if (state.country && state.country !== COUNTRY_NOT_STATED && countries.length && !countries.includes(state.country)) state = { ...state, country: "" };
  if (state.band && state.band !== NOT_STATED && bands.length && !bands.includes(state.band)) state = { ...state, band: "" };
  return state;
}

export function patchFromFilters(patch: Partial<Filters>, current: Filters): PreferencePatch {
  const next = { ...current, ...patch };
  const out: PreferencePatch = {};
  if ("stage" in patch) out.tab = next.stage === "" ? "all" : next.stage;
  if ("sort" in patch) out.sort = next.sort;
  if ("hideWeak" in patch) out.hide_weak = next.hideWeak;
  if (PANEL_FILTERS.some((k) => k in patch)) {
    const filters: PrefFilters = { fit: next.fit, match: next.band, work: next.work, country: next.country, posting: next.live, found: next.found };
    out.filters = filters;
  }
  return out;
}

// ---- words and dates ---------------------------------------------------------------------------------------------------

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function shortDate(iso: string, year = false): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]}${year ? ` ${m[1]}` : ""}`;
}

export function interviewWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function timeAgo(iso: string, now: Date = new Date()): string {
  const seconds = Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / 1000));
  const units: [string, number][] = [["year", 31536000], ["month", 2592000], ["week", 604800], ["day", 86400], ["hour", 3600], ["minute", 60]];
  for (const [name, size] of units) {
    const n = Math.floor(seconds / size);
    if (n >= 1) return `${n} ${name}${n === 1 ? "" : "s"}`;
  }
  return "a moment";
}

export function subtitle(total: number, checkedAt: string | null, now: Date = new Date()): string {
  if (!total) return "Your job search, in one calm place.";
  return checkedAt ? `We last looked at which jobs are still open ${timeAgo(checkedAt, now)} ago.` : "We have not yet looked at which of your jobs are still open.";
}

export function headerLine(stats: Dashboard["stats"], urgentDays: number, checkedAt: string | null): string {
  if (!stats.total) return subtitle(0, checkedAt);
  const parts = [`${stats.total} ${stats.total === 1 ? "job" : "jobs"}`, `${stats.submitted} applied`];
  if (stats.urgent > 0) parts.push(`${stats.urgent} closing within ${urgentDays} days`);
  return `${parts.join(" · ")}. ${subtitle(stats.total, checkedAt)}`;
}

export function deadlineText(job: Pick<Job, "deadline" | "overdue" | "days_left">): string {
  if (!job.deadline) return "";
  const when = job.overdue ? "(it has passed)" : job.days_left === 0 ? "(today)" : job.days_left === 1 ? "(tomorrow)" : `(in ${job.days_left} days)`;
  return `Deadline ${shortDate(job.deadline, true)} ${when}`;
}

export const truncate = (text: string, n: number) => (text.length <= n ? text : `${text.slice(0, Math.max(0, n - 1))}…`);

export const repostTitle = (r: NonNullable<Job["repost"]>) =>
  `Seen as ${r.distinct_urls} different postings on ${r.distinct_dates} separate days at this company, same title. An observation, not a verdict. First seen ${shortDate(r.first_seen)}, last ${shortDate(r.last_seen)}.`;

export function livingBadge(state: Job["live_state"]): { text: string; tone: "good" | "bad" | "warn" } | null {
  if (state === "active") return { text: "Open", tone: "good" };
  if (state === "expired") return { text: "Closed", tone: "bad" };
  if (state === "uncertain") return { text: "Unclear", tone: "warn" };
  return null;
}

export const FIT_BADGE_TEXT = { fits: "Fits", check: "Check fit", unknown: "Fit unknown" } as const;
export const cvBadgeText = (cv: { label: string; flagged: boolean; approved: boolean }) => `${cv.label}${cv.flagged && !cv.approved ? " · review" : ""}`;

export function appliedParts(job: Job): string[] {
  if (!job.applied_date || !job.counts_as_applied) return [];
  const parts = [`Applied ${shortDate(job.applied_date, true)}${job.applied_channel ? ` via ${job.applied_channel}` : ""}`];
  if (job.applied_cv) parts.push(`sent ${job.applied_cv.label}`);
  if (job.follow_up_date) parts.push(`follow up ${shortDate(job.follow_up_date)}`);
  return parts;
}

// ---- the search card ---------------------------------------------------------------------------------------------------

export function scanPercent(s: Pick<ScanStatus, "done" | "total" | "phase">): number {
  if (s.phase === "sorting") return 100;
  return s.total ? Math.min(100, Math.round((100 * s.done) / s.total)) : 0;
}

export function scanTitle(s: ScanStatus): string {
  if (s.running) {
    if (s.phase === "sorting") return "Sorting out the best matches for you…";
    return s.total ? `Reading job sources… ${s.done}/${s.total}` : "Starting the search…";
  }
  const when = s.started_at ? `${timeAgo(s.started_at)} ago` : "a while ago";
  return `Last search: ${when}. Looked through ${s.found} openings, ${s.added} new for you.`;
}

export function scanButtonText(s: ScanStatus | null, starting: boolean): string {
  if (starting && !s?.running) return "Starting…";
  if (!s?.running) return "Find jobs now";
  if (s.phase === "sorting") return "Sorting…";
  return s.total ? `Reading ${s.done}/${s.total}` : "Starting…";
}

export const entryText = (e: ScanEntry) =>
  e.error || `${e.found} found, ${e.matched} matched, ${e.added} new, ${e.duplicates} already tracked${e.outside ? `, ${e.outside} outside your areas` : ""}`;

export const checkButtonText = (running: boolean, starting: boolean, done: number, total: number) =>
  running ? `Checking ${done}/${total}…` : starting ? "Starting…" : "Check which are still open";

export type EmptyKind = "searching" | "nothing-matched" | "no-jobs" | "no-matches" | "stage-empty";

export function emptyKind(total: number, shown: number, scan: Pick<ScanStatus, "running" | "added"> | null, inStage: number = total): EmptyKind | null {
  if (shown > 0) return null;
  if (total > 0) return inStage === 0 ? "stage-empty" : "no-matches";
  if (scan?.running) return "searching";
  if (scan && !scan.added) return "nothing-matched";
  return "no-jobs";
}

export function troubleLine(t: { total: number; trouble: number } | null | undefined): string {
  if (!t || t.trouble <= 0) return "";
  return `${t.trouble} of ${t.total} ${t.total === 1 ? "source" : "sources"} had trouble in the last search.`;
}

/** Where a next-step button goes: inside the app, to a card on this screen, or to another address. */
export function nextStepTarget(url: string): { kind: "app"; to: string } | { kind: "card"; id: number } | { kind: "other"; href: string } {
  if (url.startsWith("#job-")) return { kind: "card", id: Number(url.slice(5)) };
  if (url === "/app" || url.startsWith("/app/") || url.startsWith("/app?") || url.startsWith("/app#")) return { kind: "app", to: url.slice(4) || "/" };
  return { kind: "other", href: url };
}

// ---- checklist, coming up, worth a look ---------------------------------------------------------------------------------

export type ChecklistStep = { key: string; label: string; done: boolean; to: string; cta: string };

export function checklistSteps(data: Pick<Dashboard, "search_summary" | "jobs" | "scan">): ChecklistStep[] {
  const roles = data.search_summary?.roles ?? [];
  return [
    { key: "roles", label: "Tell us which roles you want", done: roles.length > 0, to: "/profile", cta: "Add roles" },
    { key: "cv", label: "Add your CV", done: data.search_summary?.has_cv === true, to: "/cv/new", cta: "Add a CV" },
    { key: "search", label: "Run your first job search", done: Boolean(data.scan?.finished_at), to: "", cta: "Find jobs now" },
    { key: "job", label: "Track your first job", done: data.jobs.length > 0, to: "/jobs/add", cta: "Add a job" },
    { key: "fit", label: "Press Check my fit on a job", done: data.jobs.some((j) => j.evaluated || j.percent !== null), to: "", cta: "See your jobs" },
  ];
}

export const showChecklist = (steps: ChecklistStep[], dismissed: boolean) => !dismissed && steps.filter((s) => s.done).length < 3;

export const COMING_UP_WORD: Record<ComingUpItem["kind"], string> = { interview: "Interview", deadline: "Apply by", offer: "Reply to offer" };

export function comingUpItems(data: Pick<Dashboard, "coming_up" | "upcoming_interviews">): ComingUpItem[] {
  if (data.coming_up) return data.coming_up;
  return data.upcoming_interviews.map((i) => ({ kind: "interview" as const, date: i.when.slice(0, 10), when: i.when, label: i.kind, company: i.company, role: i.role, job_id: i.job_id }));
}

export function comingUpTo(item: ComingUpItem): string {
  if (item.kind === "interview") return "/interviews";
  if (item.kind === "offer") return "/offers";
  return `/jobs/${item.job_id}/apply`;
}

export function comingUpText(item: ComingUpItem): string {
  const when = item.kind === "interview" ? interviewWhen(item.when) : shortDate(item.date);
  const lead = item.kind === "interview" ? `${COMING_UP_WORD.interview} · ${when} · ${item.label}` : `${COMING_UP_WORD[item.kind]} · ${when}`;
  return `${lead}: ${item.company}, ${item.role}`;
}

export function worthTo(i: { kind: string; job_id: number; version_id?: number }): string {
  if (i.kind === "interview") return "/interviews";
  if (i.kind === "offer") return "/offers";
  if (i.kind === "draft" && i.version_id) return `/cv/${i.version_id}`;
  return `/jobs/${i.job_id}/apply`;
}

export const WORTH_WORD: Record<string, string> = { interview: "Interview", offer: "Offer", followup: "Follow up", draft: "CV draft", quiet: "Quiet" };

// ---- choosing several jobs ----------------------------------------------------------------------------------------------

export function notForMeStatus(statuses: StatusInfo[]): StatusInfo | undefined {
  return (
    statuses.find((s) => s.name === "Not for me") ??
    statuses.find((s) => s.name === "Discarded") ??
    statuses.find((s) => !s.counts_as_applied && s.name !== "Skipped" && /closed|skip|discard/i.test(s.bucket_key))
  );
}

export const statusLabel = (s: Pick<StatusInfo, "name" | "label"> | undefined) => (s ? s.label || s.name : "its new status");

export function toggleId(selected: ReadonlySet<number>, id: number): Set<number> {
  const next = new Set(selected);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}
export const pruneSelection = (selected: ReadonlySet<number>, jobs: Pick<Job, "id">[]) => {
  const present = new Set(jobs.map((j) => j.id));
  return new Set([...selected].filter((id) => present.has(id)));
};
export const allSelected = (selected: ReadonlySet<number>, jobs: Pick<Job, "id">[]) => jobs.length > 0 && jobs.every((j) => selected.has(j.id));

const njobs = (n: number) => `${n} ${n === 1 ? "job" : "jobs"}`;
export const selectedText = (count: number) => (count === 0 ? "Choose the jobs you want to act on." : `${count} selected`);
export const movedText = (count: number, label: string, role?: string) => (count === 1 && role ? `Moved ${role} to ${label}.` : `Moved ${njobs(count)} to ${label}.`);
export const undoText = (count: number, label: string, role?: string) =>
  count === 1 && role ? `${role} is now ${label}.` : `${njobs(count)} ${count === 1 ? "is" : "are"} now ${label}.`;
export const removedText = (count: number, role?: string) => (count === 1 && role ? `Removed ${role}.` : `Removed ${njobs(count)}.`);
export const weakLine = (hidden: number) => (hidden === 0 ? "" : `${hidden} weak ${hidden === 1 ? "match is" : "matches are"} hidden (under 40%).`);
export const archivedText = (count: number, role?: string) =>
  count === 1 && role ? `Archived ${role}. You can bring it back from Archived, below your list.` : `Archived ${njobs(count)}. You can bring them back from Archived, below your list.`;

/** A mailto: or http(s) link for the address a posting publishes, else "". */
export function applyHref(address: string | undefined | null): string {
  const a = (address ?? "").trim();
  if (/^https?:\/\//i.test(a)) return a;
  return /^[^\s@<>"']+@[^\s@<>"']+\.[A-Za-z]{2,}$/.test(a) ? `mailto:${a}` : "";
}

/** The IANA zone this device is in, or "". */
export function deviceZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch {
    return "";
  }
}

function canonicalZone(name: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, { timeZone: name }).resolvedOptions().timeZone;
  } catch {
    return "";
  }
}

export function shouldSuggestZone(opts: { device: string; saved: string; site: string; dismissed: boolean }): boolean {
  if (opts.dismissed || !canonicalZone(opts.device)) return false;
  const current = opts.saved || opts.site;
  if (!current) return false;
  return canonicalZone(opts.device) !== canonicalZone(current);
}
