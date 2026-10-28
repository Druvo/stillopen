"use client";

import { useQuery } from "@tanstack/react-query";
import { Card } from "@/components/ui";
import { Link } from "@/lib/router";
import { jobsApi } from "@/features/jobs/api";
import { strengthText } from "@/features/jobs/match-logic";

export const STRENGTH_KEY = ["profile-strength"] as const;

/** How much of what matching needs is filled in, with the three most useful things still missing. Counts only what changes a match. */
export function StrengthMeter({ stamp }: { stamp?: unknown }) {
  const query = useQuery({ queryKey: [...STRENGTH_KEY, stamp ?? null], queryFn: jobsApi.strength, retry: false });
  if (!query.data) return null;
  const { percent, missing, complete } = query.data;
  return (
    <Card>
      <h2 className="font-semibold">Profile strength</h2>
      <div className="mt-2 flex items-center gap-3">
        <div
          role="meter"
          aria-label="Profile strength"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          aria-valuetext={strengthText(percent)}
          className="h-2.5 flex-1 overflow-hidden rounded-full bg-surface-2"
        >
          <div className="h-full bg-brand" style={{ width: `${percent}%` }} />
        </div>
        <span className="text-sm font-semibold" aria-hidden>
          {percent}%
        </span>
      </div>
      {complete ? (
        <p className="mt-2 text-sm text-muted">Everything that matters for matching is filled in.</p>
      ) : (
        <>
          <p className="mt-2 text-sm text-muted">The most useful things to add next:</p>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
            {missing.map((m) => (
              <li key={m.key}>
                <Link to={m.to} className="text-brand underline">
                  {m.label}
                </Link>
                <span className="text-muted"> — {m.why}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}
