"use client";

import type { Route } from "@/lib/router";
import { AiSettingsPage } from "./ai";
import { AssistantPage } from "./assistant";
import { ProfilePage } from "./profile";
import { SourcesPage } from "./sources";
import { WelcomePage } from "./welcome";

/** The screens of this area, matched against the path inside the app (no /app prefix). Add a screen = add a line here. */
export const ROUTES: Route[] = [
  { pattern: /^\/profile$/, render: () => <ProfilePage /> },
  { pattern: /^\/profile\/ai$/, render: () => <AiSettingsPage /> },
  { pattern: /^\/profile\/assistant$/, render: () => <AssistantPage /> },
  { pattern: /^\/sources$/, render: () => <SourcesPage /> },
  { pattern: /^\/welcome$/, render: () => <WelcomePage /> },
];

/** Classic page path (as in the sidebar) -> path of its replacement in this app. A migrated screen switches its sidebar entry to the new app. */
export const NAV_OVERRIDES: Record<string, string> = { "/profile/": "/profile", "/profile/ai/": "/profile/ai", "/sources/": "/sources" };
