"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, LogOut, Menu, Moon, PanelLeftClose, PanelLeftOpen, Search, Settings, ShieldCheck, Sun, UserRound, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { csrfToken, request } from "@/lib/api";
import { Link, matchRoute, navigate, useAppPath } from "@/lib/router";
import { Toasts } from "@/lib/toast";
import { cn } from "@/lib/utils";
import { NAV, ROUTES } from "@/routes";
import { Loading, PageHeader } from "./ui";

// The layout (fixed sidebar that collapses on wide screens and slides in on small ones, a sticky header with search, theme
// switch and a user menu) follows TailAdmin free Next.js dashboard, MIT. See frontend/THIRD_PARTY.md.

const SIDEBAR_KEY = "so-sidebar";

function toggleTheme() {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem("so-theme", next);
  } catch {
    /* private window: the choice just is not remembered */
  }
}

/** The sidebar entry for the current path: the longest entry that is the path or a parent of it (so /profile/ai lights "AI settings", not "Profile"). */
export function currentEntry(path: string, entries: string[]): string | undefined {
  return entries
    .filter((to) => (to === "/" ? path === "/" : path === to || path.startsWith(`${to}/`)))
    .sort((a, b) => b.length - a.length)[0];
}

type Me = { id: number; name: string; email: string; is_staff: boolean; site_title?: string; prep_enabled?: boolean; assistant_enabled?: boolean };

function initials(me?: Me) {
  const source = me?.name || me?.email || "?";
  return source.trim().slice(0, 1).toUpperCase();
}

function UserMenu({ me }: { me?: Me }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  const item = "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-theme-sm font-medium text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/5";
  return (
    <div className="relative" ref={box}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Your account"
        className="flex items-center gap-3 rounded-lg p-1 text-gray-700 dark:text-gray-400"
      >
        <span className="flex size-10 items-center justify-center rounded-full bg-brand-50 text-theme-sm font-semibold text-brand-500 dark:bg-brand-500/15 dark:text-brand-400" aria-hidden>
          {initials(me)}
        </span>
        <span className="hidden max-w-32 truncate text-theme-sm font-medium sm:block">{me?.name || "Account"}</span>
        <ChevronDown className={cn("hidden size-4 transition-transform sm:block", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-50 mt-3 w-64 rounded-2xl border border-gray-200 bg-white p-3 shadow-theme-lg dark:border-gray-800 dark:bg-gray-900">
          <div className="border-b border-gray-200 px-3 pb-3 dark:border-gray-800">
            <p className="text-theme-sm font-medium text-gray-700 dark:text-gray-200">{me?.name}</p>
            <p className="truncate text-theme-xs text-gray-500 dark:text-gray-400">{me?.email}</p>
          </div>
          <ul className="mt-2 space-y-0.5">
            <li>
              <Link to="/profile" role="menuitem" onClick={() => setOpen(false)} className={item}>
                <UserRound className="size-4 text-gray-500" aria-hidden /> Your profile
              </Link>
            </li>
            <li>
              <Link to="/profile/ai" role="menuitem" onClick={() => setOpen(false)} className={item}>
                <Settings className="size-4 text-gray-500" aria-hidden /> AI settings
              </Link>
            </li>
            {me?.is_staff && (
              <li>
                <a href="/admin/" role="menuitem" className={item}>
                  <ShieldCheck className="size-4 text-gray-500" aria-hidden /> Admin
                </a>
              </li>
            )}
          </ul>
          <form
            method="post"
            action="/accounts/logout/"
            className="mt-2 border-t border-gray-200 pt-2 dark:border-gray-800"
            onSubmit={(event) => {
              const field = event.currentTarget.elements.namedItem("csrfmiddlewaretoken") as HTMLInputElement | null;
              if (field) field.value = csrfToken();
            }}
          >
            <input type="hidden" name="csrfmiddlewaretoken" defaultValue="" />
            <button type="submit" role="menuitem" className={item}>
              <LogOut className="size-4 text-gray-500" aria-hidden /> Sign out
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

function SearchBox() {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        input.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
  return (
    <form
      role="search"
      className="hidden md:block"
      onSubmit={(e) => {
        e.preventDefault();
        const q = input.current?.value.trim() ?? "";
        navigate(q ? `/?q=${encodeURIComponent(q)}` : "/");
        window.dispatchEvent(new CustomEvent("so-search", { detail: q }));
      }}
    >
      <div className="relative">
        <Search className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-gray-500 dark:text-gray-400" aria-hidden />
        <input
          ref={input}
          type="search"
          aria-label="Search your jobs"
          placeholder="Search your jobs…"
          className="h-11 w-full rounded-lg border border-gray-200 bg-transparent py-2.5 pl-12 pr-14 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:ring-3 focus:ring-brand-500/10 focus:outline-hidden lg:w-80 xl:w-105 dark:border-gray-800 dark:bg-white/3 dark:text-white/90 dark:placeholder:text-white/30"
        />
        <kbd className="absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded-lg border border-gray-200 bg-gray-50 px-1.5 py-1 text-xs text-gray-500 lg:inline-flex dark:border-gray-800 dark:bg-white/3 dark:text-gray-400">⌘ K</kbd>
      </div>
    </form>
  );
}

export function AppShell() {
  const path = useAppPath();
  const screen = path === null ? null : matchRoute(ROUTES, path);
  const me = useQuery({ queryKey: ["me"], queryFn: () => request<Me>("GET", "/me"), staleTime: 5 * 60_000 });
  const [expanded, setExpanded] = useState(true);
  const [hovered, setHovered] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    try {
      if (localStorage.getItem(SIDEBAR_KEY) === "collapsed") setExpanded(false);
    } catch {
      /* not remembered */
    }
  }, []);
  useEffect(() => setMobileOpen(false), [path]); // a tap on a link closes the drawer
  useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMobileOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [mobileOpen]);

  const title = me.data?.site_title || "StillOpen";
  const wide = expanded || hovered || mobileOpen;
  // Entries the admin switched off (prep plans, the assistant) leave the menu; until /me has answered, everything shows.
  const nav = NAV.map((g) => ({ ...g, items: g.items.filter((i) => !i.needs || me.data?.[i.needs] !== false) }));
  const flat = nav.flatMap((g) => g.items.map((i) => i.to));
  const active = path === null ? undefined : currentEntry(path, flat);

  const toggleSidebar = () => {
    if (window.matchMedia("(min-width: 1280px)").matches) {
      const next = !expanded;
      setExpanded(next);
      try {
        localStorage.setItem(SIDEBAR_KEY, next ? "expanded" : "collapsed");
      } catch {
        /* not remembered */
      }
    } else {
      setMobileOpen((v) => !v);
    }
  };

  return (
    <div className="min-h-screen xl:flex">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[100] focus:rounded-lg focus:bg-brand-500 focus:px-4 focus:py-2 focus:text-white">
        Skip to the page
      </a>

      <aside
        aria-label="Sidebar"
        onMouseEnter={() => !expanded && setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        className={cn(
          "fixed left-0 top-0 z-50 flex h-screen flex-col border-r border-gray-200 bg-white px-5 transition-all duration-300 ease-in-out dark:border-gray-800 dark:bg-gray-900",
          wide ? "w-72.5" : "w-22.5",
          mobileOpen ? "translate-x-0" : "-translate-x-full xl:translate-x-0",
        )}
      >
        <div className={cn("flex h-16 items-center py-8", !wide && "justify-center")}>
          <Link to="/" className="flex items-center gap-2 text-xl font-semibold tracking-tight text-gray-800 dark:text-white/90">
            <span className="flex size-9 items-center justify-center rounded-lg bg-brand-500 text-white" aria-hidden>
              S
            </span>
            {wide && <span>{title}</span>}
          </Link>
        </div>
        <nav aria-label="Main" className="no-scrollbar flex-1 overflow-y-auto pb-6">
          {nav.map((group) => (
            <div key={group.title} className="mb-6">
              <h2 className={cn("mb-3 flex text-xs uppercase leading-5 text-gray-400", !wide && "justify-center")}>{wide ? group.title : "···"}</h2>
              <ul className="space-y-1">
                {group.items.map(({ label, to, icon: Icon }) => {
                  const current = active === to;
                  return (
                    <li key={to}>
                      <Link
                        to={to}
                        aria-current={current ? "page" : undefined}
                        title={wide ? undefined : label}
                        className={cn("menu-item", current ? "menu-item-active" : "menu-item-inactive", !wide && "justify-center")}
                      >
                        <Icon className={cn("size-5 shrink-0", current ? "text-brand-500 dark:text-brand-400" : "text-gray-500 dark:text-gray-400")} aria-hidden />
                        {wide ? <span>{label}</span> : <span className="sr-only">{label}</span>}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>
      </aside>
      {mobileOpen && <div className="fixed inset-0 z-40 bg-gray-900/50 xl:hidden" onClick={() => setMobileOpen(false)} aria-hidden />}

      <div className={cn("min-w-0 flex-1 transition-all duration-300 ease-in-out", expanded ? "xl:ml-72.5" : "xl:ml-22.5")}>
        <header className="sticky top-0 z-40 flex h-16 w-full items-center gap-3 border-b border-gray-200 bg-white px-3 sm:px-4 xl:px-6 dark:border-gray-800 dark:bg-gray-900">
          <button
            type="button"
            onClick={toggleSidebar}
            aria-label={mobileOpen ? "Close the menu" : "Open or collapse the menu"}
            aria-expanded={mobileOpen}
            className="flex size-10 items-center justify-center rounded-lg border-gray-200 text-gray-500 hover:bg-gray-100 xl:size-11 xl:border dark:border-gray-800 dark:text-gray-400 dark:hover:bg-white/5"
          >
            {mobileOpen ? <X className="size-5" aria-hidden /> : <Menu className="size-5 xl:hidden" aria-hidden />}
            {!mobileOpen && (expanded ? <PanelLeftClose className="hidden size-5 xl:block" aria-hidden /> : <PanelLeftOpen className="hidden size-5 xl:block" aria-hidden />)}
          </button>
          <Link to="/" className="text-lg font-semibold tracking-tight text-gray-800 xl:hidden dark:text-white/90">
            {title}
          </Link>
          <SearchBox />
          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <button
              type="button"
              onClick={toggleTheme}
              aria-label="Switch between light and dark"
              className="flex size-10 items-center justify-center rounded-full border border-gray-200 text-gray-500 hover:bg-gray-100 hover:text-gray-700 xl:size-11 dark:border-gray-800 dark:text-gray-400 dark:hover:bg-white/5"
            >
              <Sun className="hidden size-5 dark:block" aria-hidden />
              <Moon className="size-5 dark:hidden" aria-hidden />
            </button>
            <UserMenu me={me.data} />
          </div>
        </header>

        <main id="main" className="mx-auto max-w-(--breakpoint-2xl) p-4 md:p-6">
          {path === null ? (
            <Loading />
          ) : (
            screen ?? (
              <>
                <PageHeader title="We could not find that page" />
                <Link to="/" className="text-brand underline">
                  Back to your dashboard
                </Link>
              </>
            )
          )}
        </main>
      </div>
      <Toasts />
    </div>
  );
}
