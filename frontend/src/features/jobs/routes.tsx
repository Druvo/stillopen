"use client";

import type { Route } from "@/lib/router";
import { AddJob } from "./add-job";
import { ApplyAssistant } from "./apply";
import { EditJob } from "./edit-job";
import { Knowledge } from "./knowledge";
import { Postings } from "./postings";

/** The screens of this area, matched against the path inside the app (no /app prefix). Add a screen = add a line here. */
export const ROUTES: Route[] = [
  { pattern: /^\/jobs\/add$/, render: () => <AddJob /> },
  { pattern: /^\/jobs\/(\d+)\/edit$/, render: ([id]) => <EditJob key={id} id={Number(id)} /> },
  { pattern: /^\/jobs\/(\d+)\/apply$/, render: ([id]) => <ApplyAssistant key={id} id={Number(id)} /> },
  { pattern: /^\/postings$/, render: () => <Postings /> },
  { pattern: /^\/knowledge$/, render: () => <Knowledge /> },
];

/** Classic page path (as in the sidebar) -> path of its replacement in this app. A migrated screen switches its sidebar entry to the new app. */
export const NAV_OVERRIDES: Record<string, string> = { "/jobs/add/": "/jobs/add", "/postings/": "/postings", "/knowledge/": "/knowledge" };
