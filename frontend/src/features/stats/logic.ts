import type { Stats } from "./api";

/** "1 posting", "3 postings". */
export function count(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** The largest of some numbers, never below 1 (so a bar can always be scaled). */
export function maxOf(values: number[]): number {
  return Math.max(1, ...values);
}

/** How wide a bar is, 0 to 100. A real but tiny value still shows a sliver, so "1" never looks like "0". */
export function barPercent(value: number, max: number): number {
  if (value <= 0 || max <= 0) return 0;
  return Math.min(100, Math.max(4, Math.round((100 * value) / max)));
}

/** "27 Oct" for a day like "2026-10-27". */
export function dayShort(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${Number(m[3])} ${months[Number(m[2]) - 1]}`;
}

/** The last day of a 7-day window that starts on `start`. */
export function weekEnd(start: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(start);
  if (!m) return start;
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + 6));
  return d.toISOString().slice(0, 10);
}

export function weekLabel(start: string): string {
  return `${dayShort(start)} to ${dayShort(weekEnd(start))}`;
}

/** Whether any of the eight weeks has anything in it. */
export function weeklyHasData(weekly: Stats["weekly"]): boolean {
  return weekly.some((w) => w.found + w.checked + w.applied > 0);
}

export type Tile = { key: string; label: string; value: number; to?: string; note?: string };

/** The seven numbers of "This week", in plain words. Follow-ups link to the dashboard, where they can be done. */
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

/** "40% of your applications were to a strong match (Strong)", or what to do when it cannot be said yet. */
export function strongShareText(match: Pick<Stats["match"], "strong_share_applied" | "top_band">): string {
  if (match.strong_share_applied === null) return "Once you have applied to a job whose fit was checked, we show how many of your applications were to a strong match.";
  const band = match.top_band ? ` (${match.top_band})` : "";
  return `${match.strong_share_applied}% of your applications were to a strong match${band}.`;
}

/** Whether any job has been checked (a band has jobs). */
export function anyChecked(match: Pick<Stats["match"], "bands">): boolean {
  return match.bands.some((b) => b.count > 0);
}

export function waitingText(waiting: Stats["waiting"]): string {
  if (waiting.count === 0) return "Nothing is waiting for a reply right now.";
  const typical = waiting.median_days === null ? "" : `, typically for ${count(waiting.median_days, "day")}`;
  return `${count(waiting.count, "application is", "applications are")} waiting for a reply${typical}.`;
}

export const WORK_LABELS: Record<string, string> = { remote: "Remote", hybrid: "Hybrid", onsite: "On-site", unknown: "Not stated" };
export const workLabel = (kind: string) => WORK_LABELS[kind] ?? kind;

export function marketText(market: NonNullable<Stats["market"]>): string {
  const roles = market.roles.join(", ");
  return `${count(market.this_week, "new posting")} matched ${roles} this week, and ${market.last_week} last week.`;
}

export function prepText(prep: NonNullable<Stats["prep"]>): { plans: string; lessons: string; streak: string } {
  return {
    plans: `${count(prep.active_plans, "active prep plan")}`,
    lessons: `${prep.lessons_done} of ${count(prep.lessons_total, "lesson")} done`,
    streak: prep.streak > 0 ? `${count(prep.streak, "day")} in a row` : "No streak yet. A short lesson today starts one.",
  };
}

/** What the "This week" card on the dashboard shows: found, checked, applied and how many are waiting. */
export function cardTiles(stats: Pick<Stats, "week" | "waiting">): { label: string; value: number }[] {
  return [
    { label: "New jobs", value: stats.week.found },
    { label: "Fits checked", value: stats.week.checked },
    { label: "Applied", value: stats.week.applied },
    { label: "Waiting for a reply", value: stats.waiting.count },
  ];
}
