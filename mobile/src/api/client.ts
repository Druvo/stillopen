import * as SecureStore from "expo-secure-store";

// Which StillOpen server this phone talks to. The released app is not tied to one site: the person types their server's address on the
// sign-in screen (or opens a stillopen://connect?server=... link from their server's "Get the app" page) and it is remembered. A developer
// build can set EXPO_PUBLIC_API_BASE to skip that. `API_BASE` is a live binding: it changes when `setApiBase` runs.
const SERVER_KEY = "stillopen_server";
export let API_BASE = process.env.EXPO_PUBLIC_API_BASE ?? "";

/** An address as people type it ("jobs.example.com", "https://jobs.example.com/") -> "https://jobs.example.com", or null if it is not usable. */
export function normalizeServer(input: string): string | null {
  let text = input.trim();
  if (!text) return null;
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(text)) text = `https://${text}`;
  try {
    const url = new URL(text);
    if (url.protocol !== "https:" && !(url.protocol === "http:" && __DEV__)) return null; // a release build only talks over HTTPS
    if (!url.hostname || url.username || url.password) return null;
    return `${url.protocol}//${url.host}`;
  } catch {
    return null;
  }
}

export async function loadApiBase(): Promise<string> {
  const saved = await SecureStore.getItemAsync(SERVER_KEY);
  if (saved) API_BASE = saved;
  return API_BASE;
}

export async function setApiBase(address: string): Promise<boolean> {
  const clean = normalizeServer(address);
  if (!clean) return false;
  if (clean !== API_BASE) await setToken(null); // a token belongs to one server
  API_BASE = clean;
  await SecureStore.setItemAsync(SERVER_KEY, clean);
  return true;
}

const TOKEN_KEY = "stillopen_token";

let cachedToken: string | null | undefined;

export async function getToken(): Promise<string | null> {
  if (cachedToken !== undefined) return cachedToken;
  cachedToken = await SecureStore.getItemAsync(TOKEN_KEY);
  return cachedToken;
}

export async function setToken(token: string | null) {
  cachedToken = token;
  if (token) await SecureStore.setItemAsync(TOKEN_KEY, token);
  else await SecureStore.deleteItemAsync(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  fields?: Record<string, string>;
  constructor(status: number, message: string, fields?: Record<string, string>) {
    super(message);
    this.status = status;
    this.fields = fields;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = await getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(options.headers as Record<string, string>) };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;

  if (!response.ok) {
    if (response.status === 401) await setToken(null); // the token is gone or revoked -- send the person back to sign in
    throw new ApiError(response.status, (data && data.error) || `Request failed (${response.status})`, data && data.fields);
  }
  return data as T;
}

/** Send files and fields as multipart form data (no JSON Content-Type: fetch sets the boundary itself). */
async function upload<T>(path: string, form: FormData, method: "POST" | "PUT" | "PATCH" = "POST"): Promise<T> {
  const token = await getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}${path}`, { method, headers, body: form });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    if (response.status === 401) await setToken(null);
    throw new ApiError(response.status, (data && data.error) || `Request failed (${response.status})`, data && data.fields);
  }
  return data as T;
}

export const api = {
  upload,
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: "PUT", body: body !== undefined ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
