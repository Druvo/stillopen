"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, ErrorBox, Loading } from "@/components/ui";
import { errorText } from "@/lib/api";
import { jobsApi } from "./api";
import { historyDay } from "./jobmgmt";

/** What has happened to one job, newest first: moves between statuses, applying, interviews, follow-ups and notes. */
export function HistoryPanel({ jobId }: { jobId: number }) {
  const query = useQuery({ queryKey: ["job-history", jobId], queryFn: () => jobsApi.history(jobId), staleTime: 0 });
  return (
    <Card className="mb-4" role="region" aria-labelledby="job-history-title">
      <h2 id="job-history-title" className="mb-2 font-semibold">
        History
      </h2>
      {query.isPending ? (
        <Loading what="the history" />
      ) : query.isError ? (
        <ErrorBox message={errorText(query.error, "We could not load the history.")} onRetry={() => query.refetch()} />
      ) : query.data.items.length === 0 ? (
        <p className="text-sm text-muted">Nothing has happened to this job yet. When you move it to another status, apply, add an interview or set a reminder, it is written down here.</p>
      ) : (
        <>
          <ol className="divide-y divide-border text-sm">
            {query.data.items.map((item) => (
              <li key={item.id} className="flex flex-wrap gap-x-3 gap-y-0.5 py-1.5">
                <time dateTime={item.date} className="w-28 shrink-0 text-muted">
                  {historyDay(item.date)}
                </time>
                <span className="min-w-0 flex-1 break-words">
                  <span className="mr-1.5 rounded bg-surface-2 px-1.5 py-0.5 text-xs text-muted">{item.kind_label}</span>
                  {item.text}
                </span>
              </li>
            ))}
          </ol>
          {query.data.capped && <p className="mt-2 text-xs text-muted">Showing the latest 100. Older lines are kept.</p>}
        </>
      )}
    </Card>
  );
}
