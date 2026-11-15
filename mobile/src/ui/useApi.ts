import { useFocusEffect } from "expo-router";
import { useCallback, useRef, useState } from "react";

import { ApiError } from "../api/client";

export function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message === "Network request failed" ? "Could not reach the server. Check your connection and try again." : error.message;
  return "Something went wrong. Please try again.";
}

/**
 * Load something from the API every time the screen comes into view, with pull-to-refresh and an error to show.
 *
 *   const { data, error, loading, refreshing, reload, refresh } = useLoad(() => getThing(id), [id]);
 *
 * `reload()` fetches again quietly (after a save); `refresh()` is for a pull-to-refresh control.
 */
export function useLoad<T>(fetcher: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const latest = useRef(fetcher);
  latest.current = fetcher;

  const run = useCallback(async () => {
    try {
      setData(await latest.current());
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useFocusEffect(useCallback(() => { run().finally(() => setLoading(false)); }, [run, ...deps]));

  const refresh = useCallback(async () => {
    setRefreshing(true);
    await run();
    setRefreshing(false);
  }, [run]);

  return { data, setData, error, loading, refreshing, reload: run, refresh };
}

/** Run something that changes data (a save, a delete) with a busy flag and an error message. Returns the result, or undefined if it failed. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fieldsRef = useRef<Record<string, string> | undefined>(undefined);
  const [fields, setFields] = useState<Record<string, string> | undefined>(undefined);

  const run = useCallback(async <T,>(action: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setError(null);
    setFields(undefined);
    try {
      return await action();
    } catch (e) {
      setError(errorText(e));
      if (e instanceof ApiError) {
        fieldsRef.current = e.fields;
        setFields(e.fields);
      }
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);

  return { run, busy, error, fields, clearError: () => setError(null) };
}
