"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Link } from "@/lib/router";
import type { Dashboard as DashboardData, Job, Progress } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Board } from "./board";
import { JobCard } from "./job-card";
import { applyMove, visibleJobs, type Sort } from "./logic";

const KEY = ["dashboard"] as const;
const VIEW_KEY = "stillopen-dashboard-view";

function usePersistedView(): ["board" | "list", (v: "board" | "list") => void] {
  const [view, setView] = useState<"board" | "list">("board");
  useEffect(() => {
    try {
      if (localStorage.getItem(VIEW_KEY) === "list") setView("list");
    } catch {
      /* not remembered */
    }
  }, []);
  return [
    view,
    (v) => {
      setView(v);
      try {
        localStorage.setItem(VIEW_KEY, v);
      } catch {
        /* not remembered */
      }
    },
  ];
}

/** Polls a progress endpoint every 2 seconds, only while a run is going. */
function useProgress(kind: "scan" | "liveness", onFinished: () => void) {
  const [progress, setProgress] = useState<Progress | null>(null);
  const read = kind === "scan" ? api.scanStatus : api.livenessStatus;
  const start = kind === "scan" ? api.startScan : api.startLiveness;
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    read().then((p) => !cancelled && setProgress(p)).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [read]);

  const running = progress?.running ?? false;
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(async () => {
      try {
        const p = await read();
        setProgress(p);
        if (!p.running) onFinished();
      } catch {
        /* try again on the next tick */
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [running, read, onFinished]);

  const begin = async () => {
    setError("");
    try {
      setProgress(await start());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start. Please try again.");
    }
  };
  return { progress, begin, error };
}

function ProgressChip({ label, running, done, total, error }: { label: string; running: boolean; done: number; total: number; error: string }) {
  if (!running && !error) return null;
  return (
    <p role="status" className="text-sm text-muted">
      {error || `${label}… ${done} of ${total || "?"}`}
    </p>
  );
}

export function Dashboard() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: KEY, queryFn: api.dashboard });
  const [view, setView] = usePersistedView();
  const [text, setText] = useState("");
  const [sort, setSort] = useState<Sort>("best");
  const [message, setMessage] = useState("");
  const [checkingId, setCheckingId] = useState<number | null>(null);

  const refresh = () => client.invalidateQueries({ queryKey: KEY });
  const scan = useProgress("scan", refresh);
  const liveness = useProgress("liveness", refresh);

  const move = useMutation({
    mutationFn: ({ job, statusId }: { job: Job; statusId: number }) => api.setStatus(job.id, statusId),
    onMutate: async ({ job, statusId }) => {
      await client.cancelQueries({ queryKey: KEY });
      const before = client.getQueryData<DashboardData>(KEY);
      const status = before?.statuses.find((s) => s.id === statusId);
      if (before && status) client.setQueryData<DashboardData>(KEY, applyMove(before, job.id, status));
      return { before, status, job };
    },
    onError: (error, _vars, ctx) => {
      if (ctx?.before) client.setQueryData(KEY, ctx.before); // put the card back
      setMessage(`Could not move ${ctx?.job.role ?? "the job"}: ${error instanceof ApiError ? error.message : "please try again."}`);
    },
    onSuccess: (_data, _vars, ctx) => {
      setMessage(`Moved ${ctx?.job.role ?? "job"} to ${ctx?.status?.name ?? "its new status"}.`);
      refresh();
    },
  });

  const onMove = (job: Job, statusId: number) => {
    if (job.status_id !== statusId) move.mutate({ job, statusId });
  };

  const onCheckFit = async (job: Job) => {
    setCheckingId(job.id);
    setMessage("");
    try {
      const result = await api.evaluate(job.id);
      setMessage(`${job.role} at ${job.company}: ${result.match_percent}% match.`);
      await refresh();
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : "Could not check the fit. Please try again.");
    } finally {
      setCheckingId(null);
    }
  };

  const data = query.data;
  const jobs = useMemo(() => (data ? visibleJobs(data.jobs, { text, sort }) : []), [data, text, sort]);

  if (query.isPending) return <p className="text-muted">Loading your jobs…</p>;
  if (query.isError || !data) {
    return (
      <div role="alert" className="rounded-lg border border-border bg-surface p-4">
        <p className="font-medium">We could not load your jobs.</p>
        <button type="button" onClick={() => query.refetch()} className="mt-2 rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-brand-contrast">
          Try again
        </button>
      </div>
    );
  }

  const common = { statuses: data.statuses, onMove, onCheckFit, checkingId };

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{data.greeting}</h1>
          <p className="text-sm text-muted">
            {data.stats.total} {data.stats.total === 1 ? "job" : "jobs"}
            {data.stats.submitted ? ` · ${data.stats.submitted} applied` : ""}
            {data.stats.average_match !== null ? ` · ${data.stats.average_match}% average match` : ""}
            {data.stats.urgent ? ` · ${data.stats.urgent} due soon` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {data.can_scan && (
            <button type="button" onClick={scan.begin} disabled={scan.progress?.running} className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-brand-contrast disabled:opacity-60">
              Search for jobs
            </button>
          )}
          <button type="button" onClick={liveness.begin} disabled={liveness.progress?.running} className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm font-medium disabled:opacity-60">
            Check which are still open
          </button>
          <Link to="/jobs/add" className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm font-medium">
            Add job
          </Link>
        </div>
      </header>

      <ProgressChip label="Searching" running={scan.progress?.running ?? false} done={scan.progress?.done ?? 0} total={scan.progress?.total ?? 0} error={scan.error || scan.progress?.error || ""} />
      <ProgressChip label="Checking" running={liveness.progress?.running ?? false} done={liveness.progress?.done ?? 0} total={liveness.progress?.total ?? 0} error={liveness.error || liveness.progress?.error || ""} />

      {data.next_step && (
        <div className="rounded-lg border border-border bg-surface p-4">
          <h2 className="font-semibold">{data.next_step.headline}</h2>
          <p className="mt-1 text-sm text-muted">{data.next_step.body}</p>
          {data.next_step.label && data.next_step.url && (
            <a href={data.next_step.url} className="mt-3 inline-block rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-brand-contrast">
              {data.next_step.label}
            </a>
          )}
        </div>
      )}

      {data.followups.length > 0 && (
        <div className="rounded-lg border border-border bg-surface p-4 text-sm">
          <h2 className="font-semibold">Time to follow up</h2>
          <ul className="mt-1 list-inside list-disc text-muted">
            {data.followups.map((f) => (
              <li key={f.id}>
                {f.role} at {f.company} (since {f.follow_up_date})
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <label className="sr-only" htmlFor="search">
          Search your jobs
        </label>
        <input
          id="search"
          type="search"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Search company, role or place"
          className="min-w-0 flex-1 rounded-md border border-border bg-surface px-3 py-1.5 text-sm sm:max-w-sm"
        />
        <label className="sr-only" htmlFor="sort">
          Sort by
        </label>
        <select id="sort" value={sort} onChange={(e) => setSort(e.target.value as Sort)} className="rounded-md border border-border bg-surface px-2 py-1.5 text-sm">
          <option value="best">Best match first</option>
          <option value="newest">Newest first</option>
          <option value="deadline">Deadline soonest</option>
          <option value="company">Company A to Z</option>
        </select>
        <div role="group" aria-label="Layout" className="ml-auto flex overflow-hidden rounded-md border border-border text-sm">
          {(["board", "list"] as const).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setView(v)}
              aria-pressed={view === v}
              className={cn("px-3 py-1.5", view === v ? "bg-brand text-brand-contrast" : "bg-surface")}
            >
              {v === "board" ? "Board" : "List"}
            </button>
          ))}
        </div>
      </div>

      <p role="status" aria-live="polite" className="min-h-5 text-sm text-muted">
        {message}
      </p>

      {data.jobs.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-8 text-center">
          <p className="font-medium">No jobs yet.</p>
          <p className="mt-1 text-sm text-muted">Press Search for jobs, or paste a link on the <Link to="/jobs/add" className="text-brand underline">Add job</Link> page.</p>
        </div>
      ) : view === "board" ? (
        <Board buckets={data.buckets} jobs={jobs} {...common} />
      ) : jobs.length === 0 ? (
        <p className="text-sm text-muted">No job matches that search.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {jobs.map((job) => (
            <JobCard key={job.id} job={job} statuses={data.statuses} onMove={onMove} onCheckFit={onCheckFit} checking={checkingId === job.id} />
          ))}
        </div>
      )}
    </div>
  );
}
