"use client";

import { lazy } from "react";
import type { Route } from "@/lib/router";

// Each screen is its own chunk: it is downloaded when the person opens it, not with the dashboard.
const HelpPage = lazy(() => import("./help").then((m) => ({ default: m.HelpPage })));

/** The screens of this area, matched against the path inside the app (no /app prefix). Add a screen = add a line here. */
export const ROUTES: Route[] = [{ pattern: /^\/help$/, render: () => <HelpPage /> }];
