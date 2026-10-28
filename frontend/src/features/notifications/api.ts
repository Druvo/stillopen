import { request } from "@/lib/api";

export type Notice = { id: number; kind: string; title: string; text: string; link: string; created_at: string; read: boolean };
export type NoticeList = { items: Notice[]; unread: number };
export type NoticeKinds = { kinds: { key: string; label: string; on: boolean }[] };

export const SUMMARY_KEY = ["notifications", "summary"] as const;
export const LIST_KEY = ["notifications", "list"] as const;
export const SETTINGS_KEY = ["notifications", "settings"] as const;

export const noticeApi = {
  summary: () => request<{ unread: number }>("GET", "/notifications/summary"),
  list: (limit = 100) => request<NoticeList>("GET", `/notifications?limit=${limit}`),
  read: (id: number) => request<{ unread: number }>("POST", `/notifications/${id}/read`),
  readAll: () => request<{ unread: number }>("POST", "/notifications/read-all"),
  clearAll: () => request<{ unread: number }>("POST", "/notifications/clear"),
  clearOne: (id: number) => request<{ unread: number }>("DELETE", `/notifications/${id}`),
  settings: () => request<NoticeKinds>("GET", "/notifications/settings"),
  saveSettings: (muted: string[]) => request<NoticeKinds>("PUT", "/notifications/settings", { muted }),
};
