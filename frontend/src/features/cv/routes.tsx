"use client";

import type { Route } from "@/lib/router";
import { CoverDetail, CvDetail, CvDiff, CvList } from "./screens";

/** The screens of this area, matched against the path inside the app (no /app prefix). Add a screen = add a line here. */
export const ROUTES: Route[] = [
  { pattern: /^\/cv$/, render: () => <CvList /> },
  { pattern: /^\/cv\/(\d+)$/, render: ([id]) => <CvDetail key={id} id={Number(id)} /> },
  { pattern: /^\/cv\/(\d+)\/diff$/, render: ([id]) => <CvDiff key={id} id={Number(id)} /> },
  { pattern: /^\/cover\/(\d+)$/, render: ([id]) => <CoverDetail key={id} id={Number(id)} /> },
];

