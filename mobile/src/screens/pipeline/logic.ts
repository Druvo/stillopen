// Pure helpers for the pipeline and insights screens (no React, no network): dates, money, plain-words sentences, chart maths.
// Ported from the website's frontend/src/features/{pipeline,stats}/*logic.ts so both say the same things.
import type { Activity, CalendarItem, CalendarMonth, Funnel, Goals, Period, Stats } from "../../api/stats";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const pad = (n: number) => String(n).padStart(2, "0");

/** "2026-09-29" (or a full timestamp) as "29 Sep 2026", the calendar day as written, never shifted by a time zone. */
export function dayLabel(iso: string | null | undefined): string {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const month = Number(m[2]);
  if (month < 1 || month > 12) return iso;
  return `${Number(m[3])} ${MONTHS[month - 1]} ${m[1]}`;
}

/** A moment ("2026-11-03T14:30" in the person's time, or an ISO timestamp) as "Tue 3 Nov 2026, 14:30" on this phone. */
export function whenLabel(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** "2026-11-03T14:30" for a Date, in the phone's own time (what the API's datetime field takes). */
export function toLocalInput(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** "2026-11-03" for a Date. */
export function toDayInput(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Reads "2026-11-03T14:30" or "2026-11-03" back into a Date (local time); today when empty or unreadable. */
export function fromInput(text: string): Date {
  if (!text) return new Date();
  const d = /^\d{4}-\d{2}-\d{2}$/.test(text) ? new Date(`${text}T12:00:00`) : new Date(text);
  return Number.isNaN(d.getTime()) ? new Date() : d;
}

/** Money as plain text in the offer's own currency. Never converted. A code the phone does not know is shown as written. */
export function formatMoney(amount: string, currency: string): string {
  const value = Number(amount);
  if (!Number.isFinite(value)) return `${amount} ${currency}`;
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
  } catch {
    return `${Math.round(value).toLocaleString()} ${currency}`;
  }
}

export const MAX_COMPARE = 4;
export const MIN_COMPARE = 2;

export function toggleOffer(selected: number[], id: number): number[] {
  if (selected.includes(id)) return selected.filter((x) => x !== id);
  return selected.length >= MAX_COMPARE ? selected : [...selected, id];
}
export const canCompare = (selected: number[]) => selected.length >= MIN_COMPARE && selected.length <= MAX_COMPARE;
export function compareHint(count: number): string {
  if (count === 0) return "Tick two to four offers to read the differences in words.";
  if (count === 1) return "Tick one more offer to compare.";
  if (count >= MAX_COMPARE) return `That is the most we can compare at once (${MAX_COMPARE}).`;
  return `${count} offers ticked.`;
}

export function toggleId(list: number[], id: number): number[] {
  return list.includes(id) ? list.filter((x) => x !== id) : [...list, id];
}

/** "Subject: ...\n\n..." as one block to copy. */
export function messageText(m: { subject: string; body: string }): string {
  return `Subject: ${m.subject}\n\n${m.body}`;
}

// ---- stats sentences ---------------------------------------------------------------------------------------------------------------

export function count(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

export function dayShort(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]}`;
}

export function weekEnd(start: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(start);
  if (!m) return start;
  return new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + 6)).toISOString().slice(0, 10);
}
export const weekLabel = (start: string) => `${dayShort(start)} to ${dayShort(weekEnd(start))}`;

export function weeklyHasData(weekly: Stats["weekly"]): boolean {
  return weekly.some((w) => w.found + w.checked + w.applied > 0);
}

export type Tile = { key: string; label: string; value: number; to?: string; note?: string };
export function weekTiles(week: Stats["week"]): Tile[] {
  return [
    { key: "found", label: "New jobs found", value: week.found },
    { key: "checked", label: "Fits checked", value: week.checked },
    { key: "applied", label: "Applications sent", value: week.applied },
    { key: "interviews", label: "Interviews coming up", value: week.interviews_soon, to: week.interviews_soon > 0 ? "/interviews" : undefined },
    { key: "followups", label: "Follow-ups due", value: week.followups_due, to: week.followups_due > 0 ? "/" : undefined, note: week.followups_due > 0 ? "See them on your dashboard" : undefined },
    { key: "closing", label: "Closing soon", value: week.closing_soon },
    { key: "closed", label: "Postings that closed", value: week.went_cold },
  ];
}

export function averageText(average: number | null, averageApplied: number | null): { all: string; applied: string } {
  return {
    all: average === null ? "Average fit: nothing checked yet" : `Average fit across your jobs: ${average}%`,
    applied: averageApplied === null ? "Average fit of the jobs you applied to: no checked applications yet" : `Average fit of the jobs you applied to: ${averageApplied}%`,
  };
}

export function strongShareText(match: Pick<Stats["match"], "strong_share_applied" | "top_band">): string {
  if (match.strong_share_applied === null) return "Once you have applied to a job whose fit was checked, we show how many of your applications were to a strong match.";
  const band = match.top_band ? ` (${match.top_band})` : "";
  return `${match.strong_share_applied}% of your applications were to a strong match${band}.`;
}

export const anyChecked = (match: Pick<Stats["match"], "bands">) => match.bands.some((b) => b.count > 0);

export function waitingText(waiting: Stats["waiting"]): string {
  if (waiting.count === 0) return "Nothing is waiting for a reply right now.";
  const typical = waiting.median_days === null ? "" : `, typically for ${count(waiting.median_days, "day")}`;
  return `${count(waiting.count, "application is", "applications are")} waiting for a reply${typical}.`;
}

const WORK_LABELS: Record<string, string> = { remote: "Remote", hybrid: "Hybrid", onsite: "On-site", unknown: "Not stated" };
export const workLabel = (kind: string) => WORK_LABELS[kind] ?? kind;

export function marketText(market: NonNullable<Stats["market"]>): string {
  return `${count(market.this_week, "new posting")} matched ${market.roles.join(", ")} this week, and ${market.last_week} last week.`;
}

export function prepText(prep: NonNullable<Stats["prep"]>): { plans: string; lessons: string; streak: string } {
  return {
    plans: count(prep.active_plans, "active prep plan"),
    lessons: `${prep.lessons_done} of ${count(prep.lessons_total, "lesson")} done`,
    streak: prep.streak > 0 ? `${count(prep.streak, "day")} in a row` : "No streak yet. A short lesson today starts one.",
  };
}

export function calibrationLine(b: { label: string; applied: number; replies: number; reply_rate: number | null }): string {
  if (b.applied === 0) return `${b.label}: you did not apply to any.`;
  const reply = b.replies === 1 ? "1 got a reply" : b.replies === 0 ? "none got a reply" : `${b.replies} got a reply`;
  return `${b.label}: ${b.applied} applied, ${reply}${b.reply_rate === null ? "" : ` (${b.reply_rate}%)`}.`;
}

export function calibrationWaiting(c: { scored: number; needed: number }): string {
  const left = Math.max(0, c.needed - c.scored);
  return `This shows once you have applied to ${c.needed} jobs that have a match percent. You have ${c.scored} so far, ${left} to go. Press Check my fit on a job before you apply, and it counts.`;
}

/** "Mar 2026" for "2026-03". */
export function monthLabel(month: string): string {
  const [year, m] = month.split("-").map(Number);
  return `${MONTHS[(m || 1) - 1]} ${year}`;
}

// ---- funnel, heatmap, goals, calendar ------------------------------------------------------------------------------------------

export const PERIOD_LABELS: Record<Period, string> = { "30": "30 days", "90": "90 days", all: "All time" };

export function stageShare(n: number, previous: number | null): string {
  if (previous === null || previous === 0) return String(n);
  return `${n} of ${previous} (${Math.round((100 * n) / previous)}%)`;
}
export const funnelEmpty = (f: Funnel) => f.stages[0].count === 0;
export function funnelSentence(f: Funnel, period: Period): string {
  const [sent, replied, interviews, offers] = f.stages.map((s) => s.count);
  const when = period === "all" ? "so far" : `in the last ${period} days`;
  return `Of ${sent} ${sent === 1 ? "application" : "applications"} sent ${when}, ${replied} heard back, ${interviews} reached an interview and ${offers} got an offer.`;
}

export type HeatCell = { date: string; applied: number; interviews: number; total: number; level: 0 | 1 | 2 | 3 | 4 };
const iso = (d: Date) => d.toISOString().slice(0, 10);
const utc = (s: string) => {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
};
export function heatLevel(total: number, max: number): 0 | 1 | 2 | 3 | 4 {
  if (total <= 0 || max <= 0) return 0;
  return Math.min(4, Math.max(1, Math.ceil((4 * total) / max))) as 1 | 2 | 3 | 4;
}
/** Weeks (columns, Monday first) of day cells; days outside the range are null. */
export function heatWeeks(activity: Pick<Activity, "start" | "end" | "days">): (HeatCell | null)[][] {
  const start = utc(activity.start);
  const end = utc(activity.end);
  const max = Math.max(0, ...Object.values(activity.days).map((d) => d.applied + d.interviews));
  let cursor = new Date(start);
  cursor.setUTCDate(cursor.getUTCDate() - ((cursor.getUTCDay() + 6) % 7));
  const weeks: (HeatCell | null)[][] = [];
  while (cursor <= end) {
    const week: (HeatCell | null)[] = [];
    for (let i = 0; i < 7; i++) {
      if (cursor < start || cursor > end) week.push(null);
      else {
        const key = iso(cursor);
        const d = activity.days[key] ?? { applied: 0, interviews: 0 };
        const total = d.applied + d.interviews;
        week.push({ date: key, applied: d.applied, interviews: d.interviews, total, level: heatLevel(total, max) });
      }
      cursor = new Date(cursor.getTime() + 86400000);
    }
    weeks.push(week);
  }
  return weeks;
}
export function heatText(c: Pick<HeatCell, "date" | "applied" | "interviews">): string {
  return `${dayLabel(c.date)}: ${c.applied} ${c.applied === 1 ? "application" : "applications"}, ${c.interviews} ${c.interviews === 1 ? "interview" : "interviews"}`;
}

export const goalPercent = (done: number, target: number) => (target <= 0 ? 0 : Math.min(100, Math.round((100 * done) / target)));
export function goalLine(done: number, target: number, unit: string): string {
  if (target <= 0) return "";
  return done >= target ? `${unit}: ${done} of ${target}. Goal reached.` : `${unit}: ${done} of ${target}.`;
}
export function streakLine(g: Pick<Goals, "current_streak" | "best_streak">): string {
  const day = (n: number) => `${n} ${n === 1 ? "day" : "days"}`;
  if (g.best_streak === 0) return "No streak yet. Send an application and it starts.";
  return `Current streak: ${day(g.current_streak)} in a row. Best: ${day(g.best_streak)}.`;
}

export const KIND_WORDS: Record<CalendarItem["kind"], string> = { interview: "Interview", deadline: "Apply by", followup: "Follow up", offer: "Reply to offer" };
export function calendarTo(i: CalendarItem): string {
  return i.kind === "interview" ? "/interviews" : i.kind === "offer" ? "/offers" : `/jobs/${i.job_id}/apply`;
}
export function shiftMonth(month: string, by: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + by, 1));
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}`;
}
export function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
}
/** Rows of 7 cells (Monday first) for the month; blank cells are null. */
export function monthGrid(cal: Pick<CalendarMonth, "first" | "last" | "weekday_of_first">): (string | null)[][] {
  const lastDay = Number(cal.last.slice(8, 10));
  const cells: (string | null)[] = Array(cal.weekday_of_first).fill(null);
  for (let d = 1; d <= lastDay; d++) cells.push(`${cal.first.slice(0, 8)}${pad(d)}`);
  while (cells.length % 7) cells.push(null);
  const rows: (string | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) rows.push(cells.slice(i, i + 7));
  return rows;
}
