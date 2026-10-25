"use client";

import type { Route } from "@/lib/router";
import { Contacts } from "./contacts";
import { Insights } from "./insights";
import { Interviews } from "./interviews";
import { Offers } from "./offers";

/** The screens of this area, matched against the path inside the app (no /app prefix). Add a screen = add a line here. */
export const ROUTES: Route[] = [
  { pattern: /^\/interviews$/, render: () => <Interviews /> },
  { pattern: /^\/contacts$/, render: () => <Contacts /> },
  { pattern: /^\/offers$/, render: () => <Offers /> },
  { pattern: /^\/insights$/, render: () => <Insights /> },
];

