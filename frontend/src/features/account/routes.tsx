"use client";

import { lazy } from "react";
import type { Route } from "@/lib/router";

// Each screen is its own chunk: it is downloaded when the person opens it, not with the dashboard.
const AiSettingsPage = lazy(() => import("./ai").then((m) => ({ default: m.AiSettingsPage })));
const AssistantPage = lazy(() => import("./assistant").then((m) => ({ default: m.AssistantPage })));
const ProfilePage = lazy(() => import("./profile").then((m) => ({ default: m.ProfilePage })));
const SourcesPage = lazy(() => import("./sources").then((m) => ({ default: m.SourcesPage })));
const WelcomePage = lazy(() => import("./welcome").then((m) => ({ default: m.WelcomePage })));

/** The screens of this area, matched against the path inside the app (no /app prefix). Add a screen = add a line here. */
export const ROUTES: Route[] = [
  { pattern: /^\/profile$/, render: () => <ProfilePage /> },
  { pattern: /^\/profile\/ai$/, render: () => <AiSettingsPage /> },
  { pattern: /^\/profile\/assistant$/, render: () => <AssistantPage /> },
  { pattern: /^\/sources$/, render: () => <SourcesPage /> },
  { pattern: /^\/welcome$/, render: () => <WelcomePage /> },
];
