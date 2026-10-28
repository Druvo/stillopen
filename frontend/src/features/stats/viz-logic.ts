import type { Activity, CalendarItem, CalendarMonth, Funnel, Goals } from "./api";

// ---- funnel -----------------------------------------------------------------------------------------------------------------

export const PERIOD_LABELS = { "30": "30 days", "90": "90 days", all: "All time" } as const;

/** "3 of 10 (30%)", or just the count for the first stage. A stage after an empty one says nothing about a share. */
export function stageShare(count: number, previous: number | null): string {
  if (previous === null || previous === 0) return String(count);
  return `${count} of ${previous} (${Math.round((100 * count) / previous)}%)`;
}

export function funnelEmpty(f: Funnel): boolean {
  return f.stages[0].count === 0;
}

/** The plain sentence for a period, for example "Of 12 applications sent in the last 30 days, 5 heard back, 2 reached an interview and 1 got an offer." */
export function funnelSentence(f: Funnel, period: "30" | "90" | "all"): string {
  const [sent, replied, interviews, offers] = f.stages.map((s) => s.count);
  const when = period === "all" ? "so far" : `in the last ${period} days`;
  return `Of ${sent} ${sent === 1 ? "application" : "applications"} sent ${when}, ${replied} heard back, ${interviews} reached an interview and ${offers} got an offer.`;
}

// ---- activity heatmap -----------------------------------------------------------------------------------------------------

export type HeatCell = { date: string; applied: number; interviews: number; total: number; level: 0 | 1 | 2 | 3 | 4 };

const iso = (d: Date) => d.toISOString().slice(0, 10);
const utc = (s: string) => {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
};

/** Colour step 0 to 4 for a day's total, scaled to the busiest day so a quiet year still shows its shape. */
export function heatLevel(total: number, max: number): 0 | 1 | 2 | 3 | 4 {
  if (total <= 0 || max <= 0) return 0;
  return Math.min(4, Math.max(1, Math.ceil((4 * total) / max))) as 1 | 2 | 3 | 4;
}

/** Weeks (columns, Monday first) of day cells from the week containing `start` to `end`. Days outside the range are null. */
export function heatWeeks(activity: Pick<Activity, "start" | "end" | "days">): (HeatCell | null)[][] {
  const start = utc(activity.start);
  const end = utc(activity.end);
  const max = Math.max(0, ...Object.values(activity.days).map((d) => d.applied + d.interviews));
  let cursor = new Date(start);
  cursor.setUTCDate(cursor.getUTCDate() - ((cursor.getUTCDay() + 6) % 7)); // back to the Monday
  const weeks: (HeatCell | null)[][] = [];
  while (cursor <= end) {
    const week: (HeatCell | null)[] = [];
    for (let i = 0; i < 7; i++) {
      if (cursor < start || cursor > end) {
        week.push(null);
      } else {
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
  return `${c.date}: ${c.applied} ${c.applied === 1 ? "application" : "applications"}, ${c.interviews} ${c.interviews === 1 ? "interview" : "interviews"}`;
}

// ---- goals ----------------------------------------------------------------------------------------------------------------------

/** 0 to 100, for the ring. No target means no ring. */
export function goalPercent(done: number, target: number): number {
  if (target <= 0) return 0;
  return Math.min(100, Math.round((100 * done) / target));
}

export function goalLine(done: number, target: number, unit: string): string {
  if (target <= 0) return "";
  if (done >= target) return `${unit}: ${done} of ${target}. Goal reached.`;
  return `${unit}: ${done} of ${target}.`;
}

export function streakLine(g: Pick<Goals, "current_streak" | "best_streak">): string {
  const day = (n: number) => `${n} ${n === 1 ? "day" : "days"}`;
  if (g.best_streak === 0) return "No streak yet. Send an application and it starts.";
  return `Current streak: ${day(g.current_streak)} in a row. Best: ${day(g.best_streak)}.`;
}

// ---- calendar ------------------------------------------------------------------------------------------------------------------

export const KIND_WORDS: Record<CalendarItem["kind"], string> = { interview: "Interview", deadline: "Apply by", followup: "Follow up", offer: "Reply to offer" };

export function calendarTo(i: CalendarItem): string {
  return i.kind === "interview" ? "/interviews" : i.kind === "offer" ? "/offers" : `/jobs/${i.job_id}/apply`;
}

/** A "YYYY-MM" month moved by `by` months. */
export function shiftMonth(month: string, by: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + by, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

/** Rows of 7 cells (Monday first) for the month; blank cells are null. */
export function monthGrid(cal: Pick<CalendarMonth, "first" | "last" | "weekday_of_first">): (string | null)[][] {
  const lastDay = Number(cal.last.slice(8, 10));
  const cells: (string | null)[] = Array(cal.weekday_of_first).fill(null);
  for (let d = 1; d <= lastDay; d++) cells.push(`${cal.first.slice(0, 8)}${String(d).padStart(2, "0")}`);
  while (cells.length % 7) cells.push(null);
  const rows: (string | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) rows.push(cells.slice(i, i + 7));
  return rows;
}

/** Where the arrow keys move on the grid, kept inside the month: the new date, or the same one at the edge. */
export function moveDay(date: string, key: string, first: string, last: string): string {
  const step: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
  if (!(key in step)) return date;
  const out = iso(new Date(utc(date).getTime() + step[key] * 86400000));
  return out < first || out > last ? date : out;
}
