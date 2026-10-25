"use client";

import { useSyncExternalStore } from "react";

/** Whether a media query matches, kept up to date. False where there is no browser (the build-time render, unit tests). */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (notify) => {
      const list = typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query) : null;
      list?.addEventListener("change", notify);
      return () => list?.removeEventListener("change", notify);
    },
    () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query).matches : false),
    () => false,
  );
}

/** The `xl` breakpoint (80rem), where the dashboard's side column sits beside the list. rem, like Tailwind's own breakpoints. */
export const useIsWide = () => useMediaQuery("(min-width: 80rem)");
