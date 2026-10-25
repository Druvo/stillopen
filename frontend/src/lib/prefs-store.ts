import { createPrefsSaver, mergePreferences, normalizePreferences, type PrefsSaver } from "./preferences";
import type { Me, PreferencePatch, Preferences } from "./types";

let saver: PrefsSaver | null = null;

/** The one saver of this page (changes from every screen share one debounce). Created on first use with the handlers of that moment. */
export function getSaver(make: () => PrefsSaver): PrefsSaver {
  return (saver ??= make());
}

/** Test hook: forget the saver. */
export function resetSaver() {
  saver = null;
}

/** A fresh /me with the not-yet-confirmed local changes laid over it. */
export function applyPending(me: Me): Me {
  const base = normalizePreferences(me.preferences);
  const pending: PreferencePatch = saver?.pending() ?? {};
  return { ...me, preferences: Object.keys(pending).length ? mergePreferences(base, pending) : base };
}

export function flushPreferences(keepalive = true) {
  saver?.flush(keepalive);
}

export type { Preferences };
export { createPrefsSaver };
