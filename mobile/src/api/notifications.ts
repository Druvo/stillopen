// The notification centre: tracker/api/notifications.py. Summary is the cheap polled count behind the unread badge.
import { api } from "./client";

const V = "/api/v1";

export type Notice = { id: number; kind: string; title: string; text: string; link: string; created_at: string; read: boolean };
export type NoticeList = { items: Notice[]; unread: number };
export type NoticeKinds = { kinds: { key: string; label: string; on: boolean }[] };

export const noticeApi = {
  summary: () => api.get<{ unread: number }>(`${V}/notifications/summary`),
  list: (limit = 100) => api.get<NoticeList>(`${V}/notifications?limit=${limit}`),
  read: (id: number) => api.post<{ unread: number }>(`${V}/notifications/${id}/read`),
  readAll: () => api.post<{ unread: number }>(`${V}/notifications/read-all`),
  clearAll: () => api.post<{ unread: number }>(`${V}/notifications/clear`),
  clearOne: (id: number) => api.delete<{ unread: number }>(`${V}/notifications/${id}`),
  settings: () => api.get<NoticeKinds>(`${V}/notifications/settings`),
  saveSettings: (muted: string[]) => api.put<NoticeKinds>(`${V}/notifications/settings`, { muted }),
};

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

export function unreadText(count: number): string {
  if (count <= 0) return "No unread notifications";
  return count === 1 ? "1 unread notification" : `${count} unread notifications`;
}

/** The badge shows 9+ rather than a long number. */
export function badgeText(count: number): string {
  return count > 9 ? "9+" : String(count);
}
