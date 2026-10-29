"use client";

import { SlidersHorizontal } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { Card } from "@/components/ui";
import type { Bucket, Job } from "@/lib/types";
import { cn } from "@/lib/utils";
import { COUNTRY_NOT_STATED, countryOptions, isFiltered, NOT_STATED, SORT_OPTIONS, stageChips, type Filters, type Sort } from "./logic";

const CONTROL = "w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-theme-sm";

function Select({ label, value, onChange, children }: { label: string; value: string; onChange: (v: string) => void; children: ReactNode }) {
  const id = useId();
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="mb-1 block text-theme-xs font-medium text-muted">
        {label}
      </label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className={CONTROL}>
        {children}
      </select>
    </div>
  );
}

type Props = {
  filters: Filters;
  set: (patch: Partial<Filters>) => void;
  reset: () => void;
  jobs: Job[];
  buckets: Bucket[];
  bandLabels: string[];
  shown: number;
};

/**
 * Stage chips, search and the dropdowns the classic dashboard had. On a phone everything but the chips folds into a "Filters" button.
 * "Showing N of M" and "Clear filters" stay visible.
 */
export function FilterBar({ filters, set, reset, jobs, buckets, bandLabels, shown }: Props) {
  const [open, setOpen] = useState(false);
  const chips = stageChips(jobs, buckets);
  const countries = countryOptions(jobs);
  const filtered = isFiltered(filters);
  const searchId = useId();
  return (
    <Card id="job-filters" className="space-y-3">
      <div role="group" aria-label="Show jobs by stage" className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 sm:flex-wrap sm:overflow-visible sm:pb-0">
        {chips.map((chip) => {
          const on = chip.key === filters.stage;
          return (
            <button
              key={chip.key || "all"}
              type="button"
              aria-pressed={on}
              title={chip.description || undefined}
              onClick={() => set({ stage: chip.key })}
              className={cn(
                "shrink-0 rounded-full px-3 py-1 text-theme-sm font-medium",
                on ? "bg-brand text-brand-contrast" : "border border-border bg-surface text-muted hover:bg-surface-2 hover:text-fg",
              )}
            >
              {chip.label} ({chip.count})
            </button>
          );
        })}
      </div>

      <div className="flex items-end gap-2">
        <div className="min-w-0 flex-1 md:max-w-sm">
          <label htmlFor={searchId} className="mb-1 block text-theme-xs font-medium text-muted">
            Search
          </label>
          <input id={searchId} type="search" value={filters.q} onChange={(e) => set({ q: e.target.value })} placeholder="Company, role or place" autoComplete="off" className={CONTROL} />
        </div>
        <button
          type="button"
          aria-expanded={open}
          aria-controls="more-filters"
          onClick={() => setOpen((v) => !v)}
          className="inline-flex items-center gap-1 rounded-lg border border-border bg-surface px-3 py-1.5 text-theme-sm font-medium md:hidden"
        >
          <SlidersHorizontal className="size-4" aria-hidden /> {open ? "Hide more filters" : "More filters"}
        </button>
      </div>

      <div id="more-filters" className={cn("grid-cols-2 gap-2 md:grid-cols-4 md:grid", open ? "grid" : "hidden")}>
        <Select label="Fits your places" value={filters.fit} onChange={(v) => set({ fit: v as Filters["fit"] })}>
          <option value="">Any</option>
          <option value="fits">Fits</option>
          <option value="check">Check fit</option>
          <option value="unknown">Fit unknown</option>
        </Select>
        <Select label="How well you match" value={filters.band} onChange={(v) => set({ band: v })}>
          <option value="">Any</option>
          {bandLabels.map((label) => (
            <option key={label} value={label}>
              {label}
            </option>
          ))}
          <option value={NOT_STATED}>Not checked yet</option>
        </Select>
        <Select label="Work" value={filters.work} onChange={(v) => set({ work: v })}>
          <option value="">Any</option>
          <option value="remote">Remote</option>
          <option value="hybrid">Hybrid</option>
          <option value="onsite">On-site</option>
          <option value={NOT_STATED}>Not stated</option>
        </Select>
        <Select label="Country" value={filters.country} onChange={(v) => set({ country: v })}>
          <option value="">Anywhere</option>
          {countries.map((c) => (
            <option key={c.code} value={c.code}>
              {c.name}
            </option>
          ))}
          <option value={COUNTRY_NOT_STATED}>Not stated</option>
        </Select>
        <Select label="Posting" value={filters.live} onChange={(v) => set({ live: v })}>
          <option value="">Any</option>
          <option value="active">Open</option>
          <option value="expired">Closed</option>
          <option value="uncertain">Unclear</option>
          <option value="unknown">Not checked</option>
        </Select>
        <Select label="Found" value={filters.found} onChange={(v) => set({ found: v as Filters["found"] })}>
          <option value="">Any time</option>
          <option value="today">Today</option>
          <option value="week">Last 7 days</option>
        </Select>
        <Select label="Sort by" value={filters.sort} onChange={(v) => set({ sort: v as Sort })}>
          {SORT_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </Select>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <span aria-live="polite" className="text-theme-sm text-muted">
          {filtered ? `Showing ${shown} of ${jobs.length}` : `Showing all ${jobs.length}`}
        </span>
        {filtered && (
          <button type="button" onClick={reset} className="text-theme-sm text-brand underline">
            Clear filters
          </button>
        )}
      </div>
    </Card>
  );
}
