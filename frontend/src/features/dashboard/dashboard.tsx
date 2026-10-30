"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActionMenu, type MenuItem } from "@/components/menu";
import { Button, buttonClass, ErrorBox, ScreenSkeleton } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { usePreferences } from "@/lib/use-preferences";
import { Link } from "@/lib/router";
import { notify } from "@/lib/toast";
import { takeScanRequest } from "@/lib/scan-request";
import type { Dashboard as DashboardData, Job, Progress, ScanStatus, ViewMode } from "@/lib/types";
import { cn } from "@/lib/utils";
import { jobsApi } from "@/features/jobs/api";
import { CSV_EXPORT_URL, troubleLine } from "@/features/jobs/jobmgmt";
import { RemoveDialog } from "@/features/jobs/remove";
import { STATS_KEY, useStats } from "@/features/stats/api";
import { useCoverageLine } from "@/features/account/coverage";
import { dashboardApi, useMe } from "./api";
import { FilterPanel } from "./filters";
import { JobCard, type CardExtras } from "./job-card";
import {
  activeFilterCount, applyMove, checkButtonText, emptyKind, filtersFromPrefs, headerLine, hiddenWeakCount, importMessage, isFiltered, patchFromFilters, resultsText, scanButtonText, stageChips,
  visibleJobs, type Filters,
} from "./logic";
import { allSelected, archivedText, movedText, notForMeStatus, pruneSelection, removedText, selectAllIn, statusLabel, toggleId, undoText, weakLine } from "./jobmgmt";
import { ArchivedSection } from "./archived";
import { SelectionBar, UndoBar } from "./selection";
import { comingUpItems } from "./coming-up";
import { checklistSteps, showChecklist } from "./checklist";
import { AiKeyPrompt, ChecklistCard, AsideCard, ComingUpBody, DraftsBody, FollowupsBody, WorthBody, LastSearchBody, NextStepBody, Spinner, StaffBanners, StatTiles, ThisWeekBody, UpdateNotice, YourSearchBody } from "./panels";
import { StageTabs, TAB_PANEL_ID, tabId, Toolbar } from "./toolbar";
import { useRun } from "./use-run";
import { TimezonePrompt } from "./timezone-prompt";

// The board (and the drag-and-drop library it needs) is fetched only when someone asks for the board view.
const Board = lazy(() => import("./board"));
// The goals card draws with the stats chunk, which is fetched only for a person who set a goal.
const GoalsBody = lazy(() => import("@/features/stats/viz").then((m) => ({ default: m.GoalsBody })));

const KEY = ["dashboard"] as const;
const PAGE = 50; // the list shows this many at first, then "Show more"
const FILTER_PANEL_ID = "job-filters-panel";
const TOUCH = "min-h-11 sm:min-h-9";

export function Dashboard() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: KEY, queryFn: api.dashboard });
  const me = useMe();
  const emptyPlaces = useCoverageLine(Boolean(query.data?.has_areas));
  const stats = useStats(); // fetched together with the dashboard, not after it; the card just appears when it is there
  const { prefs, update } = usePreferences();
  // The header's search box sets this text (also through `?q=` in the address). It is the one thing not saved.
  const [q, setQ] = useState(() => (typeof window === "undefined" ? "" : (new URLSearchParams(window.location.search).get("q") ?? "")));
  const [message, setMessage] = useState("");
  const [checkingId, setCheckingId] = useState<number | null>(null);
  const [importing, setImporting] = useState(false);
  const [pendingCard, setPendingCard] = useState<string | null>(null);
  const [limit, setLimit] = useState(PAGE);
  // Looking after several jobs at once: the choice, the Undo bar after a move, and the "remove for good" confirmation.
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [undo, setUndo] = useState<{ key: number; text: string; ids: number[] } | null>(null);
  const [undoing, setUndoing] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [removing, setRemoving] = useState<{ ids: number[]; name: string } | null>(null);

  const refresh = useCallback(() => client.invalidateQueries({ queryKey: KEY }), [client]);
  const data = query.data;

  const scan = useRun<ScanStatus>({ read: dashboardApi.scanStatus, start: dashboardApi.startScan, initial: data?.scan, onFinished: refresh, onAdded: refresh });
  const liveness = useRun<Progress>({ read: api.livenessStatus, start: api.startLiveness, readOnMount: true, onFinished: refresh });

  // "Search for jobs now" from the palette: taken once, as soon as the dashboard has its answer.
  useEffect(() => {
    if (!data || !takeScanRequest()) return;
    if (data.can_scan && !scan.running && !scan.starting) scan.begin();
    else if (!data.can_scan) notify("Searching for jobs is not turned on for your account.", "info");
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onSearch = (e: Event) => setQ(String((e as CustomEvent<string>).detail ?? ""));
    window.addEventListener("so-search", onSearch);
    return () => window.removeEventListener("so-search", onSearch);
  }, []);

  // The saved choices as filters; an option that no longer exists (a country with no jobs left, a stage that was removed) reads as "any".
  const options = useMemo(
    () => ({
      countries: data ? [...new Set(data.jobs.map((j) => j.country).filter(Boolean))] : [],
      bands: data?.band_labels ?? [],
      stages: data ? data.buckets.map((b) => b.key) : [],
    }),
    [data],
  );
  const filters = useMemo(() => filtersFromPrefs(prefs, q, options.countries, options.bands, options.stages), [prefs, q, options]);
  const setFilter = useCallback(
    (patch: Partial<Filters>) => {
      if ("q" in patch) setQ(patch.q ?? "");
      const { q: _q, ...saved } = patch;
      void _q;
      // Worked out from the latest saved choices, so two quick changes (a filter, then another) both stay.
      update((current) => patchFromFilters(saved, filtersFromPrefs(current)));
      setLimit(PAGE);
    },
    [update],
  );
  const clearFilters = useCallback(() => {
    setQ("");
    update({ hide_weak: false, filters: { fit: "", match: "", work: "", country: "", posting: "", found: "" } });
    setLimit(PAGE);
  }, [update]);
  const showEverything = useCallback(() => {
    setQ("");
    update({ tab: "all", hide_weak: false, filters: { fit: "", match: "", work: "", country: "", posting: "", found: "" } });
    setLimit(PAGE);
  }, [update]);

  // Saved values that no longer exist are put right once, so they do not come back.
  const tidied = useRef(false);
  useEffect(() => {
    if (!data || tidied.current) return;
    tidied.current = true;
    const fixed = filtersFromPrefs(prefs, "", options.countries, options.bands, options.stages);
    const was = filtersFromPrefs(prefs, "");
    const change = patchFromFilters(
      Object.fromEntries((Object.keys(fixed) as (keyof Filters)[]).filter((k) => k !== "q" && fixed[k] !== was[k]).map((k) => [k, fixed[k]])) as Partial<Filters>,
      was,
    );
    if (Object.keys(change).length) update(change);
  }, [data, prefs, options, update]);

  const offerUndo = useCallback((text: string, ids: number[]) => setUndo({ key: Date.now(), text, ids }), []);
  // Choosing several jobs only makes sense in the list: the board hides it.
  useEffect(() => {
    if (prefs.view === "board" && selecting) {
      setSelecting(false);
      setSelected(new Set());
    }
  }, [prefs.view, selecting]);

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
    onSuccess: (done, _vars, ctx) => {
      const label = statusLabel(ctx?.status);
      setMessage(`Moved ${ctx?.job.role ?? "job"} to ${label}.`);
      if (done.changed && ctx) offerUndo(undoText(1, label, ctx.job.role), [ctx.job.id]);
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

  const jobs = useMemo(() => (data ? visibleJobs(data.jobs, filters) : []), [data, filters]);
  const selectedIds = useMemo(() => pruneSelection(selected, jobs), [selected, jobs]);

  // A link to one card (the next-step button, or #job-N in the address) must never land on a filtered-out job.
  const goToCard = useCallback(
    (id: string) => {
      const num = Number(id.replace("job-", ""));
      const at = jobs.findIndex((j) => j.id === num);
      if (at < 0) showEverything();
      else setLimit((n) => Math.max(n, at + 1));
      setPendingCard(id);
    },
    [jobs, showEverything],
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
  }, [pendingCard, data, jobs, limit]);

  // Cached answers are painted at once; the skeleton shows only when there is nothing yet.
  if (query.isPending || me.isPending) return <ScreenSkeleton />;
  if (query.isError || !data) return <ErrorBox message="We could not load your jobs." onRetry={() => query.refetch()} />;

  const view: ViewMode = prefs.view;
  const hiddenWeak = hiddenWeakCount(data.jobs, filters);
  const notForMe = notForMeStatus(data.statuses);
  const afterChange = () => Promise.all([refresh(), client.invalidateQueries({ queryKey: STATS_KEY })]);
  const leaveSelecting = () => {
    setSelecting(false);
    setSelected(new Set());
  };
  const doUndo = async () => {
    if (!undo) return;
    setUndoing(true);
    try {
      if (undo.ids.length === 1) await jobsApi.undoStatus(undo.ids[0]);
      else await jobsApi.bulkUndo(undo.ids);
      setMessage("Undone.");
      await refresh();
    } catch (e) {
      setMessage(errorText(e, "It is too late to undo that."));
    } finally {
      setUndo(null);
      setUndoing(false);
    }
  };
  const bulkMove = async (statusId: number, ids: number[] = [...selectedIds]) => {
    const target = data.statuses.find((s) => s.id === statusId);
    setBulkBusy(true);
    try {
      const done = await jobsApi.bulkStatus(ids, statusId);
      const label = statusLabel(target ?? done.status);
      const role = done.changed.length === 1 ? data.jobs.find((j) => j.id === done.changed[0])?.role : undefined;
      setMessage(movedText(done.changed.length, label, role));
      if (done.changed.length > 0) offerUndo(undoText(done.changed.length, label, role), done.changed);
      leaveSelecting();
      await afterChange();
    } catch (e) {
      setMessage(errorText(e, "That did not work. Nothing was changed."));
    } finally {
      setBulkBusy(false);
    }
  };
  const archive = async (ids: number[]) => {
    setBulkBusy(true);
    try {
      const done = ids.length === 1 ? await jobsApi.archive(ids[0]) : await jobsApi.bulkArchive(ids);
      const role = ids.length === 1 ? data.jobs.find((j) => j.id === ids[0])?.role : undefined;
      setMessage(archivedText(done.archived.length, role));
      leaveSelecting();
      await afterChange();
    } catch (e) {
      setMessage(errorText(e, "That did not work. Nothing was changed."));
    } finally {
      setBulkBusy(false);
    }
  };
  const restore = async (id: number) => {
    try {
      await jobsApi.restore(id);
      setMessage("Brought it back to your list.");
      await afterChange();
    } catch (e) {
      setMessage(errorText(e, "That did not work. Please try again."));
    }
  };
  const askRemove = (ids: number[], name = "") => setRemoving({ ids, name });
  const removeOne = (job: Job) => askRemove([job.id], `${job.role} at ${job.company}`);
  const notForMeOne = (job: Job) => {
    if (notForMe) onMove(job, notForMe.id);
  };
  const startSelecting = () => {
    if (view === "board") update({ view: "list" });
    setSelecting(true);
  };
  const tabs = stageChips(data.jobs, data.buckets);
  const activeTab = tabs.find((t) => t.key === filters.stage) ?? tabs[0];
  const filtered = isFiltered(filters);
  const extras: CardExtras = {
    judgeLabel: data.judge_label, prepEnabled: data.prep_enabled, paperlessUrl: data.paperless_on ? data.paperless_url : "", refresh,
    notForMe: notForMe ? notForMeOne : undefined, remove: removeOne, archive: (job) => void archive([job.id]),
  };
  const common = { statuses: data.statuses, extras, onMove, onCheckFit, checkingId };
  const scanView = scan.current;
  const comingUp = comingUpItems(data);
  const empty = emptyKind(data.jobs.length, jobs.length, scanView, activeTab.count);
  const boardColumns = filters.stage ? data.buckets.filter((b) => b.key === filters.stage) : data.buckets;
  const checkText = checkButtonText(liveness.running, liveness.starting, liveness.current?.done ?? 0, liveness.current?.total ?? 0);
  const searching = scan.running || scan.starting;

  const scanButton = data.can_scan ? (
    <Button onClick={scan.begin} disabled={searching} className={TOUCH} title="Searches every enabled job board for postings matching your target roles. Free -- no AI used.">
      {searching && <Spinner />}
      {scanButtonText(scanView, scan.starting)}
    </Button>
  ) : null;
  const addJob = (
    <Link to="/jobs/add" aria-label="Add job by hand" className={cn(buttonClass(data.can_scan ? "outline" : "primary"), TOUCH)}>
      Add job
    </Link>
  );
  const checkButton = (
    <Button variant="outline" onClick={liveness.begin} disabled={liveness.running || liveness.starting} className={TOUCH} title="Looks at each job link and tells you if the posting has closed.">
      {checkText}
    </Button>
  );
  const importButton = data.can_import ? (
    <Button variant="outline" onClick={importNow} disabled={importing} className={TOUCH}>
      {importing ? "Importing…" : "Import from career-ops"}
    </Button>
  ) : null;
  const paperlessLink = data.paperless_on ? (
    <a href={data.paperless_url} target="_blank" rel="noopener noreferrer" className={cn(buttonClass("outline"), TOUCH)}>
      Paperless
    </a>
  ) : null;

  // On a phone the main button stays and everything else moves into "More".
  const moreItems: MenuItem[] = [
    ...(data.can_scan ? [{ key: "add", label: "Add job", to: "/jobs/add" }] : []),
    { key: "check", label: checkText, onSelect: liveness.begin, disabled: liveness.running || liveness.starting },
    ...(data.can_import ? [{ key: "import", label: importing ? "Importing…" : "Import from career-ops", onSelect: importNow, disabled: importing }] : []),
    ...(data.paperless_on ? [{ key: "paperless", label: "Paperless", href: data.paperless_url }] : []),
    { key: "select", label: "Select several jobs", onSelect: startSelecting },
    { key: "export", label: "Export my jobs (CSV)", onSelect: () => window.location.assign(CSV_EXPORT_URL) },
  ];
  // On a wide screen the buttons stay, and these two sit in a small menu next to them.
  const moreWide: MenuItem[] = moreItems.filter((item) => item.key === "select" || item.key === "export");

  const announce = resultsText(jobs.length, activeTab.count, activeTab.label, view, filtered);
  const hasFollowups = data.followups.length > 0;
  const steps = checklistSteps(data);

  return (
    <div className="so-stack">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{data.greeting}</h1>
          <p className="text-theme-sm text-muted">{headerLine(data.stats, data.urgent_days, data.checked_at)}</p>
        </div>
        <div className="hidden flex-wrap gap-2 sm:flex">
          {scanButton}
          {addJob}
          {checkButton}
          {importButton}
          {paperlessLink}
          <ActionMenu label="More actions for your jobs" items={moreWide} variant="chevron" />
        </div>
        <div className="flex gap-2 sm:hidden">
          {scanButton ?? addJob}
          <ActionMenu label="More actions" items={moreItems} />
        </div>
      </header>
      <StaffBanners me={me.data} />
      <UpdateNotice me={me.data} />
      {data.ai_prompt?.show && !prefs.ai_prompt_dismissed && <AiKeyPrompt onDismiss={() => update({ ai_prompt_dismissed: true })} />}
      <TimezonePrompt />
      {liveness.error && (
        <p role="alert" className="text-theme-sm text-bad">
          {liveness.error}
        </p>
      )}

      <StatTiles data={data} />
      {troubleLine(data.source_trouble) && (
        <p className="text-theme-sm text-muted">
          {troubleLine(data.source_trouble)}{" "}
          <Link to="/sources" className="text-brand underline">
            See which
          </Link>
        </p>
      )}

      <div className="grid gap-[var(--stack-gap)] xl:grid-cols-[minmax(0,1fr)_20rem]">
        <aside aria-label="Next steps and your search" className="so-stack xl:col-start-2 xl:row-start-1">
          {showChecklist(steps, prefs.checklist_dismissed) && <ChecklistCard steps={steps} onDismiss={() => update({ checklist_dismissed: true })} />}
          {data.next_step && (
            <AsideCard title="Your next step" defaultOpen accent>
              <NextStepBody step={data.next_step} onCard={goToCard} />
            </AsideCard>
          )}
          {(data.worth_a_look ?? []).length > 0 && (
            <AsideCard title="Worth a look next" defaultOpen>
              <WorthBody items={data.worth_a_look ?? []} />
            </AsideCard>
          )}
          {stats.data?.goals && (
            <AsideCard title="Today" defaultOpen>
              <Suspense fallback={<p className="text-theme-sm text-muted">Loading…</p>}>
                <GoalsBody goals={stats.data.goals} />
              </Suspense>
            </AsideCard>
          )}
          {hasFollowups && (
            <AsideCard title="Time to follow up" defaultOpen>
              <FollowupsBody items={data.followups} onChanged={refresh} />
            </AsideCard>
          )}
          {(data.drafts ?? []).length > 0 && (
            <AsideCard title="Drafts waiting for you" defaultOpen>
              <DraftsBody items={data.drafts ?? []} onChanged={refresh} />
            </AsideCard>
          )}
          {comingUp.length > 0 && (
            <AsideCard title="Coming up">
              <ComingUpBody items={comingUp} />
            </AsideCard>
          )}
          {stats.data?.has_jobs && (
            <AsideCard title="This week">
              <ThisWeekBody stats={stats.data} />
            </AsideCard>
          )}
          <AsideCard title="Your search">
            <YourSearchBody summary={data.search_summary} emptyPlaces={emptyPlaces} />
          </AsideCard>
          <AsideCard title="Last search" defaultOpen={searching}>
            <LastSearchBody scan={scanView} starting={scan.starting} canScan={data.can_scan} />
          </AsideCard>
        </aside>

        <div className="so-stack min-w-0 xl:col-start-1 xl:row-start-1">
          <StageTabs tabs={tabs} active={activeTab.key} onChange={(key) => setFilter({ stage: key })} />
          <Toolbar
            filters={filters}
            set={setFilter}
            open={prefs.filters_open}
            onToggle={() => update((current) => ({ filters_open: !current.filters_open }))}
            panelId={FILTER_PANEL_ID}
            activeCount={activeFilterCount(filters)}
            view={view}
            onView={(v) => update({ view: v })}
          />
          {prefs.filters_open && (
            <FilterPanel id={FILTER_PANEL_ID} filters={filters} set={setFilter} reset={clearFilters} jobs={data.jobs} bandLabels={data.band_labels} inStage={activeTab.count} shown={jobs.length} hidden={hiddenWeak} />
          )}
          {(hiddenWeak > 0 || (view === "list" && !selecting && data.jobs.length > 0)) && (
            <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-theme-sm text-muted">
              <p>
                {/* with the filter panel open, the same words and button are in the panel's own "Showing N of M" line */}
                {!prefs.filters_open && weakLine(hiddenWeak)}{" "}
                {hiddenWeak > 0 && !prefs.filters_open && (
                  <button type="button" onClick={() => setFilter({ hideWeak: false })} className="min-h-11 text-brand underline sm:min-h-0">
                    Show them
                  </button>
                )}
              </p>
              {view === "list" && !selecting && data.jobs.length > 0 && (
                <Button variant="ghost" onClick={startSelecting} className="min-h-11 sm:min-h-9">
                  Select jobs
                </Button>
              )}
            </div>
          )}
          {selecting && view === "list" && (
            <SelectionBar
              count={selectedIds.size}
              total={jobs.length}
              allChecked={allSelected(selectedIds, jobs)}
              onToggleAll={() => setSelected(allSelected(selectedIds, jobs) ? new Set() : selectAllIn(jobs))}
              statuses={data.statuses}
              canNotForMe={!!notForMe}
              onNotForMe={() => notForMe && void bulkMove(notForMe.id)}
              onSetStatus={(id) => void bulkMove(id)}
              onArchive={() => void archive([...selectedIds])}
              onRemove={() => askRemove([...selectedIds])}
              onCancel={leaveSelecting}
              busy={bulkBusy}
            />
          )}

          <p role="status" aria-live="polite" className={message ? "text-theme-sm text-muted" : "sr-only"}>
            {message}
          </p>
          <p role="status" aria-live="polite" className="sr-only">
            {announce}
          </p>

          <div role="tabpanel" id={TAB_PANEL_ID} aria-labelledby={tabId(activeTab.key)} className="min-w-0">
            {empty ? (
              <div className="rounded-xl border border-dashed border-border p-8 text-center text-theme-sm text-muted">
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
                    , paste a link above, or{" "}
                    <Link to="/jobs/add" className="text-brand underline">
                      add one by hand
                    </Link>
                    .
                  </p>
                )}
                {empty === "no-jobs" && (
                  <>
                    <p>
                      No jobs yet. Paste a link above, or{" "}
                      <Link to="/jobs/add" className="text-brand underline">
                        add one by hand
                      </Link>
                      .
                    </p>
                    <p className="mt-1 text-theme-sm">
                      New here?{" "}
                      <Link to="/help" className="text-brand underline">
                        Read how StillOpen works
                      </Link>
                      .
                    </p>
                  </>
                )}
                {empty === "stage-empty" && <p>Nothing is in {activeTab.label} right now. That is fine. Pick another stage above.</p>}
                {empty === "no-matches" && (
                  <p>
                    No jobs match these filters.{" "}
                    <button type="button" onClick={showEverything} className="text-brand underline">
                      Show everything again
                    </button>
                  </p>
                )}
              </div>
            ) : view === "board" ? (
              <Suspense fallback={<div className="h-64 animate-pulse rounded-md bg-surface-2" role="status" aria-label="Loading the board" />}>
                <Board buckets={boardColumns} jobs={jobs} {...common} />
              </Suspense>
            ) : (
              <>
                <div className="so-stack">
                  {jobs.slice(0, limit).map((job) => (
                    <JobCard
                      key={job.id}
                      job={job}
                      statuses={data.statuses}
                      extras={extras}
                      onMove={onMove}
                      onCheckFit={onCheckFit}
                      checking={checkingId === job.id}
                      select={selecting ? { checked: selectedIds.has(job.id), onToggle: () => setSelected(toggleId(selectedIds, job.id)) } : undefined}
                    />
                  ))}
                </div>
                {jobs.length > limit && (
                  <div className="mt-4 text-center">
                    <Button variant="outline" className={TOUCH} onClick={() => setLimit((n) => n + PAGE)}>
                      Show {Math.min(PAGE, jobs.length - limit)} more ({jobs.length - limit} left)
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
      <ArchivedSection items={data.archived ?? []} onRestore={restore} />
      {undo && <UndoBar key={undo.key} text={undo.text} onUndo={doUndo} onDismiss={() => setUndo(null)} busy={undoing} />}
      {removing && (
        <RemoveDialog
          ids={removing.ids}
          name={removing.name}
          onClose={() => setRemoving(null)}
          onSoft={
            notForMe
              ? () => {
                  const ids = removing.ids;
                  setRemoving(null);
                  if (ids.length === 1) {
                    const job = data.jobs.find((j) => j.id === ids[0]);
                    if (job) onMove(job, notForMe.id);
                  } else {
                    void bulkMove(notForMe.id, ids);
                  }
                }
              : undefined
          }
          onRemoved={(count) => {
            const only = removing.ids.length === 1 ? data.jobs.find((j) => j.id === removing.ids[0])?.role : undefined;
            setRemoving(null);
            leaveSelecting();
            setUndo(null);
            notify(removedText(count, only));
            void afterChange();
          }}
        />
      )}
    </div>
  );
}
