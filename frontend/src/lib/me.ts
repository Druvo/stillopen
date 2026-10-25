"use client";

import { useQuery } from "@tanstack/react-query";
import { request } from "./api";
import { applyPending } from "./prefs-store";
import type { Me } from "./types";

export const ME_KEY = ["me"] as const;

/** The signed-in person and their saved preferences; one cached answer for the whole app. */
export function useMe() {
  return useQuery({
    queryKey: ME_KEY,
    // A fresh read must not undo a change made here that the server has not confirmed yet.
    queryFn: async () => applyPending(await request<Me>("GET", "/me")),
    // Short on purpose: a change made on another device shows after a reload within seconds. The answer is tiny and the browser revalidates it (304).
    staleTime: 10_000,
  });
}
