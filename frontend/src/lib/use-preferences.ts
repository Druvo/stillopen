"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorText } from "./api";
import { ME_KEY, useMe } from "./me";
import { createPrefsSaver, DEFAULT_PREFERENCES, mergePreferences, normalizePreferences, readLocalDisplay } from "./preferences";
import { flushPreferences, getSaver } from "./prefs-store";
import { notify } from "./toast";
import type { Me, PreferencePatch, Preferences } from "./types";

/**
 * The person's saved choices (view, tab, sort, filters, sidebar, theme, text size, density). They come with /me, a change shows at once
 * and goes to the server once the person stops changing things for 400 ms. Before /me has answered, the display choices come from the
 * browser's own copy so the page does not flash.
 */
export function usePreferences(): { prefs: Preferences; ready: boolean; known: boolean; update: (patch: PreferencePatch | ((current: Preferences) => PreferencePatch)) => void } {
  const client = useQueryClient();
  const me = useMe();
  const server = me.data?.preferences;
  // The browser's own copy is read after the first render, so the build-time page and the first browser render are the same.
  const [local, setLocal] = useState<ReturnType<typeof readLocalDisplay> | null>(null);
  useEffect(() => setLocal(readLocalDisplay()), []);
  const prefs = useMemo(() => (server ? normalizePreferences(server) : { ...DEFAULT_PREFERENCES, ...(local ?? {}) }), [server, local]);

  const update = useCallback(
    (change: PreferencePatch | ((current: Preferences) => PreferencePatch)) => {
      // A change that depends on what is there (a toggle, one more filter) is worked out from the latest copy, not from what the last render saw:
      // two quick changes in a row must both count.
      const latest = normalizePreferences(client.getQueryData<Me>(ME_KEY)?.preferences);
      const patch = typeof change === "function" ? change(latest) : change;
      if (Object.keys(patch).length === 0) return;
      const saver = getSaver(() =>
        createPrefsSaver({
          send: (p, keepalive) => api.savePreferences(p, keepalive),
          onSaved: (saved, settled) => {
            if (settled) client.setQueryData<Me>(ME_KEY, (m) => (m ? { ...m, preferences: normalizePreferences(saved) } : m));
          },
          onError: (error) => {
            notify(`${errorText(error, "Could not save that setting.")} It was not saved.`, "error");
            void client.invalidateQueries({ queryKey: ME_KEY });
          },
        }),
      );
      client.setQueryData<Me>(ME_KEY, (m) => (m ? { ...m, preferences: mergePreferences(normalizePreferences(m.preferences), patch) } : m));
      saver.queue(patch);
    },
    [client],
  );

  return { prefs, ready: !!server, known: !!server || local !== null, update };
}

/** Sends a change that is still waiting when the page is left or hidden. Mount once in the shell. */
export function useFlushPreferencesOnLeave() {
  useEffect(() => {
    const onHide = () => flushPreferences(true);
    const onVisibility = () => document.visibilityState === "hidden" && onHide();
    window.addEventListener("pagehide", onHide);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("pagehide", onHide);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);
}
