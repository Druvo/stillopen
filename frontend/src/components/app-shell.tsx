"use client";

import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { Bell, ChevronDown, HelpCircle, Keyboard, Loader2, LogOut, Menu, Moon, PanelLeftClose, PanelLeftOpen, Search, Settings, ShieldCheck, Sun, UserRound, X } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useId, useRef, useState } from "react";
import { focusableIn, trapTab } from "@/lib/a11y";
import { csrfToken } from "@/lib/api";
import { useMe } from "@/lib/me";
import { applyDisplay } from "@/lib/preferences";
import { readKey } from "@/lib/palette";
import { clearPersistedStorage, tabStorage } from "@/lib/persist";
import { useFlushPreferencesOnLeave, usePreferences } from "@/lib/use-preferences";
import type { Me } from "@/lib/types";
import { Link, matchRoute, navigate, useAppPath } from "@/lib/router";
import { useScreenAnnouncer } from "@/lib/screen";
import { Toasts } from "@/lib/toast";
import { useIsWide } from "@/lib/use-media";
import { cn } from "@/lib/utils";
import { NAV, ROUTES } from "@/routes";
import { ScreenBoundary } from "./screen-boundary";
import { NotificationBell } from "@/features/notifications/bell";
import { Loading, PageHeader, ScreenSkeleton } from "./ui";

const loadOverlays = () => import("./overlays");
const CommandPalette = lazy(() => loadOverlays().then((m) => ({ default: m.CommandPalette })));
const ShortcutsDialog = lazy(() => loadOverlays().then((m) => ({ default: m.ShortcutsDialog })));
type Overlay = "palette" | "shortcuts" | null;

// The layout (fixed sidebar that collapses on wide screens and slides in on small ones, a sticky header with search, theme
// switch and a user menu) follows TailAdmin free Next.js dashboard, MIT. See frontend/THIRD_PARTY.md.

/** The sidebar entry for the current path: the longest entry that is the path or a parent of it (so /profile/ai lights "AI settings", not "Profile"). */
export function currentEntry(path: string, entries: string[]): string | undefined {
  return entries
    .filter((to) => (to === "/" ? path === "/" : path === to || path.startsWith(`${to}/`)))
    .sort((a, b) => b.length - a.length)[0];
}

function initials(me?: Me) {
  const source = me?.name || me?.email || "?";
  return source.trim().slice(0, 1).toUpperCase();
}

function UserMenu({ me, onShortcuts }: { me?: Me; onShortcuts: () => void }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const byKeyboard = useRef(false);
  const panelId = useId();
  const close = (returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) button.current?.focus();
  };
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);
  useEffect(() => {
    // Opened with the keyboard: the first entry is where the person goes next.
    if (open && byKeyboard.current) panel.current?.querySelector<HTMLElement>("a, button")?.focus();
    byKeyboard.current = false;
  }, [open]);
  const item = "flex min-h-11 w-full items-center gap-3 rounded-lg px-3 py-2 text-theme-sm font-medium text-gray-700 hover:bg-gray-100 sm:min-h-9 dark:text-gray-300 dark:hover:bg-white/5";
  return (
    <div
      className="relative"
      ref={box}
      onKeyDown={(e) => {
        if (open && e.key === "Escape") {
          e.preventDefault();
          close(true);
        }
      }}
      onBlur={(e) => {
        // Tabbing out of the open panel closes it; a click on something that cannot take focus has no next element and does not.
        const next = e.relatedTarget as Node | null;
        if (open && next && !box.current?.contains(next)) setOpen(false);
      }}
    >
      <button
        ref={button}
        type="button"
        onClick={(e) => {
          byKeyboard.current = e.detail === 0;
          setOpen((v) => !v);
        }}
        aria-expanded={open}
        aria-controls={panelId}
        aria-label="Your account"
        className="flex min-h-11 min-w-11 items-center gap-3 rounded-lg p-1 text-gray-700 dark:text-gray-400"
      >
        <span className="flex size-10 items-center justify-center rounded-full bg-brand-50 text-theme-sm font-semibold text-brand-600 dark:bg-brand-500/15 dark:text-brand-400" aria-hidden>
          {initials(me)}
        </span>
        <span className="hidden max-w-32 truncate text-theme-sm font-medium sm:block">{me?.name || "Account"}</span>
        <ChevronDown className={cn("hidden size-4 transition-transform sm:block", open && "rotate-180")} aria-hidden />
      </button>
      <div ref={panel} id={panelId} hidden={!open} className="absolute right-0 z-50 mt-3 w-64 rounded-2xl border border-gray-200 bg-white p-3 shadow-theme-lg dark:border-gray-800 dark:bg-gray-900">
        <div className="border-b border-gray-200 px-3 pb-3 dark:border-gray-800">
          <p className="text-theme-sm font-medium text-gray-700 dark:text-gray-200">{me?.name}</p>
          <p className="truncate text-theme-xs text-gray-500 dark:text-gray-400">{me?.email}</p>
        </div>
        <ul className="mt-2 space-y-0.5">
          <li>
            <Link to="/profile" onClick={() => setOpen(false)} className={item}>
              <UserRound className="size-4 text-gray-500" aria-hidden /> Your profile
            </Link>
          </li>
          <li>
            <Link to="/profile/ai" onClick={() => setOpen(false)} className={item}>
              <Settings className="size-4 text-gray-500" aria-hidden /> AI settings
            </Link>
          </li>
          <li>
            <Link to="/notifications" onClick={() => setOpen(false)} className={item}>
              <Bell className="size-4 text-gray-500" aria-hidden /> Notifications
            </Link>
          </li>
          <li>
            <Link to="/help" onClick={() => setOpen(false)} className={item}>
              <HelpCircle className="size-4 text-gray-500" aria-hidden /> Help
            </Link>
          </li>
          <li>
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                onShortcuts();
              }}
              className={item}
            >
              <Keyboard className="size-4 text-gray-500" aria-hidden /> Keyboard shortcuts
            </button>
          </li>
          {me?.is_staff && (
            <li>
              <a href="/admin/" className={item}>
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
            // Signing out ends this person's session: nothing of their data stays in this tab's cache.
            client.clear();
            clearPersistedStorage(tabStorage());
            const field = event.currentTarget.elements.namedItem("csrfmiddlewaretoken") as HTMLInputElement | null;
            if (field) field.value = csrfToken();
          }}
        >
          <input type="hidden" name="csrfmiddlewaretoken" defaultValue="" />
          <button type="submit" className={item}>
            <LogOut className="size-4 text-gray-500" aria-hidden /> Sign out
          </button>
        </form>
      </div>
    </div>
  );
}

function SearchBox() {
  const input = useRef<HTMLInputElement>(null);
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
          className="h-11 w-full rounded-lg border border-gray-200 bg-transparent py-2.5 pl-12 pr-14 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-500 focus:border-brand-500 lg:w-80 xl:w-105 dark:border-gray-800 dark:bg-white/3 dark:text-white/90 dark:placeholder:text-white/50"
        />
        <kbd aria-hidden title="Press / or Ctrl K to jump to any screen" className="absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded-lg border border-gray-200 bg-gray-50 px-1.5 py-1 text-xs text-gray-500 lg:inline-flex dark:border-gray-800 dark:bg-white/3 dark:text-gray-400">⌘ K</kbd>
      </div>
    </form>
  );
}

/** A quiet "Updating…" while answers are being refreshed behind what is already on the screen. Waits a moment so quick refreshes do not flicker. */
function UpdatingNote() {
  const busy = useIsFetching() > 0;
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (!busy) {
      setShow(false);
      return;
    }
    const t = window.setTimeout(() => setShow(true), 400);
    return () => window.clearTimeout(t);
  }, [busy]);
  if (!show) return null;
  return (
    <span className="hidden items-center gap-1.5 text-theme-xs text-muted sm:inline-flex" title="Fetching the latest in the background">
      <Loader2 className="size-3.5 animate-spin" aria-hidden /> Updating…
    </span>
  );
}

export function AppShell() {
  const path = useAppPath();
  const screen = path === null ? null : matchRoute(ROUTES, path);
  const me = useMe();
  const { prefs, update, known } = usePreferences();
  const [hovered, setHovered] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [overlay, setOverlay] = useState<Overlay>(null);
  const closeOverlay = useCallback(() => setOverlay(null), []);
  const isWide = useIsWide();
  const expanded = prefs.sidebar === "expanded";
  const aside = useRef<HTMLElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const main = useRef<HTMLElement>(null);
  const returnFocus = useRef(false);
  const sidebarId = useId();
  useFlushPreferencesOnLeave();

  // On a phone the menu is a drawer: a modal dialog while it is open. On a wide screen it is a plain sidebar and nothing is shut off.
  const drawer = mobileOpen && !isWide;
  const closeDrawer = (andFocusButton = true) => {
    returnFocus.current = andFocusButton;
    setMobileOpen(false);
  };

  // Colour mode, text size and density go on <html>; the browser's copy is kept so the next first paint is right.
  useEffect(() => {
    if (known) applyDisplay(prefs);
  }, [known, prefs.theme, prefs.text_size, prefs.density, prefs.sidebar]); // eslint-disable-line react-hooks/exhaustive-deps

  // A tap on a link closes the drawer. Done while rendering (not in an effect), so the page is no longer shut off when the screen
  // announcer moves focus to the new screen.
  const [seenPath, setSeenPath] = useState(path);
  if (seenPath !== path) {
    setSeenPath(path);
    setMobileOpen(false);
  }

  useEffect(() => {
    if (!drawer) {
      if (returnFocus.current) toggle.current?.focus();
      returnFocus.current = false;
      return;
    }
    // Open: focus goes to the first link in the drawer, the page behind it cannot be scrolled, and Escape closes it.
    if (aside.current) focusableIn(aside.current)[0]?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        closeDrawer();
      }
    };
    const scroll = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = scroll;
    };
  }, [drawer]);

  // Fetched a moment after the page is up (not part of the first load), so the first keys typed after "/" are not lost to a download.
  useEffect(() => {
    const t = window.setTimeout(() => void loadOverlays(), 1500);
    return () => window.clearTimeout(t);
  }, []);

  // Shortcuts: / or Ctrl/Cmd+K jumps, ? lists them, "g" then a letter goes to a screen. Never while typing in a field or with a dialog open.
  const overlayOpen = overlay !== null;
  useEffect(() => {
    let waiting = false;
    let timer = 0;
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      const step = readKey(e, waiting, overlayOpen || drawer);
      waiting = false;
      window.clearTimeout(timer);
      if (!step) return;
      e.preventDefault();
      if (step.open) setOverlay(step.open);
      else if (step.go) navigate(step.go);
      else if (step.waitForGo) {
        waiting = true;
        timer = window.setTimeout(() => (waiting = false), 1500);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.clearTimeout(timer);
    };
  }, [overlayOpen, drawer]);

  const title = me.data?.site_title || "StillOpen";
  useScreenAnnouncer(main, path, title);
  const wide = expanded || hovered || drawer;
  // Entries the admin switched off (prep plans, the assistant) leave the menu; until /me has answered, everything shows.
  const nav = NAV.map((g) => ({ ...g, items: g.items.filter((i) => !i.needs || me.data?.[i.needs] !== false) }));
  const flat = nav.flatMap((g) => g.items.map((i) => i.to));
  const active = path === null ? undefined : currentEntry(path, flat);

  const toggleSidebar = () => {
    if (isWide) update({ sidebar: expanded ? "collapsed" : "expanded" });
    else setMobileOpen((v) => !v);
  };

  return (
    <div className="min-h-screen xl:flex">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[100] focus:rounded-lg focus:bg-brand-600 focus:px-4 focus:py-2 focus:text-white">
        Skip to the page
      </a>

      <aside
        ref={aside}
        id={sidebarId}
        role={drawer ? "dialog" : undefined}
        aria-modal={drawer || undefined}
        aria-label={drawer ? "Menu" : "Sidebar"}
        onKeyDown={drawer ? (e) => aside.current && trapTab(e, aside.current) : undefined}
        onMouseEnter={() => !expanded && setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        className={cn(
          "fixed left-0 top-0 z-50 flex h-screen flex-col border-r border-gray-200 bg-white px-5 transition-[width,transform] duration-300 ease-in-out dark:border-gray-800 dark:bg-gray-900",
          wide ? "w-72.5" : "w-22.5",
          drawer ? "translate-x-0" : "-translate-x-full max-xl:invisible xl:translate-x-0",
        )}
      >
        <div className={cn("flex h-16 items-center py-8", !wide && "justify-center")}>
          <Link to="/" className="flex items-center gap-2 text-xl font-semibold tracking-tight text-gray-800 dark:text-white/90">
            <span className="flex size-9 items-center justify-center rounded-lg bg-brand-600 text-white" aria-hidden>
              S
            </span>
            {wide && <span>{title}</span>}
          </Link>
          {drawer && (
            <button type="button" onClick={() => closeDrawer()} aria-label="Close the menu" className="ml-auto flex size-11 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-white/5">
              <X className="size-5" aria-hidden />
            </button>
          )}
        </div>
        <nav aria-label="Main" className="no-scrollbar flex-1 overflow-y-auto pb-6">
          {nav.map((group) => (
            <div key={group.title} className="mb-6">
              {wide ? (
                <h2 className="mb-3 flex text-xs uppercase leading-5 text-gray-500 dark:text-gray-400">{group.title}</h2>
              ) : (
                <div aria-hidden className="mb-3 flex justify-center text-xs leading-5 text-gray-500 dark:text-gray-400">
                  ···
                </div>
              )}
              <ul className="space-y-1">
                {group.items.map(({ label, to, icon: Icon }) => {
                  const current = active === to;
                  return (
                    <li key={to}>
                      <Link
                        to={to}
                        aria-current={current ? "page" : undefined}
                        title={wide ? undefined : label}
                        className={cn("menu-item min-h-11 xl:min-h-9", current ? "menu-item-active" : "menu-item-inactive", !wide && "justify-center")}
                      >
                        <Icon className={cn("size-5 shrink-0", current ? "text-brand-600 dark:text-brand-400" : "text-gray-500 dark:text-gray-400")} aria-hidden />
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
      {drawer && <div className="fixed inset-0 z-40 bg-gray-900/50 xl:hidden" onClick={() => closeDrawer()} aria-hidden />}

      <div className={cn("min-w-0 flex-1 transition-all duration-300 ease-in-out", expanded ? "xl:ml-72.5" : "xl:ml-22.5")}>
        <header inert={drawer} className="sticky top-0 z-40 flex h-16 w-full items-center gap-3 border-b border-gray-200 bg-white px-3 sm:px-4 xl:px-6 dark:border-gray-800 dark:bg-gray-900">
          <button
            ref={toggle}
            type="button"
            onClick={toggleSidebar}
            aria-label={isWide ? (expanded ? "Collapse the sidebar" : "Expand the sidebar") : "Open the menu"}
            aria-expanded={isWide ? expanded : drawer}
            aria-controls={sidebarId}
            className="flex size-11 items-center justify-center rounded-lg border-gray-200 text-gray-500 hover:bg-gray-100 xl:border dark:border-gray-800 dark:text-gray-400 dark:hover:bg-white/5"
          >
            <Menu className="size-5 xl:hidden" aria-hidden />
            {expanded ? <PanelLeftClose className="hidden size-5 xl:block" aria-hidden /> : <PanelLeftOpen className="hidden size-5 xl:block" aria-hidden />}
          </button>
          <Link to="/" className="inline-flex min-h-11 items-center text-lg font-semibold tracking-tight text-gray-800 xl:hidden dark:text-white/90">
            {title}
          </Link>
          <SearchBox />
          <button
            type="button"
            onClick={() => setOverlay("palette")}
            aria-label="Search and jump to a screen"
            className="ml-auto flex size-11 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 md:hidden dark:text-gray-400 dark:hover:bg-white/5"
          >
            <Search className="size-5" aria-hidden />
          </button>
          <div className="flex items-center gap-2 max-md:ml-0 md:ml-auto sm:gap-3">
            <UpdatingNote />
            <button
              type="button"
              onClick={() => update({ theme: prefs.theme === "dark" ? "light" : "dark" })}
              aria-label="Switch between light and dark"
              className="flex size-11 items-center justify-center rounded-full border border-gray-200 text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:border-gray-800 dark:text-gray-400 dark:hover:bg-white/5"
            >
              <Sun className="hidden size-5 dark:block" aria-hidden />
              <Moon className="size-5 dark:hidden" aria-hidden />
            </button>
            <NotificationBell />
            <UserMenu me={me.data} onShortcuts={() => setOverlay("shortcuts")} />
          </div>
        </header>

        <main ref={main} id="main" tabIndex={-1} inert={drawer} className="mx-auto max-w-(--breakpoint-2xl) p-4 outline-none md:p-6">
          {path === null ? (
            <Loading />
          ) : (
            <ScreenBoundary resetKey={path}>
            <Suspense fallback={<ScreenSkeleton />}>
              {screen ?? (
                <>
                  <PageHeader title="We could not find that page" />
                  <Link to="/" className="link-target text-brand underline">
                    Back to your dashboard
                  </Link>
                </>
              )}
            </Suspense>
            </ScreenBoundary>
          )}
        </main>
      </div>
      <Suspense fallback={null}>
        {overlay === "palette" && <CommandPalette onClose={closeOverlay} />}
        {overlay === "shortcuts" && <ShortcutsDialog onClose={closeOverlay} />}
      </Suspense>
      <Toasts />
    </div>
  );
}
