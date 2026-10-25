"use client";

import { ChevronDown, Loader2, MoreHorizontal } from "lucide-react";
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "@/lib/router";
import { cn } from "@/lib/utils";

export type MenuItem = {
  key: string;
  label: string;
  /** A screen of this app. */
  to?: string;
  /** Another address; opens in a new tab. */
  href?: string;
  onSelect?: () => void;
  disabled?: boolean;
};

const ITEM = "flex min-h-11 w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-theme-sm text-gray-700 hover:bg-gray-100 focus-visible:bg-gray-100 sm:min-h-9 dark:text-gray-300 dark:hover:bg-white/5 dark:focus-visible:bg-white/5";

/**
 * A button that opens a short list of actions. The list is drawn over the page (not inside the card), so a scrolling board never clips it.
 * Keyboard: Enter or the Down arrow opens it, the arrow keys, Home and End move, Escape closes and returns to the button, Tab closes.
 */
export function ActionMenu({ label, text = "More", items, busy = false, variant = "dots", className }: { label: string; text?: string; items: MenuItem[]; busy?: boolean; variant?: "dots" | "chevron"; className?: string }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; right: number } | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const id = useId();
  const close = useCallback((returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) trigger.current?.focus();
  }, []);

  const place = useCallback(() => {
    if (!trigger.current) return false;
    const rect = trigger.current.getBoundingClientRect();
    if (rect.bottom < 0 || rect.top > window.innerHeight) return false; // the button has scrolled out of sight
    const height = panel.current?.offsetHeight ?? 0;
    const below = rect.bottom + 4;
    const top = below + height > window.innerHeight && rect.top - 4 - height > 0 ? rect.top - 4 - height : below;
    setPos({ top, right: Math.max(8, window.innerWidth - rect.right) });
    return true;
  }, []);

  useLayoutEffect(() => {
    if (open) place();
  }, [open, items.length, place]);

  useEffect(() => {
    if (!open) {
      setPos(null);
      return;
    }
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!panel.current?.contains(t) && !trigger.current?.contains(t)) setOpen(false);
    };
    // The list is drawn at a fixed spot: when the page moves under it, it follows its button, and closes if the button leaves the screen.
    const follow = () => {
      if (!place()) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    window.addEventListener("resize", follow);
    window.addEventListener("scroll", follow, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("resize", follow);
      window.removeEventListener("scroll", follow, true);
    };
  }, [open, place]);

  const placed = pos !== null;
  useEffect(() => {
    // Focus moves into the list once it is on the screen (a hidden element cannot take focus).
    if (open && placed) panel.current?.querySelector<HTMLElement>('[role="menuitem"]:not([aria-disabled="true"])')?.focus({ preventScroll: true });
  }, [open, placed]);

  const onPanelKey = (e: React.KeyboardEvent) => {
    const all = [...(panel.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([aria-disabled="true"])') ?? [])];
    const at = all.indexOf(document.activeElement as HTMLElement);
    const go = (i: number) => {
      e.preventDefault();
      all[(i + all.length) % all.length]?.focus({ preventScroll: true });
    };
    if (e.key === "ArrowDown") go(at + 1);
    else if (e.key === "ArrowUp") go(at - 1);
    else if (e.key === "Home") go(0);
    else if (e.key === "End") go(all.length - 1);
    else if (e.key === "Escape") {
      e.preventDefault();
      close(true);
    } else if (e.key === "Tab") setOpen(false);
  };

  if (items.length === 0) return null;
  return (
    <>
      <button
        ref={trigger}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        aria-label={label}
        aria-busy={busy || undefined}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" && !open) {
            e.preventDefault();
            setOpen(true);
          }
        }}
        className={cn(
          "inline-flex min-h-11 items-center justify-center gap-1 rounded-lg border border-border bg-surface px-3 py-1.5 text-theme-sm font-medium hover:bg-surface-2 sm:min-h-9",
          className,
        )}
      >
        {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : variant === "dots" ? <MoreHorizontal className="size-4" aria-hidden /> : null}
        <span>{text}</span>
        {variant === "chevron" && <ChevronDown className="size-4" aria-hidden />}
      </button>
      {open &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            ref={panel}
            id={id}
            role="menu"
            aria-label={label}
            onKeyDown={onPanelKey}
            style={{ position: "fixed", top: pos?.top ?? 0, right: pos?.right ?? 8, visibility: pos ? "visible" : "hidden" }}
            className="z-[90] min-w-52 max-w-[calc(100vw-1rem)] rounded-xl border border-gray-200 bg-white p-1.5 shadow-theme-lg dark:border-gray-800 dark:bg-gray-900"
          >
            {items.map((item) => {
              const common = { role: "menuitem", tabIndex: -1, className: cn(ITEM, item.disabled && "pointer-events-none opacity-50"), "aria-disabled": item.disabled || undefined };
              if (item.to)
                return (
                  <Link key={item.key} to={item.to} {...common} onClick={() => setOpen(false)}>
                    {item.label}
                  </Link>
                );
              if (item.href)
                return (
                  <a key={item.key} href={item.href} target="_blank" rel="noopener noreferrer" {...common} onClick={() => setOpen(false)}>
                    {item.label}
                  </a>
                );
              return (
                <button
                  key={item.key}
                  type="button"
                  {...common}
                  disabled={item.disabled}
                  onClick={() => {
                    close(true);
                    item.onSelect?.();
                  }}
                >
                  {item.label}
                </button>
              );
            })}
          </div>,
          document.body,
        )}
    </>
  );
}
