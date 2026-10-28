import type { Notice } from "./api";

/** "3 unread notifications" for a screen reader; the empty case says there is nothing new. */
export function unreadText(count: number): string {
  if (count <= 0) return "No unread notifications";
  return count === 1 ? "1 unread notification" : `${count} unread notifications`;
}

/** What is said aloud when the count changes: only a rise is news (a first look, or a drop after reading, is silent). */
export function announcement(previous: number | null, now: number): string | null {
  if (previous === null || now <= previous) return null;
  const fresh = now - previous;
  return fresh === 1 ? "1 new notification" : `${fresh} new notifications`;
}

/** The badge shows 9+ rather than a long number. */
export function badgeText(count: number): string {
  return count > 9 ? "9+" : String(count);
}

function dayKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

/** "Today", "Yesterday" or a plain date, on the person's own clock. */
export function dayLabel(iso: string, now: Date = new Date()): string {
  const day = new Date(iso);
  if (dayKey(day) === dayKey(now)) return "Today";
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (dayKey(day) === dayKey(yesterday)) return "Yesterday";
  return day.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

/** The notices grouped by day, newest day first, keeping the server's order inside a day. */
export function groupByDay(items: Notice[], now: Date = new Date()): { label: string; items: Notice[] }[] {
  const groups: { key: string; label: string; items: Notice[] }[] = [];
  for (const item of items) {
    const key = dayKey(new Date(item.created_at));
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.items.push(item);
    else groups.push({ key, label: dayLabel(item.created_at, now), items: [item] });
  }
  return groups;
}

export function timeText(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}
