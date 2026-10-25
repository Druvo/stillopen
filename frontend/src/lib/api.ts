import type { Dashboard, Progress } from "./types";

/** Same-origin calls to Django. The session cookie authenticates; unsafe methods carry Django's CSRF token. */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export function csrfToken(): string {
  const match = document.cookie.split("; ").find((c) => c.startsWith("csrftoken="));
  return match ? decodeURIComponent(match.slice("csrftoken=".length)) : "";
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") {
    headers["X-CSRFToken"] = csrfToken();
    if (body !== undefined) headers["Content-Type"] = "application/json";
  }
  const response = await fetch(`/api/v1${path}`, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 401) {
    // Signed out (session ended): go to the normal sign-in page and come straight back.
    window.location.assign(`/accounts/login/?next=${encodeURIComponent(window.location.pathname)}`);
    throw new ApiError("Please sign in again.", 401);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof data?.error === "string" ? data.error : "Something went wrong. Please try again.";
    throw new ApiError(message, response.status);
  }
  return data as T;
}

export const api = {
  dashboard: () => request<Dashboard>("GET", "/dashboard"),
  setStatus: (jobId: number, statusId: number) =>
    request<{ ok: true; status_id: number; status: string; bucket_key: string }>("PATCH", `/jobs/${jobId}/status`, { status: statusId }),
  evaluate: (jobId: number) => request<{ ok: true; match_percent: number; method: string }>("POST", `/jobs/${jobId}/evaluate`),
  startScan: () => request<Progress>("POST", "/scan"),
  scanStatus: () => request<Progress>("GET", "/scan/status"),
  startLiveness: () => request<Progress>("POST", "/liveness"),
  livenessStatus: () => request<Progress>("GET", "/liveness/status"),
};
