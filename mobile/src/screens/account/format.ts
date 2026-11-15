// Plain date and number wording shared by the account screens. Times show on the phone's own clock.
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const pad = (n: number) => String(n).padStart(2, "0");

/** "3 Nov 2026" from an ISO date or date-time ("" when empty). */
export function dayText(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

/** "3 Nov, 10:00". */
export function dayTimeText(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getDate()} ${MONTHS[d.getMonth()]}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** "3 days ago" style text for a last-used time, or "Never". */
export function lastUsed(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "Never";
  const minutes = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

export function seconds(ms: number | null): string {
  if (ms === null) return "not recorded";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function money(amount: number, currency: string): string {
  return `${currency === "USD" ? "$" : `${currency} `}${amount.toFixed(amount < 1 ? 4 : 2)}`;
}

export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/** Add the value to the list if it is missing, take it out if it is there (a group of tick boxes). */
export function toggleValue(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

/** One role per line; adds a role only when it is not there yet. */
export function addRole(current: string, role: string): string {
  const wanted = role.trim();
  if (!wanted || hasRole(current, wanted)) return current;
  const base = current.replace(/\s+$/, "");
  return base ? `${base}\n${wanted}` : wanted;
}

export function hasRole(current: string, role: string): boolean {
  const wanted = role.trim().toLowerCase();
  return current.split("\n").some((line) => line.trim().toLowerCase() === wanted);
}

/** The delete button stays off until the typed text is exactly the username (the server checks again). */
export function canConfirmDelete(typed: string, username: string): boolean {
  return typed.trim() === username && username !== "";
}

/** A real IANA time zone name the phone knows. */
export function isZoneName(name: string): boolean {
  if (!name) return false;
  try {
    new Intl.DateTimeFormat(undefined, { timeZone: name });
    return true;
  } catch {
    return false;
  }
}

export function deviceZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch {
    return "";
  }
}

const n = (count: number, one: string, many = `${one}s`) => `${count} ${count === 1 ? one : many}`;

/** The plain-words lines of an import preview, one per kind of thing, only what has something to say. */
export function importLines(r: {
  left_out: number;
  profile: { filled: string[]; kept: string[] };
  cvs: { add: number; have: number; stopped: string };
  covers: { add: number; no_job: number; stopped: string };
  notes: { add: number; kept: number };
}): string[] {
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
