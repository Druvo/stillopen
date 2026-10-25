import type { PersistedClient } from "@tanstack/react-query-persist-client";

/**
 * The query cache is kept in this tab's sessionStorage so a reload paints from the last answers and refreshes behind them.
 * sessionStorage (not localStorage) on purpose: personal job data goes when the tab does.
 */
export const CACHE_KEY = "stillopen-query-cache";
export const UID_KEY = "stillopen-cache-uid";
/** Change this when the shape of any cached answer changes: old caches are then dropped instead of misread. */
export const APP_BUSTER = "v1";
export const MAX_AGE_MS = 6 * 60 * 60 * 1000;
/** Characters, roughly bytes. sessionStorage holds about 5 MB; stay well inside so a write never fails. */
export const MAX_BYTES = 1_500_000;

/** A cache belongs to one person: another id (or none yet) is another buster, so it is never restored for them. */
export function cacheBuster(uid: number | null): string {
  return `${APP_BUSTER}:${uid ?? "anon"}`;
}

export function readUid(storage: Pick<Storage, "getItem"> | null): number | null {
  try {
    const raw = storage?.getItem(UID_KEY);
    const n = raw ? Number(raw) : NaN;
    return Number.isInteger(n) && n > 0 ? n : null;
  } catch {
    return null;
  }
}

export function writeUid(storage: Pick<Storage, "setItem"> | null, uid: number) {
  try {
    storage?.setItem(UID_KEY, String(uid));
  } catch {
    /* not remembered: the next load starts without cached data */
  }
}

/** Removes everything this tab kept: the cache and whose it was. Called on sign-out and when the session has ended (401). */
export function clearPersistedStorage(storage: Pick<Storage, "removeItem"> | null) {
  try {
    storage?.removeItem(CACHE_KEY);
    storage?.removeItem(UID_KEY);
  } catch {
    /* nothing to clear */
  }
}

export function tabStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

/** Answers that are never kept: live progress. Everything else is a plain read of the person's own data. */
export function shouldPersistKey(key: readonly unknown[]): boolean {
  const head = String(key[0] ?? "");
  return head !== "scan" && head !== "scan-log" && head !== "liveness";
}

/** If the cache is too big to store, keep only the small essentials (who is signed in and their preferences) rather than failing. */
export function trimToLimit(client: PersistedClient, maxBytes = MAX_BYTES): PersistedClient {
  if (JSON.stringify(client).length <= maxBytes) return client;
  const essentials = client.clientState.queries.filter((q) => q.queryKey[0] === "me");
  return { ...client, clientState: { mutations: [], queries: essentials } };
}
