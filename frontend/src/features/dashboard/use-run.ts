"use client";

import { useEffect, useRef, useState } from "react";
import { errorText } from "@/lib/api";
import { notify } from "@/lib/toast";
import type { Progress } from "@/lib/types";

/**
 * A search or an open/closed check: starts it, then polls every 1.5 seconds while it runs. `initial` is what the dashboard already knows,
 * so a run that was going when the page opened is picked up. `onAdded` fires when a search has found new jobs, `onFinished` at the end.
 */
export function useRun<T extends Progress>(opts: { read: () => Promise<T>; start: () => Promise<T>; initial?: T | null; readOnMount?: boolean; onFinished: () => void; onAdded?: () => void }) {
  const { read, start, initial, readOnMount, onFinished, onAdded } = opts;
  const [latest, setLatest] = useState<T | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const seenAdded = useRef<number | null>(null);
  const current = latest ?? initial ?? null;
  const running = current?.running ?? false;

  useEffect(() => {
    if (initial?.running && !latest?.running) setLatest(initial);
  }, [initial, latest?.running]);

  useEffect(() => {
    if (!readOnMount) return;
    let cancelled = false;
    read().then((p) => !cancelled && setLatest(p)).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [read, readOnMount]);

  useEffect(() => {
    if (seenAdded.current === null && current) seenAdded.current = current.added ?? 0;
  }, [current]);

  useEffect(() => {
    if (!running) return;
    const timer = setInterval(async () => {
      try {
        const p = await read();
        setLatest(p);
        if ((p.added ?? 0) > (seenAdded.current ?? 0)) {
          seenAdded.current = p.added ?? 0;
          onAdded?.(); // the first jobs are ready: show them now, the search carries on
        }
        if (!p.running) onFinished();
      } catch {
        /* try again on the next tick */
      }
    }, 1500);
    return () => clearInterval(timer);
  }, [running, read, onFinished, onAdded]);

  const begin = async () => {
    setError("");
    setStarting(true);
    try {
      const p = await start();
      seenAdded.current = p.added ?? 0;
      setLatest(p);
    } catch (e) {
      const text = errorText(e, "Could not start. Please try again.");
      setError(text);
      notify(text, "error");
    } finally {
      setStarting(false);
    }
  };
  return { current, running, starting, error, begin };
}
