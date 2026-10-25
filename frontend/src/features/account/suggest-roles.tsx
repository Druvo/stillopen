"use client";

import { useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui";
import { errorText } from "@/lib/api";
import { assistApi } from "@/features/assist/api";
import { hasRole } from "@/features/assist/logic";
import { ProblemLine } from "@/features/assist/ui";

/**
 * "Suggest roles from my CV": a few role titles (and places the CV states) as chips. Tapping a role only adds it to the box; the person
 * still saves the form themselves. Works without an AI key (it reads job titles out of the CV), and says so.
 */
export function SuggestRoles({ cv, roles, onAddRole, onAddPlace }: { cv: string; roles: string; onAddRole: (role: string) => void; onAddPlace?: (place: string) => void }) {
  const suggest = useMutation({ mutationFn: () => assistApi.suggest(cv) });
  const data = suggest.data;
  return (
    <div className="mb-3" data-testid="suggest-roles">
      <Button variant="outline" small disabled={suggest.isPending} onClick={() => suggest.mutate()}>
        {suggest.isPending ? "Reading your CV…" : "Suggest roles from my CV"}
      </Button>
      <ProblemLine message={suggest.isError ? errorText(suggest.error) : ""} />
      {data && data.roles.length === 0 && (
        <p className="mt-2 text-sm text-muted">We could not find job titles in your CV. Type the roles you want in the box above, or add your free Google AI Studio key in AI settings for suggestions.</p>
      )}
      {data && data.roles.length > 0 && (
        <div className="mt-2">
          <p className="text-xs text-muted">Tap one to add it to the box above. Nothing is saved until you save.</p>
          <ul className="mt-1 flex flex-wrap gap-2">
            {data.roles.map((role) => {
              const added = hasRole(roles, role);
              return (
                <li key={role}>
                  <button
                    type="button"
                    disabled={added}
                    onClick={() => onAddRole(role)}
                    className="rounded-full border border-border bg-surface px-3 py-1 text-sm hover:bg-surface-2 disabled:opacity-60"
                  >
                    {added ? `✓ ${role}` : `+ ${role}`}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {data && data.places.length > 0 && (
        <div className="mt-2">
          <p className="text-xs text-muted">{onAddPlace ? "Places your CV mentions (tap to add):" : "Places your CV mentions (add them under where you would work, below):"}</p>
          <ul className="mt-1 flex flex-wrap gap-2">
            {data.places.map((place) => (
              <li key={place}>
                {onAddPlace ? (
                  <button type="button" onClick={() => onAddPlace(place)} className="rounded-full border border-border bg-surface px-3 py-1 text-sm hover:bg-surface-2">
                    + {place}
                  </button>
                ) : (
                  <span className="rounded-full border border-border px-3 py-1 text-sm">{place}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {data?.method === "ai" && <p className="mt-2 text-xs text-muted">{data.notice}</p>}
      {data?.method === "rules" && data.roles.length > 0 && <p className="mt-2 text-xs text-muted">Read from the job titles in your CV, without AI.</p>}
    </div>
  );
}
