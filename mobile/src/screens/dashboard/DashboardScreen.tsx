import { useFocusEffect, useRouter, type Href } from "expo-router";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RefreshControl, ScrollView, TouchableOpacity, View } from "react-native";

import {
  archiveJob, bulkArchive, bulkPreview, bulkRemove, bulkStatus, bulkUndo, evaluate, getDashboard, getDashStats, getZones, livenessStatus, removeJob, removePreview,
  restoreJob, scanStatus, setStatus, startLiveness, startScan, undoStatus, type Dashboard, type DashStats, type Job, type Progress, type ScanStatus, type ZoneInfo,
} from "../../api/dashboard";
import { Board } from "../../components/dashboard/Board";
import { JobCard, type CardExtras } from "../../components/dashboard/JobCard";
import {
  ArchivedSection, ChecklistCard, ComingUpCard, DraftsCard, FollowupsCard, GoalsCard, LastSearchCard, NextStepCard, Notice, StatTiles, ThisWeekCard, TimezonePrompt, WorthCard,
} from "../../components/dashboard/Panels";
import { FilterPanel, SelectionBar, StageTabs, Toolbar, UndoBar } from "../../components/dashboard/Toolbar";
import { Button, confirm, Empty, ErrorBox, Loading, Screen, Text, useTheme } from "../../ui";
import { errorText } from "../../ui/useApi";
import { usePreferences, useRun } from "./hooks";
import {
  activeFilterCount, allSelected, archivedText, checkButtonText, checklistSteps, comingUpItems, deviceZone, emptyKind, filtersFromPrefs, headerLine, hiddenWeakCount, movedText,
  notForMeStatus, patchFromFilters, pruneSelection, removedText, scanButtonText, shouldSuggestZone, showChecklist, stageChips, statusLabel, toggleId, troubleLine, undoText, visibleJobs, weakLine,
  type Filters,
} from "./logic";

const PAGE = 50;

export default function DashboardScreen() {
  const router = useRouter();
  const { colors } = useTheme();
  const go = (to: string) => router.push(to as Href);
  const { prefs, update } = usePreferences();
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [stats, setStats] = useState<DashStats | null>(null);
  const [zone, setZone] = useState<ZoneInfo | null>(null);
  const [q, setQ] = useState("");
  const [message, setMessage] = useState("");
  const [checkingId, setCheckingId] = useState<number | null>(null);
  const [limit, setLimit] = useState(PAGE);
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [undo, setUndo] = useState<{ key: number; text: string; ids: number[] } | null>(null);
  const [undoing, setUndoing] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);
  const scroller = useRef<React.ComponentRef<typeof ScrollView>>(null);
  const cardY = useRef(0);

  const reload = useCallback(async () => {
    try {
      setData(await getDashboard());
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
    getDashStats().then(setStats).catch(() => undefined);
  }, []);

  useFocusEffect(
    useCallback(() => {
      void reload();
      getZones().then((m) => setZone({ timezone: m.timezone ?? "", site_timezone: m.site_timezone ?? "" })).catch(() => undefined);
    }, [reload]),
  );

  const refresh = async () => {
    setRefreshing(true);
    await reload();
    setRefreshing(false);
  };

  const scan = useRun<ScanStatus>({ read: scanStatus, start: startScan, initial: data?.scan, onFinished: reload, onAdded: reload });
  const liveness = useRun<Progress>({ read: livenessStatus, start: startLiveness, readOnMount: true, onFinished: reload });

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
      if (Object.keys(saved).length) update((current) => patchFromFilters(saved, filtersFromPrefs(current)));
      setLimit(PAGE);
    },
    [update],
  );
  const noFilters = { fit: "", match: "", work: "", country: "", posting: "", found: "" };
  const clearFilters = () => {
    setQ("");
    update({ hide_weak: false, filters: noFilters });
    setLimit(PAGE);
  };
  const showEverything = () => {
    setQ("");
    update({ tab: "all", hide_weak: false, filters: noFilters });
    setLimit(PAGE);
  };

  const jobs = useMemo(() => (data ? visibleJobs(data.jobs, filters) : []), [data, filters]);
  const selectedIds = useMemo(() => pruneSelection(selected, jobs), [selected, jobs]);

  const offerUndo = (text: string, ids: number[]) => setUndo({ key: Date.now(), text, ids });
  const leaveSelecting = () => {
    setSelecting(false);
    setSelected(new Set());
  };

  useEffect(() => {
    if (prefs.view === "board" && selecting) {
      setSelecting(false);
      setSelected(new Set());
    }
  }, [prefs.view, selecting]);

  if (!data && !error) return <Loading />;
  if (!data)
    return (
      <Screen scroll={false}>
        <View style={{ padding: 16 }}>
          <ErrorBox message={error ?? "We could not load your jobs."} onRetry={reload} />
        </View>
      </Screen>
    );

  const view = prefs.view;
  const notForMe = notForMeStatus(data.statuses);
  const hiddenWeak = hiddenWeakCount(data.jobs, filters);
  const tabs = stageChips(data.jobs, data.buckets);
  const activeTab = tabs.find((t) => t.key === filters.stage) ?? tabs[0];
  const scanView = scan.current;
  const searching = scan.running || scan.starting;
  const empty = emptyKind(data.jobs.length, jobs.length, scanView, activeTab.count);
  const boardColumns = filters.stage ? data.buckets.filter((b) => b.key === filters.stage) : data.buckets;
  const steps = checklistSteps(data);
  const comingUp = comingUpItems(data);
  const checkText = checkButtonText(liveness.running, liveness.starting, liveness.current?.done ?? 0, liveness.current?.total ?? 0);

  const onMove = async (job: Job, statusId: number) => {
    if (job.status_id === statusId) return;
    const target = data.statuses.find((s) => s.id === statusId);
    const before = data;
    if (target) setData({ ...data, jobs: data.jobs.map((j) => (j.id === job.id ? { ...j, status_id: target.id, bucket_key: target.bucket_key } : j)) });
    try {
      const done = await setStatus(job.id, statusId);
      const label = statusLabel(target);
      setMessage(`Moved ${job.role} to ${label}.`);
      if (done.changed) offerUndo(undoText(1, label, job.role), [job.id]);
      await reload();
    } catch (e) {
      setData(before);
      setMessage(`Could not move ${job.role}: ${errorText(e)}`);
    }
  };

  const onCheckFit = async (job: Job) => {
    setCheckingId(job.id);
    setMessage("");
    try {
      const r = await evaluate(job.id);
      setMessage(`${job.role} at ${job.company}: ${r.match_percent}% match.`);
      await reload();
    } catch (e) {
      setMessage(errorText(e));
    } finally {
      setCheckingId(null);
    }
  };

  const doUndo = async () => {
    if (!undo) return;
    setUndoing(true);
    try {
      if (undo.ids.length === 1) await undoStatus(undo.ids[0]);
      else await bulkUndo(undo.ids);
      setMessage("Undone.");
      await reload();
    } catch (e) {
      setMessage(errorText(e));
    } finally {
      setUndo(null);
      setUndoing(false);
    }
  };

  const bulkMove = async (statusId: number, ids: number[] = [...selectedIds]) => {
    const target = data.statuses.find((s) => s.id === statusId);
    setBulkBusy(true);
    try {
      const done = await bulkStatus(ids, statusId);
      const label = statusLabel(target ?? done.status);
      const role = done.changed.length === 1 ? data.jobs.find((j) => j.id === done.changed[0])?.role : undefined;
      setMessage(movedText(done.changed.length, label, role));
      if (done.changed.length > 0) offerUndo(undoText(done.changed.length, label, role), done.changed);
      leaveSelecting();
      await reload();
    } catch (e) {
      setMessage(errorText(e));
    } finally {
      setBulkBusy(false);
    }
  };

  const archive = async (ids: number[]) => {
    setBulkBusy(true);
    try {
      const done = ids.length === 1 ? await archiveJob(ids[0]) : await bulkArchive(ids);
      const role = ids.length === 1 ? data.jobs.find((j) => j.id === ids[0])?.role : undefined;
      setMessage(archivedText(done.archived.length, role));
      leaveSelecting();
      await reload();
    } catch (e) {
      setMessage(errorText(e));
    } finally {
      setBulkBusy(false);
    }
  };

  const restore = async (id: number) => {
    try {
      await restoreJob(id);
      setMessage("Brought it back to your list.");
      await reload();
    } catch (e) {
      setMessage(errorText(e));
    }
  };

  /** Remove for good, after saying exactly what goes with it (the sentence comes from the server). */
  const remove = async (ids: number[], name = "") => {
    let text = "This cannot be undone.";
    try {
      const p = ids.length > 1 ? await bulkPreview(ids) : await removePreview(ids[0]);
      text = `${p.text}\n\n${p.keeps}`;
    } catch {
      /* the person can still remove it */
    }
    if (!(await confirm(ids.length > 1 ? `Remove ${ids.length} jobs for good?` : `Remove ${name} for good?`, text, "Remove for good"))) return;
    setBulkBusy(true);
    try {
      const done = ids.length > 1 ? await bulkRemove(ids) : await removeJob(ids[0]);
      const only = ids.length === 1 ? data.jobs.find((j) => j.id === ids[0])?.role : undefined;
      setUndo(null);
      leaveSelecting();
      setMessage(removedText(done.removed, only));
      await reload();
    } catch (e) {
      setMessage(errorText(e));
    } finally {
      setBulkBusy(false);
    }
  };

  const extras: CardExtras = {
    judgeLabel: data.judge_label,
    prepEnabled: data.prep_enabled,
    notForMe: notForMe ? (job) => void onMove(job, notForMe.id) : undefined,
    archive: (job) => void archive([job.id]),
    remove: (job) => void remove([job.id], `${job.role} at ${job.company}`),
  };

  const goToCard = (id: number) => {
    const at = jobs.findIndex((j) => j.id === id);
    if (at < 0) showEverything();
    else setLimit((n) => Math.max(n, at + 1));
    scroller.current?.scrollTo({ y: cardY.current, animated: true });
  };

  const showZone = zone && shouldSuggestZone({ device: deviceZone(), saved: zone.timezone, site: zone.site_timezone, dismissed: prefs.tz_prompt_dismissed });
  const trouble = troubleLine(data.source_trouble);

  return (
    <Screen scroll={false} padded={false}>
      <ScrollView
        ref={scroller}
        contentContainerStyle={{ padding: 16, paddingBottom: 90 }}
        keyboardShouldPersistTaps="handled"
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.accent} />}
      >
        <Text style={{ fontSize: 26, fontWeight: "700", letterSpacing: -0.4 }}>{data.greeting}</Text>
        <Text style={{ color: colors.textMuted, marginTop: 2, marginBottom: 12 }}>{headerLine(data.stats, data.urgent_days, data.checked_at)}</Text>

        <View style={{ flexDirection: "row", gap: 8, marginBottom: 8 }}>
          {data.can_scan ? <Button label={scanButtonText(scanView, scan.starting)} busy={searching} style={{ flex: 1 }} onPress={scan.begin} icon="search" /> : null}
          <Button label="Add job" variant={data.can_scan ? "secondary" : "primary"} style={{ flex: 1 }} onPress={() => go("/jobs/add")} icon="add" />
        </View>
        <Button label={checkText} variant="ghost" disabled={liveness.running || liveness.starting} onPress={liveness.begin} />
        {scan.error ? <Text style={{ color: colors.danger, marginBottom: 8 }}>{scan.error}</Text> : null}
        {liveness.error ? <Text style={{ color: colors.danger, marginBottom: 8 }}>{liveness.error}</Text> : null}

        {data.ai_prompt?.show && !prefs.ai_prompt_dismissed ? (
          <Notice>
            <Text style={{ fontWeight: "700" }}>Add a free Google AI Studio key</Text>
            <Text style={{ color: colors.textMuted, marginTop: 4 }}>With your own key StillOpen can read each job and your CV carefully. Without it you still get the free keyword check, so you can come back to this later.</Text>
            <View style={{ flexDirection: "row", gap: 8, marginTop: 10 }}>
              <Button label="Add my key" style={{ flex: 1 }} onPress={() => go("/profile/ai")} />
              <Button label="Not now" variant="secondary" style={{ flex: 1 }} onPress={() => update({ ai_prompt_dismissed: true })} />
            </View>
          </Notice>
        ) : null}
        {showZone && zone ? (
          <TimezonePrompt
            saved={zone.timezone}
            site={zone.site_timezone}
            onDone={() => {
              update({ tz_prompt_dismissed: true });
              setZone({ ...zone, timezone: deviceZone() });
              void reload();
            }}
            onKeep={() => update({ tz_prompt_dismissed: true })}
          />
        ) : null}

        <StatTiles stats={data.stats} />
        {trouble ? (
          <TouchableOpacity onPress={() => go("/sources")} style={{ marginBottom: 12, minHeight: 44, justifyContent: "center" }}>
            <Text style={{ color: colors.textMuted }}>
              {`${trouble} `}
              <Text style={{ color: colors.accent }}>See which</Text>
            </Text>
          </TouchableOpacity>
        ) : null}

        {showChecklist(steps, prefs.checklist_dismissed) ? (
          <ChecklistCard steps={steps} onDismiss={() => update({ checklist_dismissed: true })} onSearch={() => (data.can_scan ? void scan.begin() : go("/profile"))} />
        ) : null}
        {data.next_step ? <NextStepCard step={data.next_step} onCard={goToCard} /> : null}
        {(data.worth_a_look ?? []).length > 0 ? <WorthCard items={data.worth_a_look ?? []} /> : null}
        {data.followups.length > 0 ? <FollowupsCard items={data.followups} onChanged={reload} /> : null}
        {(data.drafts ?? []).length > 0 ? <DraftsCard items={data.drafts ?? []} onChanged={reload} /> : null}
        {comingUp.length > 0 ? <ComingUpCard items={comingUp} /> : null}
        {stats ? <GoalsCard goals={stats.goals} funnel={stats.funnel} /> : null}
        {stats ? <ThisWeekCard stats={stats} /> : null}
        <LastSearchCard scan={scanView} starting={scan.starting} canScan={data.can_scan} error="" />

        <View onLayout={(e) => (cardY.current = e.nativeEvent.layout.y)}>
          <Text style={{ fontSize: 18, fontWeight: "700", marginTop: 8, marginBottom: 8 }}>Your jobs</Text>
          <StageTabs tabs={tabs} active={activeTab.key} onChange={(key) => setFilter({ stage: key })} />
          <Toolbar filters={filters} set={setFilter} open={prefs.filters_open} onToggle={() => update((c) => ({ filters_open: !c.filters_open }))} activeCount={activeFilterCount(filters)} view={view} onView={(v) => update({ view: v })} />
          {prefs.filters_open ? (
            <FilterPanel filters={filters} set={setFilter} reset={clearFilters} jobs={data.jobs} bandLabels={data.band_labels} inStage={activeTab.count} shown={jobs.length} hidden={hiddenWeak} />
          ) : null}
          {hiddenWeak > 0 && !prefs.filters_open ? (
            <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 6 }}>
              <Text style={{ color: colors.textMuted, flex: 1 }}>{weakLine(hiddenWeak)}</Text>
              <Button label="Show them" variant="ghost" onPress={() => setFilter({ hideWeak: false })} />
            </View>
          ) : null}
          {view === "list" && !selecting && data.jobs.length > 0 ? <Button label="Select jobs" variant="ghost" onPress={() => setSelecting(true)} /> : null}
          {selecting && view === "list" ? (
            <SelectionBar
              count={selectedIds.size}
              total={jobs.length}
              allChecked={allSelected(selectedIds, jobs)}
              onToggleAll={() => setSelected(allSelected(selectedIds, jobs) ? new Set() : new Set(jobs.map((j) => j.id)))}
              statuses={data.statuses}
              canNotForMe={!!notForMe}
              onNotForMe={() => notForMe && void bulkMove(notForMe.id)}
              onSetStatus={(id) => void bulkMove(id)}
              onArchive={() => void archive([...selectedIds])}
              onRemove={() => void remove([...selectedIds])}
              onCancel={leaveSelecting}
              busy={bulkBusy}
            />
          ) : null}
          {message ? (
            <Text accessibilityLiveRegion="polite" style={{ color: colors.textMuted, marginBottom: 8 }}>
              {message}
            </Text>
          ) : null}

          {empty ? (
            <View>
              {empty === "searching" ? <Empty title="Searching for you" hint="We are searching your job sources for roles that fit you. They will appear here in a minute, with nothing for you to do." /> : null}
              {empty === "nothing-matched" ? <Empty title="Nothing new matched yet" hint="Check your roles and places in Profile, or add a job by hand." action={{ label: "Add a job", onPress: () => go("/jobs/add") }} /> : null}
              {empty === "no-jobs" ? <Empty title="No jobs yet" hint={data.can_scan ? "Press Find jobs now, or add one by hand." : "Add your first job by hand, or paste a link."} action={{ label: "Add a job", onPress: () => go("/jobs/add") }} /> : null}
              {empty === "stage-empty" ? <Empty title={`Nothing is in ${activeTab.label} right now`} hint="That is fine. Pick another stage above." /> : null}
              {empty === "no-matches" ? <Empty title="No jobs match these filters" hint="Clear the filters to see everything again." action={{ label: "Show everything again", onPress: showEverything }} /> : null}
            </View>
          ) : view === "board" ? (
            <Board buckets={boardColumns} jobs={jobs} statuses={data.statuses} extras={extras} onMove={onMove} onCheckFit={onCheckFit} checkingId={checkingId} />
          ) : (
            <>
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
              {jobs.length > limit ? <Button label={`Show ${Math.min(PAGE, jobs.length - limit)} more (${jobs.length - limit} left)`} variant="secondary" onPress={() => setLimit((n) => n + PAGE)} /> : null}
            </>
          )}
        </View>

        <View style={{ marginTop: 12 }}>
          <ArchivedSection items={data.archived ?? []} onRestore={restore} />
        </View>
      </ScrollView>
      {undo ? <UndoBar key={undo.key} text={undo.text} onUndo={doUndo} onDismiss={() => setUndo(null)} busy={undoing} /> : null}
    </Screen>
  );
}
