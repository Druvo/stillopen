"use client";

import { Moon, Sun } from "lucide-react";
import { Link, matchRoute, useAppPath } from "@/lib/router";
import { cn } from "@/lib/utils";
import { NAV, ROUTES } from "@/routes";
import { Loading, PageHeader } from "./ui";

function toggleTheme() {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem("stillopen-theme", next);
  } catch {
    /* private window: the choice just is not remembered */
  }
}

function isCurrent(path: string, to: string) {
  return to === "/" ? path === "/" : path === to || path.startsWith(`${to}/`);
}

export function AppShell() {
  const path = useAppPath();
  const screen = path === null ? null : matchRoute(ROUTES, path);
  const itemClass = (current: boolean) =>
    cn("block shrink-0 rounded-md px-3 py-2 text-sm", current ? "bg-surface-2 font-medium" : "text-muted hover:bg-surface-2 hover:text-fg");

  return (
    <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col lg:flex-row">
      <aside className="border-b border-border bg-surface lg:w-56 lg:shrink-0 lg:border-r lg:border-b-0">
        <div className="flex items-center justify-between gap-2 px-4 py-3 lg:block lg:py-5">
          <Link to="/" className="text-lg font-semibold tracking-tight">
            StillOpen
          </Link>
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
          {NAV.map(([label, to, inApp]) => {
            const current = path !== null && inApp && isCurrent(path, to);
            return inApp ? (
              <Link key={to} to={to} aria-current={current ? "page" : undefined} className={itemClass(current)}>
                {label}
              </Link>
            ) : (
              <a key={to} href={to} className={itemClass(false)}>
                {label}
              </a>
            );
          })}
          <a href="/dashboard/?classic=1" className={cn(itemClass(false), "lg:mt-2")}>
            Back to the classic view
          </a>
        </nav>
      </aside>
      <main className="min-w-0 flex-1 px-4 py-5 lg:px-8">
        {path === null ? (
          <Loading />
        ) : screen ?? (
          <>
            <PageHeader title="We could not find that page" />
            <Link to="/" className="text-brand underline">
              Back to your dashboard
            </Link>
          </>
        )}
      </main>
    </div>
  );
}
