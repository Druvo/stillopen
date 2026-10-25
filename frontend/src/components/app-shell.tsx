"use client";

import { Moon, Sun } from "lucide-react";
import { Dashboard } from "@/features/dashboard/dashboard";

// Screens that have not moved yet stay on the classic pages, so nothing is lost mid-migration.
const CLASSIC_LINKS: [string, string][] = [
  ["Add job", "/jobs/add/"],
  ["All postings", "/postings/"],
  ["Job sources", "/sources/"],
  ["Interviews", "/interviews/"],
  ["Contacts", "/contacts/"],
  ["Offers", "/offers/"],
  ["Prep plans", "/prep/"],
  ["Insights", "/insights/"],
  ["CVs", "/cv/"],
  ["Documents", "/knowledge/"],
  ["Profile", "/profile/"],
  ["AI settings", "/profile/ai/"],
];

function toggleTheme() {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem("stillopen-theme", next);
  } catch {
    /* private window: the choice just is not remembered */
  }
}

export function AppShell() {
  return (
    <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col lg:flex-row">
      <aside className="border-b border-border bg-surface lg:w-56 lg:shrink-0 lg:border-r lg:border-b-0">
        <div className="flex items-center justify-between gap-2 px-4 py-3 lg:block lg:py-5">
          <a href="/app/" className="text-lg font-semibold tracking-tight">
            StillOpen
          </a>
          <button
            type="button"
            onClick={toggleTheme}
            aria-label="Switch between light and dark"
            className="rounded-md p-2 text-muted hover:bg-surface-2 lg:mt-3 lg:flex lg:items-center lg:gap-2"
          >
            <Sun className="hidden size-4 dark:block" aria-hidden />
            <Moon className="size-4 dark:hidden" aria-hidden />
            <span className="hidden text-sm lg:inline">Light or dark</span>
          </button>
        </div>
        <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-3 pb-3 lg:block lg:overflow-visible lg:pb-5">
          <a href="/app/" aria-current="page" className="block shrink-0 rounded-md bg-surface-2 px-3 py-2 text-sm font-medium">
            Dashboard
          </a>
          {CLASSIC_LINKS.map(([label, href]) => (
            <a key={href} href={href} className="block shrink-0 rounded-md px-3 py-2 text-sm text-muted hover:bg-surface-2 hover:text-fg">
              {label}
            </a>
          ))}
          <a href="/dashboard/?classic=1" className="mt-2 block shrink-0 rounded-md px-3 py-2 text-sm text-muted hover:bg-surface-2 hover:text-fg">
            Back to the classic view
          </a>
        </nav>
      </aside>
      <main className="min-w-0 flex-1 px-4 py-5 lg:px-8">
        <Dashboard />
      </main>
    </div>
  );
}
