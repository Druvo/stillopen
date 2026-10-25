import { clearPersistedStorage, tabStorage } from "./persist";
import type { Dashboard, PreferencePatch, Preferences, Progress, ScanLog } from "./types";

/** Same-origin calls to Django. The session cookie authenticates; unsafe methods carry Django's CSRF token. */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    /** Per-field messages when a form was refused: { company: ["This field is required."] }. */
    public fields: Record<string, string[]> = {},
    /** The rest of the answer (for example `duplicate` on a 409), when there was more than the message. */
    public data: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

export function csrfToken(): string {
  const match = document.cookie.split("; ").find((c) => c.startsWith("csrftoken="));
  return match ? decodeURIComponent(match.slice("csrftoken=".length)) : "";
}

type Method = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

export async function request<T>(method: Method, path: string, body?: unknown, options: { keepalive?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: BodyInit | undefined;
  if (method !== "GET") headers["X-CSRFToken"] = csrfToken();
  if (body instanceof FormData) {
    payload = body; // the browser sets the multipart boundary
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const response = await fetch(`/api/v1${path}`, { method, headers, credentials: "same-origin", body: payload, keepalive: options.keepalive });
  if (response.status === 401) {
    // Signed out (session ended): forget what this tab kept of their data, go to the normal sign-in page and come straight back.
    clearPersistedStorage(tabStorage());
    window.location.assign(`/accounts/login/?next=${encodeURIComponent(window.location.pathname)}`);
    throw new ApiError("Please sign in again.", 401);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof data?.error === "string" ? data.error : "Something went wrong. Please try again.";
    throw new ApiError(message, response.status, data?.fields ?? {}, data && typeof data === "object" ? data : {});
  }
  return data as T;
}

export function errorText(error: unknown, fallback = "Something went wrong. Please try again."): string {
  return error instanceof ApiError ? error.message : fallback;
}

export const api = {
  dashboard: () => request<Dashboard>("GET", "/dashboard"),
  setStatus: (jobId: number, statusId: number, note = "") =>
    request<{ ok: true; changed: boolean; status_id: number; status: string; label: string; bucket_key: string }>("PATCH", `/jobs/${jobId}/status`, note ? { status: statusId, note } : { status: statusId }),
  evaluate: (jobId: number) => request<{ ok: true; match_percent: number; method: string }>("POST", `/jobs/${jobId}/evaluate`),
  startScan: () => request<Progress>("POST", "/scan"),
  scanStatus: () => request<Progress>("GET", "/scan/status"),
  scanLog: () => request<ScanLog>("GET", "/scan/status?log=1"),
  savePreferences: (patch: PreferencePatch, keepalive = false) => request<Preferences>("PUT", "/preferences", patch, { keepalive }),
  startLiveness: () => request<Progress>("POST", "/liveness"),
  livenessStatus: () => request<Progress>("GET", "/liveness/status"),
};
