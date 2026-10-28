import type { Job, StatusInfo } from "@/lib/types";

/** The status people reach for first: "this is not for me". Found by its name, else the first ending that did not count as an application. */
export function notForMeStatus(statuses: StatusInfo[]): StatusInfo | undefined {
  return (
    statuses.find((s) => s.name === "Not for me") ??
    statuses.find((s) => s.name === "Discarded") ??
    statuses.find((s) => !s.counts_as_applied && s.name !== "Skipped" && /closed|skip|discard/i.test(s.bucket_key))
  );
}

/** What a screen calls a status. */
export function statusLabel(s: Pick<StatusInfo, "name" | "label"> | undefined): string {
  return s ? s.label || s.name : "its new status";
}

// ---- choosing several jobs ---------------------------------------------------------------------------------------------

export function toggleId(selected: ReadonlySet<number>, id: number): Set<number> {
  const next = new Set(selected);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

/** Every job of the list that is on the screen (the chosen stage tab with the filters applied), not only the 50 drawn so far. */
export function selectAllIn(jobs: Pick<Job, "id">[]): Set<number> {
  return new Set(jobs.map((j) => j.id));
}

/** The choice with the jobs that are no longer on the list (a filter changed, a job was removed) dropped. */
export function pruneSelection(selected: ReadonlySet<number>, jobs: Pick<Job, "id">[]): Set<number> {
  const present = new Set(jobs.map((j) => j.id));
  return new Set([...selected].filter((id) => present.has(id)));
}

export function allSelected(selected: ReadonlySet<number>, jobs: Pick<Job, "id">[]): boolean {
  return jobs.length > 0 && jobs.every((j) => selected.has(j.id));
}

const jobs = (n: number) => `${n} ${n === 1 ? "job" : "jobs"}`;

export function selectedText(count: number): string {
  return count === 0 ? "Choose the jobs you want to act on." : `${count} selected`;
}

export function movedText(count: number, label: string, role?: string): string {
  return count === 1 && role ? `Moved ${role} to ${label}.` : `Moved ${jobs(count)} to ${label}.`;
}

/** The line on the Undo bar (worded differently from the page's own "Moved ..." message, so a screen reader does not hear the same thing twice). */
export function undoText(count: number, label: string, role?: string): string {
  return count === 1 && role ? `${role} is now ${label}.` : `${jobs(count)} ${count === 1 ? "is" : "are"} now ${label}.`;
}

export function removedText(count: number, role?: string): string {
  return count === 1 && role ? `Removed ${role}.` : `Removed ${jobs(count)}.`;
}

/** The "weak matches" line under the filters: how many the switch is leaving out, with a way back. */
export function weakLine(hidden: number): string {
  return hidden === 0 ? "" : `${hidden} weak ${hidden === 1 ? "match is" : "matches are"} hidden (under 40%).`;
}

export function archivedText(count: number, role?: string): string {
  return count === 1 && role ? `Archived ${role}. You can bring it back from Archived, below your list.` : `Archived ${jobs(count)}. You can bring them back from Archived, below your list.`;
}
