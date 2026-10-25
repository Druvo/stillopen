/** Small, framework-free helpers for keyboard and screen reader behaviour, so the logic can be tested without a browser layout. */

const FOCUSABLE = 'a[href], button, input:not([type="hidden"]), select, textarea, summary, [tabindex]';

/** The elements inside `root` that the Tab key can reach, in order. */
export function focusableIn(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => {
    if (el.tabIndex < 0 || (el as HTMLButtonElement).disabled) return false;
    return !el.closest("[hidden], [inert]");
  });
}

/**
 * Where Tab should go in a focus trap: the index to move to, or null when the browser's own step stays inside.
 * `current` is the index of the focused element, or -1 when focus is outside the trap.
 */
export function nextTrapIndex(count: number, current: number, shift: boolean): number | null {
  if (count === 0) return -1;
  if (current < 0) return shift ? count - 1 : 0;
  if (!shift && current === count - 1) return 0;
  if (shift && current === 0) return count - 1;
  return null;
}

/** Keeps Tab and Shift+Tab inside `root`. Returns true when it handled the key. */
export function trapTab(event: { key: string; shiftKey: boolean; preventDefault: () => void }, root: HTMLElement): boolean {
  if (event.key !== "Tab") return false;
  const items = focusableIn(root);
  const active = typeof document === "undefined" ? null : document.activeElement;
  const target = nextTrapIndex(items.length, active ? items.indexOf(active as HTMLElement) : -1, event.shiftKey);
  if (target === null) return false;
  event.preventDefault();
  items[target]?.focus();
  return true;
}

/** The first heading of a screen, as plain text; "" while the screen is still loading. */
export function firstHeading(root: ParentNode | null): string {
  return root?.querySelector("h1")?.textContent?.replace(/\s+/g, " ").trim() ?? "";
}

/** "Add a job - StillOpen": the screen's own name first, so a tab or a history entry says where you are. */
export function screenTitle(heading: string | null | undefined, site: string): string {
  const name = (heading ?? "").trim();
  return name && name !== site ? `${name} - ${site}` : site;
}

/** What is said after a refused form. */
export function problemsText(count: number): string {
  return count === 1 ? "1 problem to fix" : `${count} problems to fix`;
}

/** Joins the ids of the elements that describe a control, leaving out the ones that are not there. */
export function describedBy(...ids: (string | false | null | undefined)[]): string | undefined {
  const used = ids.filter(Boolean).join(" ");
  return used || undefined;
}
