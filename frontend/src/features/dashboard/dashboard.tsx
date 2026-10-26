"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, buttonClass, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { Link } from "@/lib/router";
import { notify } from "@/lib/toast";
import type { Dashboard as DashboardData, Job, Progress, ScanStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { dashboardApi, useMe } from "./api";
import { Board } from "./board";
import { FilterBar } from "./filters";
import { JobCard, type CardExtras } from "./job-card";
import { ComingUp, FollowupsDue, NextStepCard, ScanCard, Spinner, StaffBanners, StatTiles } from "./panels";
import {
  applyMove, checkButtonText, DEFAULT_FILTERS, emptyKind, FILTERS_KEY, importMessage, initialFilters, scanButtonText, subtitle, visibleJobs, type Filters,
} from "./logic";

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

/** The filters, remembered for this browser tab. The header's search box sets the text (also through `?q=` in the address). */
function useFilters(): [Filters, (patch: Partial<Filters>) => void, () => void, (valid: { countries: string[]; bands: string[] }) => void] {
  const [filters, setFilters] = useState<Filters>(() => {
    let stored: string | null = null;
    try {
      stored = sessionStorage.getItem(FILTERS_KEY);
    } catch {
      /* not remembered */
    }
    return initialFilters(stored, typeof window === "undefined" ? "" : window.location.search);
  });
  useEffect(() => {
    try {
      sessionStorage.setItem(FILTERS_KEY, JSON.stringify(filters));
    } catch {
      /* not remembered */
    }
  }, [filters]);
  useEffect(() => {
    const onSearch = (e: Event) => setFilters((f) => ({ ...f, q: String((e as CustomEvent<string>).detail ?? "") }));
    window.addEventListener("so-search", onSearch);
    return () => window.removeEventListener("so-search", onSearch);
  }, []);
  return [
    filters,
    (patch) => setFilters((f) => ({ ...f, ...patch })),
    () => setFilters({ ...DEFAULT_FILTERS }),
    ({ countries, bands }) => setFilters((f) => initialFilters(JSON.stringify(f), "", countries, bands)),
  ];
}

/**
 * A search or an open/closed check: starts it, then polls every 1.5 seconds while it runs. `initial` is what the dashboard already knows,
 * so a run that was going when the page opened is picked up. `onAdded` fires when a search has found new jobs, `onFinished` at the end.
 */
function useRun<T extends Progress>(opts: { read: () => Promise<T>; start: () => Promise<T>; initial?: T | null; readOnMount?: boolean; onFinished: () => void; onAdded?: () => void }) {
  const { read, start, initial, readOnMount, onFinished, onAdded } = opts;
  const [latest, setLatest] = useState<T | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const seenAdded = useRef<number | null>(null);
  const current = latest ?? initial ?? null;
  const running = current?.running ?? false;

  useEffect(() => {
    if (initial?.running && !latest?.running) setLatest(initial);
  }, [initial, latest?.running]);

  useEffect(() => {
    if (!readOnMount) return;
    let cancelled = false;
    read().then((p) => !cancelled && setLatest(p)).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [read, readOnMount]);

  useEffect(() => {
    if (seenAdded.current === null && current) seenAdded.current = current.added ?? 0;
  }, [current]);

  useEffect(() => {
    if (!running) return;
    const timer = setInterval(async () => {
      try {
        const p = await read();
        setLatest(p);
        if ((p.added ?? 0) > (seenAdded.current ?? 0)) {
          seenAdded.current = p.added ?? 0;
          onAdded?.(); // the first jobs are ready: show them now, the search carries on
        }
        if (!p.running) onFinished();
      } catch {
        /* try again on the next tick */
      }
    }, 1500);
    return () => clearInterval(timer);
  }, [running, read, onFinished, onAdded]);

  const begin = async () => {
    setError("");
    setStarting(true);
    try {
      const p = await start();
      seenAdded.current = p.added ?? 0;
      setLatest(p);
    } catch (e) {
      const text = errorText(e, "Could not start. Please try again.");
      setError(text);
      notify(text, "error");
    } finally {
      setStarting(false);
    }
  };
  return { current, running, starting, error, begin };
}

export function Dashboard() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: KEY, queryFn: api.dashboard });
  const me = useMe();
  const [view, setView] = usePersistedView();
  const [filters, setFilter, resetFilters, fixFilters] = useFilters();
  const [message, setMessage] = useState("");
  const [checkingId, setCheckingId] = useState<number | null>(null);
  const [importing, setImporting] = useState(false);
  const [pendingCard, setPendingCard] = useState<string | null>(null);

  const refresh = useCallback(() => client.invalidateQueries({ queryKey: KEY }), [client]);
  const data = query.data;

  const scan = useRun<ScanStatus>({ read: dashboardApi.scanStatus, start: dashboardApi.startScan, initial: data?.scan, onFinished: refresh, onAdded: refresh });
  const liveness = useRun<Progress>({ read: api.livenessStatus, start: api.startLiveness, readOnMount: true, onFinished: refresh });

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
      setMessage(`Could not move ${ctx?.job.role ?? "the job"}: ${errorText(error, "please try again.")}`);
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
      setMessage(errorText(e, "That did not work this time. Please try again."));
    } finally {
      setCheckingId(null);
    }
  };

  const importNow = async () => {
    setImporting(true);
    try {
      notify(importMessage(await dashboardApi.importTracker()));
      await refresh();
    } catch (e) {
      notify(errorText(e, "Import failed"), "error");
    } finally {
      setImporting(false);
    }
  };

  // Stale choices (a country with no jobs left) fall back to "any" once the jobs are known.
  const validated = useRef(false);
  useEffect(() => {
    if (!data || validated.current) return;
    validated.current = true;
    fixFilters({ countries: [...new Set(data.jobs.map((j) => j.country).filter(Boolean))], bands: data.band_labels });
  }, [data, fixFilters]);

  const jobs = useMemo(() => (data ? visibleJobs(data.jobs, filters) : []), [data, filters]);

  // A link to one card (the next-step button, or #job-N in the address) must never land on a filtered-out job.
  const goToCard = useCallback(
    (id: string) => {
      const num = Number(id.replace("job-", ""));
      if (!jobs.some((j) => j.id === num)) resetFilters();
      setPendingCard(id);
    },
    [jobs, resetFilters],
  );
  const hashHandled = useRef(false);
  useEffect(() => {
    if (!data || hashHandled.current) return;
    hashHandled.current = true;
    if (window.location.hash.startsWith("#job-")) goToCard(window.location.hash.slice(1));
  }, [data, goToCard]);
  useEffect(() => {
    if (!pendingCard || !data) return;
    const el = document.getElementById(pendingCard);
    if (el) {
      el.scrollIntoView({ block: "start" });
      setPendingCard(null);
    } else if (!data.jobs.some((j) => `job-${j.id}` === pendingCard)) {
      setPendingCard(null);
    }
  }, [pendingCard, data, jobs]);

  if (query.isPending) return <Loading what="your jobs" />;
  if (query.isError || !data) return <ErrorBox message="We could not load your jobs." onRetry={() => query.refetch()} />;

  const extras: CardExtras = { judgeLabel: data.judge_label, prepEnabled: data.prep_enabled, paperlessUrl: data.paperless_on ? data.paperless_url : "", refresh };
  const common = { statuses: data.statuses, extras, onMove, onCheckFit, checkingId };
  const scanView = scan.current;
  const empty = emptyKind(data.jobs.length, jobs.length, scanView);
  const boardColumns = filters.stage ? data.buckets.filter((b) => b.key === filters.stage) : data.buckets;

  const actions = (
    <>
      <Link to="/jobs/add" className={buttonClass("primary")}>
        Add job
      </Link>
      {data.can_scan && (
        <Button
          variant="outline"
          onClick={scan.begin}
          disabled={scan.running || scan.starting}
          title="Searches every enabled job board for postings matching your target roles. Free -- no AI used."
        >
          {(scan.running || scan.starting) && <Spinner />}
          {scanButtonText(scanView, scan.starting)}
        </Button>
      )}
      <Button variant="outline" onClick={liveness.begin} disabled={liveness.running || liveness.starting} title="Looks at each job link and tells you if the posting has closed.">
        {checkButtonText(liveness.running, liveness.starting, liveness.current?.done ?? 0, liveness.current?.total ?? 0)}
      </Button>
      {data.can_import && (
        <Button variant="outline" onClick={importNow} disabled={importing}>
          {importing ? "Importing…" : "Import from career-ops"}
        </Button>
      )}
      {data.paperless_on && (
        <a href={data.paperless_url} target="_blank" rel="noopener noreferrer" className={buttonClass("outline")}>
          Paperless
        </a>
      )}
    </>
  );

  return (
    <div className="space-y-4">
      <PageHeader title={data.greeting} subtitle={subtitle(data.stats.total, data.checked_at)} actions={actions} />
      <StaffBanners me={me.data} />
      {liveness.error && (
        <p role="alert" className="text-theme-sm text-bad">
          {liveness.error}
        </p>
      )}
      {data.next_step && <NextStepCard step={data.next_step} onCard={goToCard} />}
      <ScanCard scan={scanView} starting={scan.starting} />
      <ComingUp items={data.upcoming_interviews} />
      <FollowupsDue items={data.followups} onChanged={refresh} />
      <StatTiles data={data} />

      <FilterBar filters={filters} set={setFilter} reset={resetFilters} jobs={data.jobs} buckets={data.buckets} bandLabels={data.band_labels} shown={jobs.length} />

      <div className="flex flex-wrap items-center gap-2">
        <p role="status" aria-live="polite" className="min-h-5 flex-1 text-theme-sm text-muted">
          {message}
        </p>
        <div role="group" aria-label="Layout" className="ml-auto flex overflow-hidden rounded-lg border border-border text-theme-sm">
          {(["board", "list"] as const).map((v) => (
            <button key={v} type="button" onClick={() => setView(v)} aria-pressed={view === v} className={cn("px-3 py-1.5", view === v ? "bg-brand text-brand-contrast" : "bg-surface")}>
              {v === "board" ? "Board" : "List"}
            </button>
          ))}
        </div>
      </div>

      {empty ? (
        <div className="rounded-2xl border border-dashed border-border p-8 text-center text-theme-sm text-muted">
          {empty === "searching" && (
            <p className="flex items-center justify-center gap-2">
              <Spinner />
              We are searching {scanView?.total} job sources for roles that fit you. They will appear here in a minute, with nothing for you to do.
            </p>
          )}
          {empty === "nothing-matched" && (
            <p>
              Nothing new matched yet. Check your roles and places in{" "}
              <Link to="/profile" className="text-brand underline">
                Profile
              </Link>
              , or{" "}
              <Link to="/jobs/add" className="text-brand underline">
                add a job
              </Link>
              .
            </p>
          )}
          {empty === "no-jobs" && (
            <p>
              No jobs yet.{" "}
              <Link to="/jobs/add" className="text-brand underline">
                Add a job
              </Link>{" "}
              to get started.
            </p>
          )}
          {empty === "no-matches" && (
            <p>
              No jobs match these filters.{" "}
              <button type="button" onClick={resetFilters} className="text-brand underline">
                Show everything again
              </button>
            </p>
          )}
        </div>
      ) : view === "board" ? (
        <Board buckets={boardColumns} jobs={jobs} {...common} />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {jobs.map((job) => (
            <JobCard key={job.id} job={job} statuses={data.statuses} extras={extras} onMove={onMove} onCheckFit={onCheckFit} checking={checkingId === job.id} />
          ))}
        </div>
      )}
    </div>
  );
}
