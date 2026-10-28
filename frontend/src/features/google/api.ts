import { request } from "@/lib/api";

export type GoogleStatus = {
  available: boolean;
  connected: boolean;
  email: string;
  connected_at: string | null;
  calendar_sync: boolean;
  problem: string;
  message: string;
};
export type MailItem = { id: number; sender: string; sent_at: string; snippet: string; from_me: boolean };
export type MailList = { connected: boolean; linked: boolean; messages: MailItem[]; checked_at: string | null };
export type MailCheck = { new: number; cached: boolean; messages: MailItem[]; linked?: boolean };
export type MessageInput = { to: string; subject: string; body: string; cv: number | null; cover: number | null };
export type Preview = { to: string; subject: string; body: string; from: string; digest: string; attachments: { name: string; bytes: number }[] };
export type CalendarSync = { changed: number; checked: number; cached: boolean; note: string };

export const googleApi = {
  status: () => request<GoogleStatus>("GET", "/google/status"),
  connect: () => request<{ url: string }>("POST", "/google/connect"),
  disconnect: () => request<GoogleStatus>("POST", "/google/disconnect"),
  setCalendarSync: (calendar_sync: boolean) => request<GoogleStatus>("PATCH", "/google/settings", { calendar_sync }),
  syncCalendar: (force: boolean) => request<CalendarSync>("POST", `/google/calendar/sync?force=${force}`),
  preview: (job: number, m: MessageInput) => request<Preview>("POST", `/jobs/${job}/google/preview`, m),
  send: (job: number, m: MessageInput, digest: string) =>
    request<{ ok: true; to: string; follow_up_date: string }>("POST", `/jobs/${job}/google/send`, { ...m, digest, confirm: true }),
  messages: (job: number) => request<MailList>("GET", `/jobs/${job}/google/messages`),
  check: (job: number, contact_email: string, force: boolean) => request<MailCheck>("POST", `/jobs/${job}/google/check`, { contact_email, force }),
  draft: (job: number, message_id: number, with_times: boolean) =>
    request<{ draft: string; flags: { kind: string; text: string }[]; times: string }>("POST", `/jobs/${job}/google/draft`, { message_id, with_times }),
  times: (job: number) => request<{ text: string; count: number }>("POST", `/jobs/${job}/google/times`),
};
