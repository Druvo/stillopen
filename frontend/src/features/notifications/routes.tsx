"use client";

import { lazy } from "react";
import type { Route } from "@/lib/router";

const NotificationsPage = lazy(() => import("./screens").then((m) => ({ default: m.NotificationsPage })));

/** The screens of this area, matched against the path inside the app (no /app prefix). */
export const ROUTES: Route[] = [{ pattern: /^\/notifications$/, render: () => <NotificationsPage /> }];
