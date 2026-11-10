// Small pure helpers shared by the job screens (ports of frontend/src/features/jobs/logic.ts and jobmgmt.ts).
import { Linking } from "react-native";

import type { Duplicate, HistoryItem, SourceHealth, StatusInfo } from "../../api/jobs";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-10-25" as "25 Oct 2026". Anything else is returned unchanged. */
export function longDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1] ?? m[2]} ${m[1]}`;
}

/** "25 Oct" (no year) for a date within this year, else with the year. */
export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const thisYear = String(new Date().getFullYear());
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1] ?? m[2]}${m[1] === thisYear ? "" : ` ${m[1]}`}`;
}

/** "3 Nov, 10:00" in the device's own time. */
export function dateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${d.getDate()} ${MONTHS[d.getMonth()]}, ${hh}:${mm}`;
}

/** "2 hours", "3 days" ago. */
export function timeAgo(iso: string, now: Date = new Date()): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const minutes = Math.max(0, Math.round((now.getTime() - then) / 60000));
  if (minutes < 60) return `${Math.max(1, minutes)} minute${minutes === 1 ? "" : "s"}`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} hour${hours === 1 ? "" : "s"}`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"}`;
}

export function statusWord(s: Pick<StatusInfo, "name" | "label"> | undefined): string {
  return s ? s.label || s.name : "its new status";
}

/** The status people reach for first: "this is not for me" (found like the website does). */
export function notForMeStatus(statuses: StatusInfo[]): StatusInfo | undefined {
  return (
    statuses.find((s) => s.name === "Not for me") ??
    statuses.find((s) => s.name === "Discarded") ??
    statuses.find((s) => !s.counts_as_applied && s.name !== "Skipped" && /closed|skip|discard/i.test(s.bucket_key))
  );
}

export function duplicateMessage(d: Pick<Duplicate, "company" | "role" | "status">): string {
  return `You already track ${d.role} at ${d.company}${d.status ? ` (${d.status})` : ""}.`;
}

export function removedMessage(count: number, name: string): string {
  return count === 1 ? `Removed ${name}.` : `Removed ${count} jobs.`;
}

/** A link we are willing to open from a posting's address: http(s) only (never a script or file address). */
export function safeWebUrl(url: string): string {
  const u = (url || "").trim();
  return /^https?:\/\/\S+$/i.test(u) ? u : "";
}

/** An apply address from a posting: a bare email becomes mailto:, an http(s) link stays, anything else is not a link. */
export function applyHref(address: string): string {
  const a = (address || "").trim();
  if (!a) return "";
  if (/^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(a)) return `mailto:${a}`;
  return safeWebUrl(a);
}

export function openLink(url: string) {
  const safe = url.startsWith("mailto:") ? url : safeWebUrl(url);
  if (safe) void Linking.openURL(safe).catch(() => undefined);
}

export function repostHint(r: { distinct_urls: number; distinct_dates: number }): string {
  return `Seen as ${r.distinct_urls} different postings on ${r.distinct_dates} separate days at this company, same title. An observation, not a verdict.`;
}

export function livingBadge(state: string): { text: string; tone: "good" | "bad" | "warn" } | null {
  if (state === "active") return { text: "Open", tone: "good" };
  if (state === "expired") return { text: "Closed", tone: "bad" };
  if (state === "uncertain") return { text: "Unclear", tone: "warn" };
  return null;
}

export function sourceHealthText(h: SourceHealth, now: Date = new Date()): string {
  if (h.state === "unknown") return "Not searched yet.";
  if (h.state === "ok") return h.checked_at ? `Worked ${timeAgo(h.checked_at, now)} ago.` : "Worked.";
  const since = h.since ? shortDate(h.since.slice(0, 10)) : "";
  const why = h.error ? `: ${h.error}` : "";
  return `Not answering${since ? ` since ${since}` : ""}${why}`;
}

export function troubleLine(t: { total: number; trouble: number } | null | undefined): string {
  if (!t || t.trouble <= 0) return "";
  return `${t.trouble} of ${t.total} ${t.total === 1 ? "source" : "sources"} had trouble in the last search.`;
}

export function historyKey(item: HistoryItem): string {
  return String(item.id);
}

/** What the add-job form starts with after a link was read: only the fields the link filled in, never overwriting what was typed. */
export function mergePrefill(current: Record<string, string>, prefill: { url: string; role: string; company: string; description: string }): Record<string, string> {
  const next = { ...current };
  for (const key of ["url", "role", "company", "description"] as const) {
    if (!next[key]?.trim() && prefill[key]) next[key] = prefill[key];
  }
  return next;
}

const LABELS = { company: "the company", role: "the role", location: "the place", pay: "the pay", deadline: "the apply-by date", link: "the link" } as const;

/** Lay what was read from pasted text over the form: only EMPTY fields are filled; place and pay go to the notes when those are empty. */
export function fillFromParsed(
  values: Record<string, string>,
  fields: { company: string; role: string; location: string; pay: string; deadline: string; link: string },
): { values: Record<string, string>; filled: string[] } {
  const next = { ...values };
  const filled: string[] = [];
  const put = (key: string, value: string, label: keyof typeof LABELS) => {
    if (value && !(next[key] ?? "").trim()) {
      next[key] = value;
      filled.push(LABELS[label]);
    }
  };
  put("company", fields.company, "company");
  put("role", fields.role, "role");
  put("url", fields.link, "link");
  put("deadline", fields.deadline, "deadline");
  const extra = [fields.location && `Place: ${fields.location}`, fields.pay && `Pay: ${fields.pay}`].filter(Boolean).join(". ");
  if (extra && !(next.notes ?? "").trim()) {
    next.notes = extra;
    if (fields.location) filled.push(LABELS.location);
    if (fields.pay) filled.push(LABELS.pay);
  }
  return { values: next, filled };
}

export function filledMessage(filled: string[], aiNotice = ""): string {
  if (filled.length === 0) return "We found nothing new to fill in. Either the form already has those details, or the text is short on them. Type them in, or paste more of the posting.";
  const list = filled.length === 1 ? filled[0] : `${filled.slice(0, -1).join(", ")} and ${filled[filled.length - 1]}`;
  return `We filled in ${list}. Please check each one before you save.${aiNotice ? ` ${aiNotice}` : ""}`;
}

/** The message after recording an application. */
export function appliedMessage(followUpDate: string): string {
  return `Good luck! We have noted it, and will remind you to follow up on ${longDate(followUpDate)}.`;
}

export type PostingsSort = "newest" | "oldest" | "company" | "title";
export const POSTINGS_SORT_OPTIONS: { value: PostingsSort; label: string }[] = [
  { value: "newest", label: "Last seen, newest first" },
  { value: "oldest", label: "Last seen, oldest first" },
  { value: "company", label: "Company A to Z" },
  { value: "title", label: "Title A to Z" },
];

export function postingsQuery({ q, source, page, sort }: { q: string; source: string; page: number; sort: PostingsSort }): string {
  const params: string[] = [];
  if (q.trim()) params.push(`q=${encodeURIComponent(q.trim())}`);
  if (source) params.push(`source=${encodeURIComponent(source)}`);
  if (page > 1) params.push(`page=${page}`);
  if (sort !== "newest") params.push(`sort=${sort}`);
  return params.length ? `?${params.join("&")}` : "";
}

export const COVER_TONES = [
  { value: "warm", label: "Warm" },
  { value: "direct", label: "Direct" },
  { value: "formal", label: "Formal" },
];

/** True when `text` is a real calendar date written YYYY-MM-DD (or empty). */
export function validIsoDate(text: string): boolean {
  if (!text) return true;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
  if (!m) return false;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return d.getFullYear() === Number(m[1]) && d.getMonth() === Number(m[2]) - 1 && d.getDate() === Number(m[3]);
}
