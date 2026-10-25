/** Pure helpers for "Where we find jobs for you": the sentences the card and the dashboard line show. No React here. */

export type CoverageSearch = { name: string; connector: string; connector_label: string; ready: boolean; reason: "" | "needs_key" | "needs_roles" };
export type CoverageArea = {
  id: number;
  place: string;
  label: string;
  known: boolean;
  postings: number;
  boards: number;
  searches: CoverageSearch[];
  searches_ready: number;
  searches_waiting: number;
  level: "none" | "thin" | "ok" | "unknown";
  tip: string;
};
export type Coverage = { days: number; areas: CoverageArea[]; has_areas: boolean; empty_areas: number; keys: { jooble: boolean; adzuna: boolean } };

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** "12 jobs listed in the last 30 days, from 3 job sources." */
export function countText(area: CoverageArea, days: number): string {
  if (!area.known) return "We could not tell which country this is, so we cannot count jobs there.";
  if (area.postings === 0) return `No jobs listed in the last ${days} days.`;
  return `${plural(area.postings, "job")} listed in the last ${days} days, from ${plural(area.boards, "job source")}.`;
}

/** What the country searches that can see this place are doing, in words ("Jooble: needs a free key from the site owner"). */
export function searchText(s: CoverageSearch): string {
  if (s.reason === "needs_key") return `${s.connector_label}: switched off until the site owner adds a free key`;
  if (s.reason === "needs_roles") return `${s.connector_label}: add the roles you want in your profile to use it`;
  return `${s.connector_label}: searches here with your next job search`;
}

export function levelWord(area: CoverageArea): string {
  return { none: "No jobs yet", thin: "A few jobs", ok: "Well covered", unknown: "Not checked" }[area.level];
}

/** The places that have nothing listed at all (an unrecognised place is never called empty). */
export function emptyAreas(coverage: Coverage | undefined): CoverageArea[] {
  return (coverage?.areas ?? []).filter((a) => a.known && a.level === "none");
}

/** One line for the dashboard's "Your search" card, or null when every place has something. */
export function emptyLine(coverage: Coverage | undefined): string | null {
  const empty = emptyAreas(coverage);
  if (empty.length === 0) return null;
  if (empty.length === 1) return `Nothing lists jobs in ${empty[0].label} yet.`;
  if (empty.length === 2) return `Nothing lists jobs in ${empty[0].label} or ${empty[1].label} yet.`;
  return `Nothing lists jobs in ${empty.length} of your places yet.`;
}
