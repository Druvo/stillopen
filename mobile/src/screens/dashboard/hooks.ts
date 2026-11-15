import { useCallback, useEffect, useRef, useState } from "react";

import { DEFAULT_PREFS, getPreferences, putPreferences, type PreferencePatch, type Preferences, type Progress } from "../../api/dashboard";
import { errorText } from "../../ui/useApi";

/**
 * The person's saved layout choices (view, tab, sort, filters, dismissed cards), kept on the server like the website does.
 * `update` changes the screen at once and saves in the background; a failed save puts the old choice back.
 */
export function usePreferences() {
  const [prefs, setPrefs] = useState<Preferences>(DEFAULT_PREFS);
  const [ready, setReady] = useState(false);
  const latest = useRef(prefs);
  latest.current = prefs;

  useEffect(() => {
    let cancelled = false;
    getPreferences()
      .then((p) => !cancelled && setPrefs({ ...DEFAULT_PREFS, ...p }))
      .catch(() => undefined) // the defaults are fine until the next time
      .finally(() => !cancelled && setReady(true));
    return () => {
      cancelled = true;
    };
  }, []);

  const update = useCallback((patch: PreferencePatch | ((current: Preferences) => PreferencePatch)) => {
    const change = typeof patch === "function" ? patch(latest.current) : patch;
    const before = latest.current;
    const next = { ...before, ...change };
    latest.current = next;
    setPrefs(next);
    putPreferences(change)
      .then((saved) => setPrefs((cur) => ({ ...cur, ...saved })))
      .catch(() => {
        latest.current = before;
        setPrefs(before);
      });
  }, []);

  return { prefs, update, ready };
}

/**
 * A search or an open/closed check: starts it, then asks how it is going every 1.5 seconds while it runs. `initial` is what the
 * dashboard already knows, so a run that was going when the screen opened is picked up. `onAdded` fires when new jobs have shown up
 * (the search carries on), `onFinished` at the end.
 */
export function useRun<T extends Progress>(opts: { read: () => Promise<T>; start: () => Promise<T>; initial?: T | null; readOnMount?: boolean; onFinished: () => void; onAdded?: () => void }) {
  const { read, start, initial, readOnMount, onFinished, onAdded } = opts;
  const [latest, setLatest] = useState<T | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const seenAdded = useRef<number | null>(null);
  const callbacks = useRef({ onFinished, onAdded, read });
  callbacks.current = { onFinished, onAdded, read };
  const current = latest ?? initial ?? null;
  const running = current?.running ?? false;

  useEffect(() => {
    if (initial?.running && !latest?.running) setLatest(initial);
  }, [initial, latest?.running]);

  useEffect(() => {
    if (!readOnMount) return;
    let cancelled = false;
    callbacks.current.read().then((p) => !cancelled && setLatest(p)).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [readOnMount]);

  useEffect(() => {
    if (seenAdded.current === null && current) seenAdded.current = current.added ?? 0;
  }, [current]);

  useEffect(() => {
    if (!running) return;
    const timer = setInterval(async () => {
      try {
        const p = await callbacks.current.read();
        setLatest(p);
        if ((p.added ?? 0) > (seenAdded.current ?? 0)) {
          seenAdded.current = p.added ?? 0;
          callbacks.current.onAdded?.();
        }
        if (!p.running) callbacks.current.onFinished();
      } catch {
        /* try again on the next tick */
      }
    }, 1500);
    return () => clearInterval(timer);
  }, [running]);

  const begin = useCallback(async () => {
    setError("");
    setStarting(true);
    try {
      const p = await start();
      seenAdded.current = p.added ?? 0;
      setLatest(p);
    } catch (e) {
      setError(errorText(e).replace(/^$/, "Could not start. Please try again."));
    } finally {
      setStarting(false);
    }
  }, [start]);

  return { current, running, starting, error, begin };
}
