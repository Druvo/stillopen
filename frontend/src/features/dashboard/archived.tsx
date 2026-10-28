"use client";

import { Button } from "@/components/ui";
import type { ArchivedJob } from "@/lib/types";

/** Jobs the person archived: kept out of the list and its counts, each with a way back. Shown only when there are some. */
export function ArchivedSection({ items, onRestore }: { items: ArchivedJob[]; onRestore: (id: number) => void }) {
  if (items.length === 0) return null;
  return (
    <details id="archived" className="so-card rounded-2xl border border-border bg-surface p-3 text-theme-sm">
      <summary className="cursor-pointer font-medium">Archived ({items.length})</summary>
      <p className="mt-2 text-theme-xs text-muted">These are kept, but they are not on your list or in your numbers. Restore one to bring it back exactly as it was.</p>
      <ul className="mt-2 divide-y divide-border">
        {items.map((a) => (
          <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span className="min-w-0">
              <span className="font-medium">{a.role}</span> at {a.company} <span className="text-muted">· {a.status}</span>
            </span>
            <Button variant="outline" small onClick={() => onRestore(a.id)} aria-label={`Restore ${a.role} at ${a.company}`}>
              Restore
            </Button>
          </li>
        ))}
      </ul>
    </details>
  );
}
