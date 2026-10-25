import type { ComingUpItem, Dashboard } from "@/lib/types";
import { interviewWhen, shortDate } from "./logic";

/** The plain word for each kind of item on the "Coming up" card. */
export const COMING_UP_WORD: Record<ComingUpItem["kind"], string> = { interview: "Interview", deadline: "Apply by", offer: "Reply to offer" };

/**
 * What the card lists. The server sends interviews, apply-by dates and offer reply-by dates together; an older answer (only interviews) is
 * turned into the same shape so the card never breaks.
 */
export function comingUpItems(data: Pick<Dashboard, "coming_up" | "upcoming_interviews">): ComingUpItem[] {
  if (data.coming_up) return data.coming_up;
  return data.upcoming_interviews.map((i) => ({ kind: "interview" as const, date: i.when.slice(0, 10), when: i.when, label: i.kind, company: i.company, role: i.role, job_id: i.job_id }));
}

/** Where an item leads: interviews to the interviews screen, a deadline to that job's apply screen, an offer to the offers screen. */
export function comingUpTo(item: ComingUpItem): string {
  if (item.kind === "interview") return "/interviews";
  if (item.kind === "offer") return "/offers";
  return `/jobs/${item.job_id}/apply`;
}

/** "Mon 5 Oct, 14:30" for an interview; "5 Oct" for a date that has no time. */
export function comingUpWhen(item: ComingUpItem): string {
  return item.kind === "interview" ? interviewWhen(item.when) : shortDate(item.date);
}

/** The line for one item, for example "Apply by · 5 Oct: Acme, Backend Engineer". An interview adds its kind (Phone screen). */
export function comingUpText(item: ComingUpItem): string {
  const lead = item.kind === "interview" ? `${COMING_UP_WORD.interview} · ${comingUpWhen(item)} · ${item.label}` : `${COMING_UP_WORD[item.kind]} · ${comingUpWhen(item)}`;
  return `${lead}: ${item.company}, ${item.role}`;
}

/** The text of the "see all" link: interviews and offers have their own screens, a deadline is only found on the job. */
export function comingUpAllLinks(items: ComingUpItem[]): { label: string; to: string }[] {
  const out: { label: string; to: string }[] = [];
  if (items.some((i) => i.kind === "interview")) out.push({ label: "All interviews", to: "/interviews" });
  if (items.some((i) => i.kind === "offer")) out.push({ label: "All offers", to: "/offers" });
  return out;
}
