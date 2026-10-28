import type { PersistedClient } from "@tanstack/react-query-persist-client";

/**
 * The query cache is kept in this tab's sessionStorage so a reload paints from the last answers and refreshes behind them.
 * sessionStorage (not localStorage) on purpose: personal job data goes when the tab does.
 */
export const CACHE_KEY = "stillopen-query-cache";
export const UID_KEY = "stillopen-cache-uid";
const OTHER_PERSONAL_KEYS = ["stillopen-cv-builder-draft", "stillopen-quickadd-prefill"];
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

/**
 * Set the moment this tab's person signs out (or their session is found to have ended). From then on nothing is written to the tab's
 * storage again: the cache is saved in throttled steps and answers still on their way keep arriving, so without this a write queued
 * just before the sign-out could land after the clearing and leave the last person's data behind until the page actually unloads.
 */
let ended = false;
export const storageEnded = () => ended;
/** Test hook (a real page leaves for the sign-in page and starts fresh). */
export function resetStorageEnded() {
  ended = false;
}

/** A view of the tab's storage that refuses writes once the tab's person is gone. The persister writes through this. */
export function guardedStorage(storage: Storage | null): Storage | null {
  if (!storage) return null;
  return {
    get length() {
      return storage.length;
    },
    key: (i: number) => storage.key(i),
    getItem: (k: string) => storage.getItem(k),
    setItem: (k: string, v: string) => {
      if (!ended) storage.setItem(k, v);
    },
    removeItem: (k: string) => storage.removeItem(k),
    clear: () => storage.clear(),
  };
}

export function writeUid(storage: Pick<Storage, "setItem"> | null, uid: number) {
  if (ended) return;
  try {
    storage?.setItem(UID_KEY, String(uid));
  } catch {
    /* not remembered: the next load starts without cached data */
  }
}

/** Removes everything this tab kept: the cache and whose it was. Called on sign-out and when the session has ended (401). */
export function clearPersistedStorage(storage: Pick<Storage, "removeItem"> | null) {
  ended = true;
  try {
    storage?.removeItem(CACHE_KEY);
    storage?.removeItem(UID_KEY);
    // Other things this tab kept for the person (a half-made CV, a pasted job waiting to be reviewed) leave with them too.
    for (const k of OTHER_PERSONAL_KEYS) storage?.removeItem(k);
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
