"use client";

import { lazy } from "react";
import type { Route } from "@/lib/router";

// Each screen is its own chunk: it is downloaded when the person opens it, not with the dashboard.
const Interviews = lazy(() => import("./interviews").then((m) => ({ default: m.Interviews })));
const Contacts = lazy(() => import("./contacts").then((m) => ({ default: m.Contacts })));
const Offers = lazy(() => import("./offers").then((m) => ({ default: m.Offers })));
const JobProcess = lazy(() => import("./process").then((m) => ({ default: m.JobProcess })));
const QuestionBank = lazy(() => import("./bank").then((m) => ({ default: m.QuestionBank })));
const Companies = lazy(() => import("./companies").then((m) => ({ default: m.Companies })));
const CompanyDetail = lazy(() => import("./companies").then((m) => ({ default: m.CompanyDetail })));
const Insights = lazy(() => import("./insights").then((m) => ({ default: m.Insights })));

function safeDecode(text: string): string {
  try {
    return decodeURIComponent(text);
  } catch {
    return text;
  }
}

/** The screens of this area, matched against the path inside the app (no /app prefix). Add a screen = add a line here. */
export const ROUTES: Route[] = [
  { pattern: /^\/interviews$/, render: () => <Interviews /> },
  { pattern: /^\/contacts$/, render: () => <Contacts /> },
  { pattern: /^\/offers$/, render: () => <Offers /> },
  { pattern: /^\/jobs\/(\d+)\/process$/, render: ([id]) => <JobProcess key={id} id={Number(id)} /> },
  { pattern: /^\/questions$/, render: () => <QuestionBank /> },
  { pattern: /^\/companies$/, render: () => <Companies /> },
  { pattern: /^\/companies\/(.+)$/, render: ([name]) => <CompanyDetail key={name} name={safeDecode(name)} /> },
  { pattern: /^\/insights$/, render: () => <Insights /> },
];
