"use client";

import { useId, type ReactNode } from "react";
import type { Job } from "@/lib/types";
import { COUNTRY_NOT_STATED, countryOptions, isFiltered, NOT_STATED, type Filters } from "./logic";

const CONTROL = "w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-theme-sm min-h-11 sm:min-h-9";

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
  id: string;
  filters: Filters;
  set: (patch: Partial<Filters>) => void;
  reset: () => void;
  /** Every job (the countries to pick from come from these, whatever stage tab is chosen). */
  jobs: Job[];
  bandLabels: string[];
  /** How many jobs the chosen stage tab holds, and how many of those the search and filters keep. */
  inStage: number;
  shown: number;
  /** How many jobs "Hide weak matches" is leaving out of what the other filters keep. */
  hidden?: number;
};

/**
 * The six filters, "Showing N of M" and "Clear filters". The dashboard shows this panel only when the person pressed the Filters button;
 * the stage tabs, the search box and the sort order live in the toolbar above it.
 */
export function FilterPanel({ id, filters, set, reset, jobs, bandLabels, inStage, shown, hidden = 0 }: Props) {
  const countries = countryOptions(jobs);
  const filtered = isFiltered(filters);
  return (
    <section id={id} aria-label="Filters" className="so-card rounded-xl border border-border bg-surface p-3 sm:p-4">
      <div className="grid grid-cols-1 gap-2 min-[425px]:grid-cols-2 md:grid-cols-3 xl:grid-cols-6">
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
      </div>
      <label className="mt-3 flex min-h-11 items-center gap-2 text-theme-sm sm:min-h-6">
        <input type="checkbox" checked={filters.hideWeak} onChange={(e) => set({ hideWeak: e.target.checked })} />
        <span>Hide weak matches (under 40%)</span>
      </label>
      <p className="text-theme-xs text-muted">Jobs that have not been checked yet are always shown.</p>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <span className="text-theme-sm text-muted">
          {filtered ? `Showing ${shown} of ${inStage}` : `Showing all ${inStage}`}
          {hidden > 0 ? ` (${hidden} hidden as weak ${hidden === 1 ? "match" : "matches"}) ` : ""}
          {hidden > 0 && (
            <button type="button" onClick={() => set({ hideWeak: false })} className="text-brand underline">
              Show them
            </button>
          )}
        </span>
        {filtered && (
          <button type="button" onClick={reset} className="min-h-11 px-2 text-theme-sm text-brand underline sm:min-h-0">
            Clear filters
          </button>
        )}
      </div>
    </section>
  );
}
