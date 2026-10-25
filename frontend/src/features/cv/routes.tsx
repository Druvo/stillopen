"use client";

import { lazy } from "react";
import type { Route } from "@/lib/router";

// Each screen is its own chunk: it is downloaded when the person opens it, not with the dashboard.
const CvList = lazy(() => import("./screens").then((m) => ({ default: m.CvList })));
const CvDetail = lazy(() => import("./screens").then((m) => ({ default: m.CvDetail })));
const CvDiff = lazy(() => import("./screens").then((m) => ({ default: m.CvDiff })));
const CoverDetail = lazy(() => import("./screens").then((m) => ({ default: m.CoverDetail })));

/** The screens of this area, matched against the path inside the app (no /app prefix). Add a screen = add a line here. */
export const ROUTES: Route[] = [
  { pattern: /^\/cv$/, render: () => <CvList /> },
  { pattern: /^\/cv\/(\d+)$/, render: ([id]) => <CvDetail key={id} id={Number(id)} /> },
  { pattern: /^\/cv\/(\d+)\/diff$/, render: ([id]) => <CvDiff key={id} id={Number(id)} /> },
  { pattern: /^\/cover\/(\d+)$/, render: ([id]) => <CoverDetail key={id} id={Number(id)} /> },
];
