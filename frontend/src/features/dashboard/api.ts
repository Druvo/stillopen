import { request } from "@/lib/api";
import type { ScanLog, ScanStatus } from "@/lib/types";

export type ImportResult = { ok: true; created: number; updated: number; documents: number; message: string };
export type PaperlessResult = { ok: boolean; paperless_id: number | null; error: string; url: string };

export const dashboardApi = {
  scanLog: () => request<ScanLog>("GET", "/scan/status?log=1"),
  scanStatus: () => request<ScanStatus>("GET", "/scan/status"),
  startScan: () => request<ScanStatus>("POST", "/scan"),
  importTracker: () => request<ImportResult>("POST", "/import"),
  followupDone: (jobId: number) => request<{ ok: true }>("POST", `/jobs/${jobId}/followup/done`),
  followupSnooze: (jobId: number, days = 3) => request<{ ok: true; follow_up_date: string }>("POST", `/jobs/${jobId}/followup/snooze`, { days }),
  discardDraft: (cvId: number) => request<{ ok: true }>("DELETE", `/cv/${cvId}`),
  sendToPaperless: (documentId: number) => request<PaperlessResult>("POST", `/documents/files/${documentId}/paperless`),
};

export { useMe } from "@/lib/me";
