"use client";

import { Keyboard, Search, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { trapTab } from "@/lib/a11y";
import { useMe } from "@/lib/me";
import { availableEntries, filterEntries, SHORTCUTS, type PaletteEntry } from "@/lib/palette";
import { navigate } from "@/lib/router";
import { usePreferences } from "@/lib/use-preferences";
import { requestScan } from "@/lib/scan-request";
import { cn } from "@/lib/utils";

// Loaded only when someone presses / or ? or Ctrl+K, so it adds nothing to the first load.

/** Where focus goes when a dialog closes: the thing that opened it, or the account button when that was a menu entry that has since closed. */
function giveFocusBack(opener: HTMLElement | null) {
  if (opener && opener.isConnected && opener.offsetParent !== null) opener.focus();
  else document.querySelector<HTMLElement>('button[aria-label="Your account"]')?.focus();
}

function useDialog(onClose: () => void) {
  const box = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLElement | null>(typeof document === "undefined" ? null : (document.activeElement as HTMLElement | null));
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    // Escape closes wherever focus happens to be (a page may move it while the dialog is opening).
    const onEsc = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      close.current();
    };
    document.addEventListener("keydown", onEsc);
    const scroll = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const back = opener.current;
    return () => {
      document.removeEventListener("keydown", onEsc);
      document.body.style.overflow = scroll;
      window.setTimeout(() => giveFocusBack(back), 0); // after the dialog is gone from the page
    };
  }, []);
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (box.current) trapTab(e, box.current);
  };
  return { box, onKeyDown };
}

const shade = "fixed inset-0 z-[90] flex items-start justify-center bg-gray-900/50 p-4 pt-[10vh]";
const panel = "w-full rounded-2xl border border-gray-200 bg-white shadow-theme-lg dark:border-gray-800 dark:bg-gray-900";

export function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  const { box, onKeyDown } = useDialog(onClose);
  const title = useId();
  const closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeButton.current?.focus();
  }, []);
  return (
    <div className={shade} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={box} role="dialog" aria-modal="true" aria-labelledby={title} onKeyDown={onKeyDown} className={cn(panel, "max-w-lg p-5")}>
        <div className="flex items-center gap-2">
          <Keyboard className="size-5 text-gray-500" aria-hidden />
          <h2 id={title} className="text-lg font-semibold">
            Keyboard shortcuts
          </h2>
          <button ref={closeButton} type="button" onClick={onClose} aria-label="Close" className="ml-auto flex size-11 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 sm:size-9 dark:hover:bg-white/5">
            <X className="size-5" aria-hidden />
          </button>
        </div>
        {SHORTCUTS.map((group) => (
          <section key={group.title} className="mt-3" aria-label={group.title}>
            <h3 className="text-theme-xs font-medium uppercase text-muted">{group.title}</h3>
            <dl className="mt-1 divide-y divide-gray-100 dark:divide-gray-800">
              {group.rows.map((row) => (
                <div key={row.keys.join("+")} className="flex items-center justify-between gap-3 py-1.5 text-theme-sm">
                  <dt className="flex-1">{row.text}</dt>
                  <dd className="flex gap-1">
                    {row.keys.map((k, i) => (
                      <kbd key={i} className="min-w-6 rounded-md border border-gray-200 bg-gray-50 px-1.5 py-0.5 text-center text-xs dark:border-gray-700 dark:bg-white/5">
                        {k}
                      </kbd>
                    ))}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
        <p className="mt-3 text-theme-xs text-muted">Letter shortcuts are off while you type in a field.</p>
      </div>
    </div>
  );
}

type Row = { key: string; label: string; hint: string; run: () => void };

export function CommandPalette({ onClose }: { onClose: () => void }) {
  const { box, onKeyDown } = useDialog(onClose);
  const me = useMe();
  const { prefs, update } = usePreferences();
  const [text, setText] = useState("");
  const [index, setIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();
  const title = useId();
  useEffect(() => {
    input.current?.focus();
  }, []);

  const rows = useMemo<Row[]>(() => {
    const run = (entry: PaletteEntry) => () => {
      onClose();
      if (entry.action === "scan") {
        requestScan();
        navigate("/");
      } else if (entry.action === "theme") update({ theme: prefs.theme === "dark" ? "light" : "dark" });
      else if (entry.to) navigate(entry.to);
    };
    const found = filterEntries(availableEntries(me.data), text).map((e) => ({ key: e.id, label: e.label, hint: e.group, run: run(e) }));
    const q = text.trim();
    if (!q) return found;
    const search: Row = {
      key: "search",
      label: `Search your jobs for “${q}”`,
      hint: "Search",
      run: () => {
        onClose();
        navigate(`/?q=${encodeURIComponent(q)}`);
        window.dispatchEvent(new CustomEvent("so-search", { detail: q }));
      },
    };
    return [...found, search];
  }, [me.data, text, onClose, update, prefs.theme]);
  const active = Math.min(index, Math.max(rows.length - 1, 0));
  useEffect(() => {
    document.getElementById(`${listId}-${active}`)?.scrollIntoView?.({ block: "nearest" });
  }, [active, listId]);

  return (
    <div className={shade} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={box} role="dialog" aria-modal="true" aria-labelledby={title} onKeyDown={onKeyDown} className={cn(panel, "max-w-xl overflow-hidden")}>
        <h2 id={title} className="sr-only">
          Search and jump
        </h2>
        <div className="flex items-center gap-3 border-b border-gray-200 px-4 dark:border-gray-800">
          <Search className="size-5 shrink-0 text-gray-500" aria-hidden />
          <input
            ref={input}
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={rows.length ? `${listId}-${active}` : undefined}
            aria-autocomplete="list"
            aria-label="Jump to a screen, or search your jobs"
            placeholder="Jump to a screen, or search your jobs…"
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setIndex(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setIndex((active + 1) % rows.length);
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setIndex((active - 1 + rows.length) % rows.length);
              } else if (e.key === "Enter") {
                e.preventDefault();
                rows[active]?.run();
              }
            }}
            className="h-14 min-w-0 flex-1 border-0 bg-transparent text-base outline-none focus:outline-none focus-visible:outline-none focus:ring-0"
          />
          <button type="button" onClick={onClose} aria-label="Close" className="flex size-11 shrink-0 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 sm:size-9 dark:hover:bg-white/5">
            <X className="size-5" aria-hidden />
          </button>
        </div>
        <ul id={listId} role="listbox" aria-label="Results" className="max-h-[50vh] overflow-y-auto p-2">
          {rows.map((r, i) => (
            <li
              key={r.key}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseMove={() => setIndex(i)}
              onClick={r.run}
              className={cn("flex min-h-11 cursor-pointer items-center justify-between gap-3 rounded-lg px-3 py-2 text-theme-sm", i === active ? "bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-300" : "text-gray-700 dark:text-gray-300")}
            >
              <span className="truncate">{r.label}</span>
              <span className="shrink-0 text-theme-xs text-muted">{r.hint}</span>
            </li>
          ))}
        </ul>
        <p role="status" className="sr-only">
          {rows.length} {rows.length === 1 ? "result" : "results"}
        </p>
        {rows.length === 0 && <p className="px-5 pb-5 text-theme-sm text-muted">Nothing matches. Try a screen name such as interviews or profile.</p>}
        <p className="border-t border-gray-200 px-4 py-2 text-theme-xs text-muted dark:border-gray-800">
          Up and down to choose, Enter to go, Esc to close. Press ? for all shortcuts.
        </p>
      </div>
    </div>
  );
}
