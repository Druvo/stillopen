// The opt-in Google connection and the per-job mail: tracker/api/google.py.
// Nothing here sends by itself: `send` needs the digest of the previewed message and confirm: true.
import { api } from "./client";

const V = "/api/v1";

export type GoogleStatus = {
  available: boolean; connected: boolean; email: string; connected_at: string | null; calendar_sync: boolean; problem: string; message: string;
};
export type MailItem = { id: number; sender: string; sent_at: string; snippet: string; from_me: boolean };
export type MailList = { connected: boolean; linked: boolean; messages: MailItem[]; checked_at: string | null };
export type MailCheck = { new: number; cached: boolean; messages: MailItem[]; linked?: boolean };
export type MessageInput = { to: string; subject: string; body: string; cv: number | null; cover: number | null };
export type Preview = { to: string; subject: string; body: string; from: string; digest: string; attachments: { name: string; bytes: number }[] };
export type CalendarSync = { changed: number; checked: number; cached: boolean; note: string };

/** What the apply screen knows about a job: the draft, the CVs that may be sent, the cover letters and the Google state. */
export type ApplyInfo = {
  job: { id: number; company: string; role: string; url: string; applied: boolean };
  versions: { id: number; label: string; kind_label: string; created: string; flagged: boolean }[];
  selected: number | null;
  cover_letters: { id: number; created: string; needs_review: boolean }[];
  draft: { subject: string; body: string };
  google: { available: boolean; connected: boolean; suggested_to: string; thread: boolean };
};

export const googleApi = {
  status: () => api.get<GoogleStatus>(`${V}/google/status`),
  disconnect: () => api.post<GoogleStatus>(`${V}/google/disconnect`),
  setCalendarSync: (calendar_sync: boolean) => api.patch<GoogleStatus>(`${V}/google/settings`, { calendar_sync }),
  syncCalendar: (force: boolean) => api.post<CalendarSync>(`${V}/google/calendar/sync?force=${force}`),
  applyInfo: (job: number) => api.get<ApplyInfo>(`${V}/jobs/${job}/apply`),
  preview: (job: number, m: MessageInput) => api.post<Preview>(`${V}/jobs/${job}/google/preview`, m),
  send: (job: number, m: MessageInput, digest: string) =>
    api.post<{ ok: true; to: string; follow_up_date: string }>(`${V}/jobs/${job}/google/send`, { ...m, digest, confirm: true }),
  messages: (job: number) => api.get<MailList>(`${V}/jobs/${job}/google/messages`),
  check: (job: number, contact_email: string, force: boolean) => api.post<MailCheck>(`${V}/jobs/${job}/google/check`, { contact_email, force }),
  draft: (job: number, message_id: number, with_times: boolean) =>
    api.post<{ draft: string; flags: { kind: string; text: string }[]; times: string }>(`${V}/jobs/${job}/google/draft`, { message_id, with_times }),
  times: (job: number) => api.post<{ text: string; count: number }>(`${V}/jobs/${job}/google/times`),
};
