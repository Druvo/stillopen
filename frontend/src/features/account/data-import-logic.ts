import type { DataImportReport } from "./api";

const n = (count: number, one: string, many = `${one}s`) => `${count} ${count === 1 ? one : many}`;

/** The plain-words lines of an import preview, one per kind of thing, only what has something to say. */
export function importLines(r: DataImportReport): string[] {
  const lines: string[] = [];
  if (r.profile.filled.length) lines.push(`Profile answers to fill in: ${r.profile.filled.join(", ")}.`);
  if (r.profile.kept.length) lines.push(`Profile answers you already have, kept as they are: ${r.profile.kept.join(", ")}.`);
  if (r.cvs.add) lines.push(`${n(r.cvs.add, "CV version")} to add to your history (your current CV stays the current one).`);
  if (r.cvs.have) lines.push(`${n(r.cvs.have, "CV version")} you already have.`);
  if (r.covers.add) lines.push(`${n(r.covers.add, "cover letter")} to add (they start unapproved and are fact-checked again).`);
  if (r.covers.no_job) lines.push(`${n(r.covers.no_job, "cover letter")} skipped because no single job here has the same company and role.`);
  if (r.notes.add) lines.push(`${n(r.notes.add, "job note")} to fill in on jobs with no note yet.`);
  if (r.notes.kept) lines.push(`${n(r.notes.kept, "job note")} different from yours, so yours are kept.`);
  for (const stop of [r.cvs.stopped, r.covers.stopped]) if (stop) lines.push(stop);
  if (r.left_out) lines.push(`${n(r.left_out, "entry", "entries")} past the size limit were left out.`);
  if (lines.length === 0) lines.push("This file has nothing that is missing from your account.");
  return lines;
}
