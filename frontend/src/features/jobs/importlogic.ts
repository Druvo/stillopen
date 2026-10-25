import type { EmailDone, EmailPreview, EmailRow, ImportFile } from "./api";

const n = (count: number, one: string, many = `${one}s`) => `${count} ${count === 1 ? one : many}`;

/** The row numbers (as the server numbered them) that are ticked, in order. */
export function ticked(rows: EmailRow[], off: Set<number>): number[] {
  return rows.filter((r) => !off.has(r.index)).map((r) => r.index);
}

/** Rows start ticked unless the person already tracks the job. */
export function initiallyOff(preview: EmailPreview): Set<number> {
  return new Set(preview.rows.filter((r) => !r.importable).map((r) => r.index));
}

export function previewHeadline(preview: EmailPreview): string {
  if (preview.found === 0) return "We did not find any jobs in that.";
  const dupes = preview.rows.filter((r) => r.duplicate).length;
  const parts = [`${n(preview.found, "job")} found`];
  if (dupes) parts.push(`${n(dupes, "job")} you already track`);
  return `${parts.join(", ")}.`;
}

export function doneMessage(done: EmailDone): string {
  const parts = [`Added ${n(done.added, "job")}`];
  if (done.skipped_count) parts.push(`${n(done.skipped_count, "job")} skipped because you already track ${done.skipped_count === 1 ? "it" : "them"}`);
  return `${parts.join(", ")}.${done.stopped ? ` ${done.stopped}` : ""}`;
}

/** What to tell the person about a row, in plain words (the server's own wording for problems). */
export function rowNotes(row: EmailRow): string[] {
  const notes = [...row.problems];
  if (row.duplicate) notes.unshift(`You already track ${row.duplicate.role} at ${row.duplicate.company} (${row.duplicate.status}).`);
  return notes;
}

export function fileCountsLine(f: ImportFile): string {
  const parts = [`${f.found} found`, `${f.new} new`];
  if (f.duplicates) parts.push(`${f.duplicates} already tracked`);
  if (f.unreadable) parts.push(`${n(f.unreadable, "row")} could not be read`);
  return `${f.label}: ${parts.join(", ")}`;
}

/** True for a file the LinkedIn import accepts (the whole export zip, or one of its CSVs). */
export function isLinkedinFile(name: string): boolean {
  return /\.(zip|csv)$/i.test(name);
}

export const LINKEDIN_BLOCKED_NOTE =
  "LinkedIn does not let other apps read its pages, so we have kept the link and need the text from you: open the job on LinkedIn, select the description, copy and paste it below.";

/** The note shown when the link was kept but not read (the server sends its own wording; this is the fallback). */
export function blockedNote(host: string | undefined, message: string | undefined): string {
  if (!host) return "";
  return message || LINKEDIN_BLOCKED_NOTE;
}

/** The address of a careers page as a host name for the list ("careers.example.com"). */
export function hostOfPage(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

/** The plain line under a careers-page source: the host, and how it last answered. */
export function careerPageLine(token: string): string {
  return `Careers page on ${hostOfPage(token)}`;
}
