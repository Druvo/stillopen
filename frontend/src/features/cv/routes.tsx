"use client";

import type { Route } from "@/lib/router";

/** The screens of this area, matched against the path inside the app (no /app prefix). Add a screen = add a line here. */
export const ROUTES: Route[] = [];

/** Classic page path (as in the sidebar) -> path of its replacement in this app. A migrated screen switches its sidebar entry to the new app. */
export const NAV_OVERRIDES: Record<string, string> = {};
