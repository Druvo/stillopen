"use client";

import { LayoutGrid, List as ListIcon, Search, SlidersHorizontal } from "lucide-react";
import { useEffect, useId, useRef } from "react";
import type { ViewMode } from "@/lib/types";
import { cn } from "@/lib/utils";
import { nextTabIndex, SORT_OPTIONS, type Filters, type Sort } from "./logic";

export type Tab = { key: string; label: string; description: string; count: number };

export const tabId = (key: string) => `stage-tab-${key || "all"}`;
export const TAB_PANEL_ID = "stage-panel";

/**
 * "All" and one tab per stage, with how many jobs each holds. Real tabs: arrow keys, Home and End move between them (and show that stage),
 * only the chosen one is in the Tab order. On a phone the row scrolls sideways inside itself.
 */
export function StageTabs({ tabs, active, onChange }: { tabs: Tab[]; active: string; onChange: (key: string) => void }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const list = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // keep the chosen tab in view in the scrolling row (a phone shows only some of them)
    // Only the row is scrolled, sideways: scrollIntoView would also scroll the whole page down to the tabs on a phone, on every first load.
    const box = list.current;
    const el = box?.querySelector<HTMLElement>('[aria-selected="true"]');
    if (!box || !el) return;
    const b = box.getBoundingClientRect();
    const t = el.getBoundingClientRect();
    if (t.left < b.left) box.scrollLeft -= b.left - t.left + 8;
    else if (t.right > b.right) box.scrollLeft += t.right - b.right + 8;
  }, [active]);
  const index = Math.max(0, tabs.findIndex((t) => t.key === active));
  const onKeyDown = (event: React.KeyboardEvent) => {
    const to = nextTabIndex(event.key, index, tabs.length);
    if (to === null) return;
    event.preventDefault();
    onChange(tabs[to].key);
    refs.current[to]?.focus();
  };
  return (
    <div ref={list} role="tablist" aria-label="Show jobs by stage" onKeyDown={onKeyDown} className="no-scrollbar -mx-1 flex gap-1 overflow-x-auto border-b border-border px-1">
      {tabs.map((tab, i) => {
        const on = tab.key === active;
        return (
          <button
            key={tab.key || "all"}
            ref={(el) => {
              refs.current[i] = el;
            }}
            id={tabId(tab.key)}
            type="button"
            role="tab"
            aria-selected={on}
            aria-controls={TAB_PANEL_ID}
            tabIndex={on ? 0 : -1}
            title={tab.description || undefined}
            onClick={() => onChange(tab.key)}
            className={cn(
              "-mb-px inline-flex min-h-11 shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-theme-sm font-medium whitespace-nowrap sm:min-h-10",
              on ? "border-brand text-brand" : "border-transparent text-muted hover:text-fg",
            )}
          >
            {tab.label}{" "}
            <span className={cn("rounded-full px-1.5 text-theme-xs", on ? "bg-brand-soft" : "bg-surface-2")}>{tab.count}</span>
          </button>
        );
      })}
    </div>
  );
}

type ToolbarProps = {
  filters: Filters;
  set: (patch: Partial<Filters>) => void;
  open: boolean;
  onToggle: () => void;
  panelId: string;
  activeCount: number;
  view: ViewMode;
  onView: (v: ViewMode) => void;
};

/** The search box, the sort order, the Filters button (with how many filters are set) and the List | Board switch. */
export function Toolbar({ filters, set, open, onToggle, panelId, activeCount, view, onView }: ToolbarProps) {
  const searchId = useId();
  const sortId = useId();
  const field = "min-h-11 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-theme-sm sm:min-h-9";
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative min-w-0 basis-full sm:basis-auto sm:flex-1 sm:max-w-sm">
        <label htmlFor={searchId} className="sr-only">
          Search
        </label>
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
        <input id={searchId} type="search" value={filters.q} onChange={(e) => set({ q: e.target.value })} placeholder="Search company, role or place" autoComplete="off" className={cn(field, "w-full pl-9")} />
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-2">
        <label htmlFor={sortId} className="sr-only">
          Sort by
        </label>
        <select id={sortId} value={filters.sort} onChange={(e) => set({ sort: e.target.value as Sort })} className={cn(field, "max-w-44")}>
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={onToggle}
          className={cn(field, "inline-flex items-center gap-1.5 font-medium hover:bg-surface-2", open && "border-brand")}
        >
          <SlidersHorizontal className="size-4" aria-hidden />
          Filters
          {activeCount > 0 && (
            <>
              <span className="min-w-5 rounded-full bg-brand px-1.5 text-center text-theme-xs text-brand-contrast" aria-hidden>
                {activeCount}
              </span>
              <span className="sr-only">{activeCount} on</span>
            </>
          )}
        </button>
        <div role="group" aria-label="Layout" className="flex overflow-hidden rounded-lg border border-border text-theme-sm">
          {(["list", "board"] as const).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => onView(v)}
              aria-pressed={view === v}
              className={cn("inline-flex min-h-11 items-center gap-1.5 px-3 py-1.5 sm:min-h-9", view === v ? "bg-brand text-brand-contrast" : "bg-surface hover:bg-surface-2")}
            >
              {v === "list" ? <ListIcon className="size-4" aria-hidden /> : <LayoutGrid className="size-4" aria-hidden />}
              {v === "list" ? "List" : "Board"}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
