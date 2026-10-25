"use client";

import { useEffect, useRef, type RefObject } from "react";
import { screenTitle } from "@/lib/a11y";
import { announce } from "@/lib/toast";

/** The dashboard's own heading is a greeting ("Good evening, Alice"), which makes a poor tab title. */
const FIXED_HEADINGS: Record<string, string> = { "/": "Dashboard" };

/** Moves the keyboard and screen reader position to the new screen: its heading if it has one yet, otherwise the main area. */
export function focusScreen(main: HTMLElement, heading: HTMLElement | null) {
  const active = document.activeElement;
  if (active && active !== main && main.contains(active)) return; // the screen already put the cursor somewhere useful (a field it wanted filled in)
  const target = heading ?? main;
  if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
  target.focus({ preventScroll: true });
}

/** The first heading that is actually showing: while a new screen loads, React keeps the old screen's content in the page, hidden. */
function shownHeading(root: HTMLElement): HTMLElement | null {
  for (const h of root.querySelectorAll<HTMLElement>("h1")) {
    if (typeof h.checkVisibility !== "function" || h.checkVisibility()) return h;
  }
  return null;
}

/**
 * Keeps `document.title` at "<screen name> - <site title>" and, after a move to another screen (not on the first load, and not when only
 * the query string or the hash changed, because `path` has neither), moves focus to the screen's heading and says its name once through
 * the shared polite live region. The name is read from the screen's own <h1>, so a screen cannot forget to set it; while a screen is still
 * loading there is no heading and the title stays the site's.
 */
export function useScreenAnnouncer(main: RefObject<HTMLElement | null>, path: string | null, site: string) {
  const last = useRef<string | null>(null);
  const pending = useRef(false);
  useEffect(() => {
    if (path === null) return;
    if (last.current !== null && last.current !== path) pending.current = true;
    last.current = path;
    const root = main.current;
    if (!root) return;
    const sync = () => {
      const heading = shownHeading(root);
      const name = FIXED_HEADINGS[path] ?? (heading?.textContent?.replace(/\s+/g, " ").trim() ?? "");
      document.title = screenTitle(name, site);
      if (pending.current && heading) {
        pending.current = false;
        focusScreen(root, heading);
        announce(name);
      }
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(root, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["style", "hidden", "class"] }); // a revealed screen changes style, not content
    // A screen that never shows a heading still gets the focus, so the person is not left on a link that is gone.
    const timer = window.setTimeout(() => {
      if (!pending.current) return;
      pending.current = false;
      focusScreen(root, null);
    }, 4000);
    return () => {
      observer.disconnect();
      window.clearTimeout(timer);
    };
  }, [main, path, site]);
}
