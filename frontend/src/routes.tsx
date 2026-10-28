"use client";

import { Dashboard } from "@/features/dashboard/dashboard";
import { BadgeDollarSign, BarChart3, Bot, CalendarClock, FileText, FolderOpen, GraduationCap, HelpCircle, LayoutDashboard, Search, PlusCircle, Radar, Sparkles, UserRound, Users, type LucideIcon } from "lucide-react";
import { lazy } from "react";
import type { Route } from "@/lib/router";
import * as account from "@/features/account/routes";
import * as cv from "@/features/cv/routes";
import * as help from "@/features/help/routes";
import * as jobs from "@/features/jobs/routes";
import * as notifications from "@/features/notifications/routes";
import * as pipeline from "@/features/pipeline/routes";

// The dashboard is what /app/ opens, so it comes with the first load. Every other screen is its own chunk, fetched when it is opened.
const PrepList = lazy(() => import("@/features/prep/screens").then((m) => ({ default: m.PrepList })));
const PrepPlan = lazy(() => import("@/features/prep/screens").then((m) => ({ default: m.PrepPlan })));
const PrepToday = lazy(() => import("@/features/prep/screens").then((m) => ({ default: m.PrepToday })));

/** Every screen of the app, matched against the path inside it (no /app prefix). */
export const ROUTES: Route[] = [
  { pattern: /^\/$/, render: () => <Dashboard /> },
  { pattern: /^\/prep$/, render: () => <PrepList /> },
  { pattern: /^\/prep\/(\d+)$/, render: ([id]) => <PrepPlan key={id} id={Number(id)} /> },
  { pattern: /^\/prep\/(\d+)\/today$/, render: ([id]) => <PrepToday key={id} id={Number(id)} /> },
  ...jobs.ROUTES,
  ...cv.ROUTES,
  ...pipeline.ROUTES,
  ...account.ROUTES,
  ...notifications.ROUTES,
  ...help.ROUTES,
];

export type NavItem = { label: string; to: string; icon: LucideIcon; needs?: "prep_enabled" | "assistant_enabled" };
export type NavGroup = { title: string; items: NavItem[] };

/** The sidebar. Every entry is a screen of this app. */
export const NAV: NavGroup[] = [
  {
    title: "Job search",
    items: [
      { label: "Dashboard", to: "/", icon: LayoutDashboard },
      { label: "Add job", to: "/jobs/add", icon: PlusCircle },
      { label: "All postings", to: "/postings", icon: Search },
      { label: "Prep plans", to: "/prep", icon: GraduationCap, needs: "prep_enabled" },
    ],
  },
  {
    title: "After you apply",
    items: [
      { label: "Interviews", to: "/interviews", icon: CalendarClock },
      { label: "Contacts", to: "/contacts", icon: Users },
      { label: "Offers", to: "/offers", icon: BadgeDollarSign },
      { label: "Insights", to: "/insights", icon: BarChart3 },
    ],
  },
  {
    title: "About you",
    items: [
      { label: "CVs", to: "/cv", icon: FileText },
      { label: "Documents", to: "/knowledge", icon: FolderOpen },
      { label: "Profile", to: "/profile", icon: UserRound },
      { label: "AI settings", to: "/profile/ai", icon: Sparkles },
      { label: "Job sources", to: "/sources", icon: Radar },
      { label: "Assistant", to: "/profile/assistant", icon: Bot, needs: "assistant_enabled" },
      { label: "Help", to: "/help", icon: HelpCircle },
    ],
  },
];
