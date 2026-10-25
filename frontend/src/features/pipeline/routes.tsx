"use client";

import type { Route } from "@/lib/router";
import { Contacts } from "./contacts";
import { Insights } from "./insights";
import { Interviews } from "./interviews";
import { Offers } from "./offers";

/** The screens of this area, matched against the path inside the app (no /app prefix). Add a screen = add a line here. */
export const ROUTES: Route[] = [
  { pattern: /^\/interviews$/, render: () => <Interviews /> },
  { pattern: /^\/contacts$/, render: () => <Contacts /> },
  { pattern: /^\/offers$/, render: () => <Offers /> },
  { pattern: /^\/insights$/, render: () => <Insights /> },
];

/** Classic page path (as in the sidebar) -> path of its replacement in this app. A migrated screen switches its sidebar entry to the new app. */
export const NAV_OVERRIDES: Record<string, string> = {
  "/interviews/": "/interviews",
  "/contacts/": "/contacts",
  "/offers/": "/offers",
  "/insights/": "/insights",
};
