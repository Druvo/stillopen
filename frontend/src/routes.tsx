"use client";

import { Dashboard } from "@/features/dashboard/dashboard";
import { PrepList, PrepPlan, PrepToday } from "@/features/prep/screens";
import type { Route } from "@/lib/router";

/** Every screen of the new app. Screens that have not moved yet are linked to their classic page from the sidebar. */
export const ROUTES: Route[] = [
  { pattern: /^\/$/, render: () => <Dashboard /> },
  { pattern: /^\/prep$/, render: () => <PrepList /> },
  { pattern: /^\/prep\/(\d+)$/, render: ([id]) => <PrepPlan key={id} id={Number(id)} /> },
  { pattern: /^\/prep\/(\d+)\/today$/, render: ([id]) => <PrepToday key={id} id={Number(id)} /> },
];

/** Sidebar: [label, path, whether it is a screen of this app (otherwise a classic Django page)]. */
export const NAV: [string, string, boolean][] = [
  ["Dashboard", "/", true],
  ["Add job", "/jobs/add/", false],
  ["All postings", "/postings/", false],
  ["Job sources", "/sources/", false],
  ["Interviews", "/interviews/", false],
  ["Contacts", "/contacts/", false],
  ["Offers", "/offers/", false],
  ["Prep plans", "/prep", true],
  ["Insights", "/insights/", false],
  ["CVs", "/cv/", false],
  ["Documents", "/knowledge/", false],
  ["Profile", "/profile/", false],
  ["AI settings", "/profile/ai/", false],
];
