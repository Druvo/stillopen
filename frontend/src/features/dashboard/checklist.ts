import type { Dashboard } from "@/lib/types";

export type ChecklistStep = { key: string; label: string; done: boolean; to: string; cta: string };

/** The "Getting started" steps, worked out from answers the dashboard already holds (no extra request). */
export function checklistSteps(data: Pick<Dashboard, "search_summary" | "jobs" | "scan" | "checked_at">): ChecklistStep[] {
  const roles = data.search_summary?.roles ?? [];
  return [
    { key: "roles", label: "Tell us which roles you want", done: roles.length > 0, to: "/profile", cta: "Add roles" },
    { key: "cv", label: "Add your CV", done: data.search_summary?.has_cv === true, to: "/cv/new", cta: "Add a CV" },
    { key: "search", label: "Run your first job search", done: Boolean(data.scan?.finished_at), to: "/", cta: "Search for jobs" },
    { key: "job", label: "Track your first job", done: data.jobs.length > 0, to: "/jobs/add", cta: "Add a job" },
    { key: "fit", label: "Press Check my fit on a job", done: data.jobs.some((j) => j.evaluated || j.percent !== null), to: "/", cta: "See your jobs" },
  ];
}

/** Shown to someone with fewer than three steps done, until they close it. */
export function showChecklist(steps: ChecklistStep[], dismissed: boolean): boolean {
  return !dismissed && steps.filter((s) => s.done).length < 3;
}
