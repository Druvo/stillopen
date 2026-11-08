import { api, API_BASE, getToken } from "./client";
import type { CvDetail, CvList, Dashboard, Me } from "./types";

export const login = (username: string, password: string) =>
  api.post<{ token: string; expires_at: string | null; user: { id: number; username: string; email: string } }>("/api/v1/auth/login", { username, password });

export const logout = () => api.post<{ ok: boolean }>("/api/v1/auth/logout");

export const getMe = () => api.get<Me>("/api/v1/me");

export const getDashboard = () => api.get<Dashboard>("/api/v1/dashboard");

export const setJobStatus = (jobId: number, statusId: number, note = "") =>
  api.patch<{ ok: boolean; changed: boolean; status_id: number; status: string; label: string; bucket_key: string }>(`/api/v1/jobs/${jobId}/status`, {
    status: statusId,
    note,
  });

export const evaluateJob = (jobId: number) => api.post<{ ok: boolean; match_percent: number | null; method: string }>(`/api/v1/jobs/${jobId}/evaluate`);

export const listCvVersions = () => api.get<CvList>("/api/v1/cv");

export const getCvVersion = (id: number) => api.get<CvDetail>(`/api/v1/cv/${id}`);

export const approveCvVersion = (id: number) => api.post<{ ok: boolean }>(`/api/v1/cv/${id}/approve`);

export const getNotificationsSummary = () => api.get<{ unread: number }>("/api/v1/notifications/summary");

/** A classic (non-JSON) file: the token goes in the Authorization header, same as any other call, via
 * `bearer_or_login_required` on the Django side (see `tracker/api/mobileauth.py`). A plain browser open can't set
 * that header, so the caller fetches the bytes itself (see `downloadToFile` in `CvDetailScreen.tsx`). */
export async function authorizedFetch(path: string): Promise<Response> {
  const token = await getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}${path}`, { headers });
  if (!response.ok) throw new Error(`Download failed (${response.status})`);
  return response;
}
