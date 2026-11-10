// "Your numbers" (stats, funnel, activity, goals, calendar) and the saved preferences the goals live in (worker B).
// Shapes copied from the website's frontend/src/features/stats/api.ts.
import { api } from "./client";

const B = "/api/v1";

export type Period = "30" | "90" | "all";
export type Funnel = { since: string | null; stages: { key: string; label: string; count: number }[] };
export type Activity = { start: string; end: string; days: Record<string, { applied: number; interviews: number }>; total_applied: number; total_interviews: number };
export type Goals = {
  daily_target: number; weekly_target: number; today: number; week: number; current_streak: number; best_streak: number; explain: string;
  month: { label: string; applied: number; interviews: number; text: string };
};
export type CalibrationBand = { label: string; color: string; min_percent: number; applied: number; replies: number; reply_rate: number | null };
export type Calibration = { enough: boolean; scored: number; needed: number; caveat: string; bands: CalibrationBand[] };

export type Stats = {
  as_of: string;
  has_jobs: boolean;
  summary_text?: string;
  week: { found: number; checked: number; applied: number; interviews_soon: number; followups_due: number; closing_soon: number; went_cold: number };
  weekly: { start: string; found: number; checked: number; applied: number }[];
  match: {
    bands: { label: string; color: string; count: number }[];
    not_checked: number; average: number | null; average_applied: number | null; top_band: string; strong_share_applied: number | null;
  };
  applied: { count: number; reply_rate: number | null };
  calibration?: Calibration;
  sources: { label: string; found: number; applied: number; interviews: number }[];
  work: { kind: "remote" | "hybrid" | "onsite" | "unknown"; count: number }[];
  countries: { name: string; count: number }[];
  waiting: { count: number; median_days: number | null; longest: { id: number; company: string; role: string; days: number }[]; after_days: number };
  skills: { gaps: { term: string; jobs: number }[]; strengths: { term: string; jobs: number }[] };
  prep: null | { active_plans: number; lessons_done: number; lessons_total: number; streak: number };
  market: null | { this_week: number; last_week: number; roles: string[] };
  funnel?: Record<Period, Funnel>;
  activity?: Activity;
  goals?: Goals | null;
};

export type CalendarItem = { kind: "interview" | "deadline" | "followup" | "offer"; date: string; when: string; label: string; company: string; role: string; job_id: number };
export type CalendarMonth = {
  month: string; label: string; first: string; last: string; weekday_of_first: number; today: string;
  days: Record<string, CalendarItem[]>; week_ahead: CalendarItem[];
};

/** The goal/period preferences this app reads and writes (PUT takes only what changed, the rest of the person's layout choices stay as they are). */
export type Prefs = { goal_daily?: number; goal_weekly?: number; insights_period?: Period; [k: string]: unknown };

export const statsApi = {
  get: () => api.get<Stats>(`${B}/stats`),
  calendar: (month: string) => api.get<CalendarMonth>(`${B}/stats/calendar?month=${encodeURIComponent(month)}`),
  preferences: () => api.get<Prefs>(`${B}/preferences`),
  savePreferences: (patch: Partial<Pick<Prefs, "goal_daily" | "goal_weekly" | "insights_period">>) => api.put<Prefs>(`${B}/preferences`, patch),
};
