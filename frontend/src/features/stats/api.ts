import { useQuery } from "@tanstack/react-query";
import { request } from "@/lib/api";

/** `GET /stats`: plain counts about one person's own search. Any percentage or average is null when there is nothing to base it on. */
export type Stats = {
  as_of: string;
  has_jobs: boolean;
  week: { found: number; checked: number; applied: number; interviews_soon: number; followups_due: number; closing_soon: number; went_cold: number };
  weekly: { start: string; found: number; checked: number; applied: number }[];
  match: {
    bands: { label: string; color: string; count: number }[];
    not_checked: number;
    average: number | null;
    average_applied: number | null;
    top_band: string;
    strong_share_applied: number | null;
  };
  applied: { count: number; reply_rate: number | null };
  sources: { label: string; found: number; applied: number; interviews: number }[];
  work: { kind: "remote" | "hybrid" | "onsite" | "unknown"; count: number }[];
  countries: { name: string; count: number }[];
  waiting: { count: number; median_days: number | null; longest: { id: number; company: string; role: string; days: number }[]; after_days: number };
  skills: { gaps: { term: string; jobs: number }[]; strengths: { term: string; jobs: number }[] };
  prep: null | { active_plans: number; lessons_done: number; lessons_total: number; streak: number };
  market: null | { this_week: number; last_week: number; roles: string[] };
};

export const STATS_KEY = ["stats"] as const;

export const statsApi = { get: () => request<Stats>("GET", "/stats") };

/** The person's numbers. Fetched alongside the dashboard (not after it), and shown from the saved copy while a fresh one loads. */
export function useStats() {
  return useQuery({ queryKey: STATS_KEY, queryFn: statsApi.get });
}
