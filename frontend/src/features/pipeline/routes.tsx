"use client";

import { lazy } from "react";
import type { Route } from "@/lib/router";

// Each screen is its own chunk: it is downloaded when the person opens it, not with the dashboard.
const Interviews = lazy(() => import("./interviews").then((m) => ({ default: m.Interviews })));
const Contacts = lazy(() => import("./contacts").then((m) => ({ default: m.Contacts })));
const Offers = lazy(() => import("./offers").then((m) => ({ default: m.Offers })));
const Insights = lazy(() => import("./insights").then((m) => ({ default: m.Insights })));

/** The screens of this area, matched against the path inside the app (no /app prefix). Add a screen = add a line here. */
export const ROUTES: Route[] = [
  { pattern: /^\/interviews$/, render: () => <Interviews /> },
  { pattern: /^\/contacts$/, render: () => <Contacts /> },
  { pattern: /^\/offers$/, render: () => <Offers /> },
  { pattern: /^\/insights$/, render: () => <Insights /> },
];
