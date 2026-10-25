import { ApiError } from "@/lib/api";
import { shortDate, timeAgo } from "@/features/dashboard/logic";
import type { Duplicate, ImportReport, ReplySuggestion } from "./api";

/** The spreadsheet download (a plain file from Django, not part of the JSON API). */
export const CSV_EXPORT_URL = "/jobs/export.csv";

// ---- the same job twice ------------------------------------------------------------------------------------------------

/** The job the server says the person already tracks, when a 409 answer carries one. */
export function duplicateOf(error: unknown): Duplicate | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const d = error.data.duplicate as Partial<Duplicate> | undefined;
  return d && typeof d.id === "number" ? { id: d.id, company: String(d.company ?? ""), role: String(d.role ?? ""), status: String(d.status ?? "") } : null;
}

export function duplicateMessage(d: Pick<Duplicate, "company" | "role" | "status">): string {
  return `You already track ${d.role} at ${d.company}${d.status ? ` (${d.status})` : ""}.`;
}

// ---- statuses and the reply reader -------------------------------------------------------------------------------------

/** What a screen calls a status: the friendly label when the server sent one, else its name. */
export function statusWord(s: { name: string; label?: string }): string {
  return s.label || s.name;
}

export function suggestionButton(s: ReplySuggestion["status"]): string {
  return `Set status to ${statusWord(s)}`;
}

export function confidenceText(c: ReplySuggestion["confidence"], mixed = false): string {
  if (mixed) return "This email seems to say two things at once, so please read it yourself before you choose.";
  if (c === "clear") return "This looks clear.";
  if (c === "probably") return "This probably means:";
  return "We are not sure, so please check it yourself.";
}

/** The sentence a "move this job?" prompt shows after an interview or an offer was saved. */
export function moveText(label: string): string {
  return `Move this job to ${label}?`;
}

// ---- the spreadsheet import --------------------------------------------------------------------------------------------

const n = (count: number, one: string, many = `${one}s`) => `${count} ${count === 1 ? one : many}`;

/** One plain sentence about what the file holds (before) or what was done (after). */
export function importHeadline(r: Pick<ImportReport, "preview" | "will_add" | "added" | "skipped_count" | "problem_count">): string {
  const parts = r.preview ? [`${n(r.will_add, "job")} will be added`] : [`Added ${n(r.added ?? r.will_add, "job")}`];
  if (r.skipped_count) parts.push(`${n(r.skipped_count, "row")} skipped because you already track ${r.skipped_count === 1 ? "it" : "them"}`);
  if (r.problem_count) parts.push(`${n(r.problem_count, "row")} could not be read`);
  return `${parts.join(", ")}.`;
}

export function removedMessage(count: number, name: string): string {
  return count === 1 ? `Removed ${name}.` : `Removed ${count} jobs.`;
}

// ---- history -----------------------------------------------------------------------------------------------------------

export function historyDay(date: string): string {
  return shortDate(date, true);
}

// ---- how a job board answered ------------------------------------------------------------------------------------------

export type SourceHealth = { state: "ok" | "error" | "unknown"; checked_at: string | null; last_ok_at: string | null; error: string; since: string | null };

/** "Worked 2 hours ago", "Not answering since 21 Oct: HTTP 500", or "Not searched yet". */
export function sourceHealthText(h: SourceHealth, now: Date = new Date()): string {
  if (h.state === "unknown") return "Not searched yet.";
  if (h.state === "ok") return h.checked_at ? `Worked ${timeAgo(h.checked_at, now)} ago.` : "Worked.";
  const since = h.since ? shortDate(h.since.slice(0, 10)) : "";
  const why = h.error ? `: ${h.error}` : "";
  return `Not answering${since ? ` since ${since}` : ""}${why}`;
}

/** The dashboard line, or "" when every source answered. */
export function troubleLine(t: { total: number; trouble: number } | null | undefined): string {
  if (!t || t.trouble <= 0) return "";
  return `${t.trouble} of ${t.total} ${t.total === 1 ? "source" : "sources"} had trouble in the last search.`;
}
