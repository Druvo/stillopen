"use client";

import { lazy } from "react";
import type { Route } from "@/lib/router";

// Each screen is its own chunk: it is downloaded when the person opens it, not with the dashboard.
const AddJob = lazy(() => import("./add-job").then((m) => ({ default: m.AddJob })));
const ApplyAssistant = lazy(() => import("./apply").then((m) => ({ default: m.ApplyAssistant })));
const EditJob = lazy(() => import("./edit-job").then((m) => ({ default: m.EditJob })));
const Knowledge = lazy(() => import("./knowledge").then((m) => ({ default: m.Knowledge })));
const Postings = lazy(() => import("./postings").then((m) => ({ default: m.Postings })));

/** The screens of this area, matched against the path inside the app (no /app prefix). Add a screen = add a line here. */
export const ROUTES: Route[] = [
  { pattern: /^\/jobs\/add$/, render: () => <AddJob /> },
  { pattern: /^\/jobs\/(\d+)\/edit$/, render: ([id]) => <EditJob key={id} id={Number(id)} /> },
  { pattern: /^\/jobs\/(\d+)\/apply$/, render: ([id]) => <ApplyAssistant key={id} id={Number(id)} /> },
  { pattern: /^\/postings$/, render: () => <Postings /> },
  { pattern: /^\/knowledge$/, render: () => <Knowledge /> },
];
