"use client";

import { useQuery } from "@tanstack/react-query";
import { Badge, Card } from "@/components/ui";
import { errorText } from "@/lib/api";
import { Link } from "@/lib/router";
import { accountApi } from "./api";
import { countText, emptyLine, levelWord, searchText, type Coverage, type CoverageArea } from "./coverage-logic";

export const COVERAGE_KEY = ["account", "coverage"] as const;

/** The one line the dashboard's "Your search" card shows when a place has no jobs; null while loading, on error, or when all is well. */
export function useCoverageLine(enabled: boolean): string | null {
  const query = useQuery({ queryKey: COVERAGE_KEY, queryFn: accountApi.coverage, enabled, retry: false, staleTime: 5 * 60 * 1000 });
  return emptyLine(query.data);
}

const TONE = { none: "bad", thin: "warn", ok: "good", unknown: "muted" } as const;

function AreaRow({ area, days }: { area: CoverageArea; days: number }) {
  return (
    <li className="rounded-lg bg-surface-2 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-medium">{area.label}</h3>
        <Badge tone={TONE[area.level]}>{levelWord(area)}</Badge>
      </div>
      <p className="mt-1 text-sm">{countText(area, days)}</p>
      {area.searches.length > 0 && (
        <ul className="mt-1 list-disc pl-5 text-sm text-muted">
          {area.searches.map((s) => (
            <li key={s.name}>{searchText(s)}</li>
          ))}
        </ul>
      )}
      {area.tip && <p className="mt-2 text-sm font-medium">{area.tip}</p>}
    </li>
  );
}

/** "Where we find jobs for you": for each place in the person's search, how many jobs the boards listed lately and what to do when it is empty. */
export function CoverageCard() {
  const query = useQuery({ queryKey: COVERAGE_KEY, queryFn: accountApi.coverage, retry: false, staleTime: 5 * 60 * 1000 });
  return (
    <Card>
      <h2 className="mb-1 font-semibold">Where we find jobs for you</h2>
      {query.isPending && <p className="text-sm text-muted">Checking your places…</p>}
      {query.isError && <p className="text-sm text-muted">{errorText(query.error, "We could not check this just now.")}</p>}
      {query.data && <CoverageBody coverage={query.data} />}
    </Card>
  );
}

export function CoverageBody({ coverage }: { coverage: Coverage }) {
  if (!coverage.has_areas) {
    return (
      <p className="text-sm text-muted">
        Tell us where you would work and we will show how many jobs each place has.{" "}
        <Link to="/profile" className="link-target text-brand underline">
          Add a place
        </Link>
      </p>
    );
  }
  return (
    <>
      <p className="mb-3 text-sm text-muted">For each place you would work in: the jobs our sources listed in the last {coverage.days} days, and what is searching there.</p>
      <ul className="space-y-2">
        {coverage.areas.map((a) => (
          <AreaRow key={a.id} area={a} days={coverage.days} />
        ))}
      </ul>
    </>
  );
}
