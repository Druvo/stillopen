import { useQuery } from "@tanstack/react-query";
import { request } from "@/lib/api";
import type { Me, ScanStatus } from "@/lib/types";

export type ImportResult = { ok: true; created: number; updated: number; documents: number; message: string };
export type PaperlessResult = { ok: boolean; paperless_id: number | null; error: string; url: string };

export const dashboardApi = {
  scanStatus: () => request<ScanStatus>("GET", "/scan/status"),
  startScan: () => request<ScanStatus>("POST", "/scan"),
  importTracker: () => request<ImportResult>("POST", "/import"),
  followupDone: (jobId: number) => request<{ ok: true }>("POST", `/jobs/${jobId}/followup/done`),
  followupSnooze: (jobId: number, days = 3) => request<{ ok: true; follow_up_date: string }>("POST", `/jobs/${jobId}/followup/snooze`, { days }),
  sendToPaperless: (documentId: number) => request<PaperlessResult>("POST", `/documents/files/${documentId}/paperless`),
};

/** The signed-in person; the same cached answer the shell uses. */
export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => request<Me>("GET", "/me"), staleTime: 5 * 60_000 });
}
