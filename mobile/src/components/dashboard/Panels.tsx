import { useRouter, type Href } from "expo-router";
import React, { useState } from "react";
import { Linking, TouchableOpacity, View } from "react-native";
import Svg, { Rect } from "react-native-svg";

import {
  discardDraft, followupDone, followupSnooze, saveTimezone, scanLog,
  type ArchivedJob, type ComingUpItem, type DashStats, type DraftWaiting, type Followup, type Goals, type NextStep, type ScanLog, type ScanStatus, type WorthItem,
} from "../../api/dashboard";
import { checklistSteps, comingUpText, comingUpTo, deviceZone, entryText, scanPercent, scanTitle, shortDate, WORTH_WORD, worthTo, nextStepTarget, type ChecklistStep } from "../../screens/dashboard/logic";
import { radius } from "../../theme";
import { Button, confirm, Ionicons, notify, Text, useStyles, useTheme } from "../../ui";
import { errorText } from "../../ui/useApi";

/** A card that folds shut. Closed unless `defaultOpen`, so a phone is not a wall of cards. */
export function FoldCard({ title, defaultOpen = false, accent = false, badge, children }: { title: string; defaultOpen?: boolean; accent?: boolean; badge?: string; children: React.ReactNode }) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(defaultOpen);
  return (
    <View style={{ backgroundColor: colors.surface, borderRadius: radius.card, borderWidth: 1, borderColor: accent ? colors.accent : colors.border, marginBottom: 12 }}>
      <TouchableOpacity onPress={() => setOpen((v) => !v)} accessibilityRole="button" accessibilityState={{ expanded: open }} style={{ minHeight: 48, flexDirection: "row", alignItems: "center", paddingHorizontal: 16 }}>
        <Text style={{ flex: 1, fontSize: 15, fontWeight: "700" }}>
          {title}
          {badge ? <Text style={{ color: colors.textMuted, fontWeight: "400" }}>{`  ${badge}`}</Text> : null}
        </Text>
        <Ionicons name={open ? "chevron-up" : "chevron-down"} size={18} color={colors.textMuted} />
      </TouchableOpacity>
      {open ? <View style={{ paddingHorizontal: 16, paddingBottom: 14 }}>{children}</View> : null}
    </View>
  );
}

function useGo() {
  const router = useRouter();
  return (to: string) => router.push(to as Href);
}

export function StatTiles({ stats }: { stats: { total: number; submitted: number; average_match: number | null; urgent: number } }) {
  const { colors } = useTheme();
  const tiles = [
    { label: "Tracking", value: stats.total },
    { label: "Applied", value: stats.submitted },
    { label: "Average fit", value: stats.average_match != null ? `${stats.average_match}%` : "–" },
    { label: "Closing soon", value: stats.urgent },
  ];
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
      {tiles.map((t) => (
        <View key={t.label} style={{ flexGrow: 1, flexBasis: "46%", backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.card, padding: 14 }}>
          <Text style={{ fontSize: 24, fontWeight: "700" }}>{t.value}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 13 }}>{t.label}</Text>
        </View>
      ))}
    </View>
  );
}

export function Notice({ children }: { children: React.ReactNode }) {
  const { colors } = useTheme();
  return (
    <View style={{ backgroundColor: colors.accentSoft, borderWidth: 1, borderColor: colors.border, borderRadius: radius.card, padding: 14, marginBottom: 12 }}>{children}</View>
  );
}

export function ChecklistCard({ steps, onDismiss, onSearch }: { steps: ChecklistStep[]; onDismiss: () => void; onSearch: () => void }) {
  const { colors } = useTheme();
  const go = useGo();
  const done = steps.filter((x) => x.done).length;
  return (
    <FoldCard title="Getting started" badge={`${done} of ${steps.length} done`} defaultOpen>
      {steps.map((x) => (
        <View key={x.key} style={{ flexDirection: "row", alignItems: "center", minHeight: 44, gap: 10 }}>
          <Ionicons name={x.done ? "checkmark-circle" : "ellipse-outline"} size={22} color={x.done ? colors.good : colors.textMuted} />
          <Text style={{ flex: 1, textDecorationLine: x.done ? "line-through" : "none", color: x.done ? colors.textMuted : colors.text }}>{x.label}</Text>
          {!x.done ? (
            <TouchableOpacity hitSlop={8} onPress={() => (x.key === "search" ? onSearch() : x.to ? go(x.to) : undefined)} accessibilityRole="button" accessibilityLabel={x.cta}>
              <Text style={{ color: colors.accent, fontWeight: "700" }}>{x.cta}</Text>
            </TouchableOpacity>
          ) : null}
        </View>
      ))}
      <View style={{ marginTop: 8 }}>
        <Button label="Close this list" variant="ghost" onPress={onDismiss} />
      </View>
    </FoldCard>
  );
}

export function NextStepCard({ step, onCard }: { step: NextStep; onCard: (id: number) => void }) {
  const { colors } = useTheme();
  const go = useGo();
  const target = step.url ? nextStepTarget(step.url) : null;
  const press = () => {
    if (!target) return;
    if (target.kind === "app") go(target.to);
    else if (target.kind === "card") onCard(target.id);
    else void Linking.openURL(target.href);
  };
  return (
    <View style={{ backgroundColor: colors.accentSoft, borderWidth: 1, borderColor: colors.accent, borderRadius: radius.card, padding: 16, marginBottom: 12 }}>
      <Text style={{ color: colors.textMuted, fontSize: 12, fontWeight: "700", marginBottom: 4 }}>YOUR NEXT STEP</Text>
      <Text style={{ fontSize: 16, fontWeight: "700" }}>{step.headline}</Text>
      <Text style={{ color: colors.textMuted, marginTop: 2 }}>{step.body}</Text>
      {target && step.label ? (
        <View style={{ marginTop: 12 }}>
          <Button label={step.label} onPress={press} />
        </View>
      ) : null}
    </View>
  );
}

export function WorthCard({ items }: { items: WorthItem[] }) {
  const { colors } = useTheme();
  const go = useGo();
  return (
    <FoldCard title="Worth a look next" defaultOpen>
      {items.map((i) => (
        <TouchableOpacity key={`${i.kind}-${i.job_id}`} onPress={() => go(worthTo(i))} accessibilityRole="button" accessibilityLabel={`${WORTH_WORD[i.kind] ?? ""}: ${i.label}`} style={{ minHeight: 48, justifyContent: "center", paddingVertical: 6 }}>
          <Text style={{ fontWeight: "600" }}>{i.label}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 12 }}>{i.reason}</Text>
        </TouchableOpacity>
      ))}
    </FoldCard>
  );
}

export function ComingUpCard({ items }: { items: ComingUpItem[] }) {
  const { colors } = useTheme();
  const go = useGo();
  return (
    <FoldCard title="Coming up">
      {items.map((i) => (
        <TouchableOpacity key={`${i.kind}-${i.job_id}-${i.when}`} onPress={() => go(comingUpTo(i))} style={{ minHeight: 44, justifyContent: "center" }}>
          <Text style={{ color: colors.text }}>{comingUpText(i)}</Text>
        </TouchableOpacity>
      ))}
      <View style={{ flexDirection: "row", gap: 16, marginTop: 6 }}>
        {items.some((i) => i.kind === "interview") ? (
          <TouchableOpacity onPress={() => go("/interviews")} hitSlop={8}>
            <Text style={{ color: colors.accent, fontWeight: "600" }}>All interviews</Text>
          </TouchableOpacity>
        ) : null}
        {items.some((i) => i.kind === "offer") ? (
          <TouchableOpacity onPress={() => go("/offers")} hitSlop={8}>
            <Text style={{ color: colors.accent, fontWeight: "600" }}>All offers</Text>
          </TouchableOpacity>
        ) : null}
      </View>
    </FoldCard>
  );
}

export function FollowupsCard({ items, onChanged }: { items: Followup[]; onChanged: () => Promise<unknown> | void }) {
  const { colors } = useTheme();
  const go = useGo();
  const [busy, setBusy] = useState<number | null>(null);
  const act = async (f: Followup, what: "done" | "snooze") => {
    setBusy(f.id);
    try {
      if (what === "done") await followupDone(f.id);
      else await followupSnooze(f.id, 3);
      notify(what === "done" ? `Marked the follow-up for ${f.company} as done.` : `We will remind you about ${f.company} again in 3 days.`);
      await onChanged();
    } catch (e) {
      notify(errorText(e));
    } finally {
      setBusy(null);
    }
  };
  return (
    <FoldCard title="Time to follow up" badge={String(items.length)} defaultOpen>
      {items.map((f) => (
        <View key={f.id} style={{ marginBottom: 12 }}>
          <TouchableOpacity onPress={() => go(`/jobs/${f.id}/apply`)} accessibilityRole="button">
            <Text style={{ fontWeight: "600" }}>{`${f.company}, ${f.role}`}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 12 }}>{`Due ${shortDate(f.follow_up_date)}${f.applied_date ? `, applied ${shortDate(f.applied_date)}` : ""}`}</Text>
          </TouchableOpacity>
          <View style={{ flexDirection: "row", gap: 8, marginTop: 6 }}>
            <Button label="Done" variant="secondary" disabled={busy === f.id} onPress={() => act(f, "done")} style={{ flex: 1 }} />
            <Button label="In 3 days" variant="secondary" disabled={busy === f.id} onPress={() => act(f, "snooze")} style={{ flex: 1 }} />
          </View>
        </View>
      ))}
    </FoldCard>
  );
}

export function DraftsCard({ items, onChanged }: { items: DraftWaiting[]; onChanged: () => Promise<unknown> | void }) {
  const { colors } = useTheme();
  const go = useGo();
  const [busy, setBusy] = useState<number | null>(null);
  const discard = async (d: DraftWaiting) => {
    if (!(await confirm(`Discard the draft CV for ${d.company}?`, "Your own CV is not touched.", "Discard"))) return;
    setBusy(d.id);
    try {
      await discardDraft(d.id);
      notify(`Discarded the draft for ${d.company}.`);
      await onChanged();
    } catch (e) {
      notify(errorText(e));
    } finally {
      setBusy(null);
    }
  };
  return (
    <FoldCard title="Drafts waiting for you" badge={String(items.length)} defaultOpen>
      <Text style={{ color: colors.textMuted, fontSize: 12, marginBottom: 8 }}>CV drafts we prepared for new jobs. Nothing is approved or sent until you check it.</Text>
      {items.map((d) => (
        <View key={d.id} style={{ marginBottom: 12 }}>
          <Text style={{ fontWeight: "600" }}>{`${d.company}, ${d.role}`}</Text>
          {d.flagged_count > 0 ? <Text style={{ color: colors.warn, fontSize: 12 }}>{`${d.flagged_count} ${d.flagged_count === 1 ? "claim needs" : "claims need"} your check`}</Text> : null}
          <View style={{ flexDirection: "row", gap: 8, marginTop: 6 }}>
            <Button label="Review" variant="secondary" onPress={() => go(`/cv/${d.id}`)} style={{ flex: 1 }} />
            <Button label="Discard" variant="danger" disabled={busy === d.id} onPress={() => discard(d)} style={{ flex: 1 }} />
          </View>
        </View>
      ))}
    </FoldCard>
  );
}

/** Today's goals, the streak and the 30-day funnel: small bars drawn with react-native-svg. */
export function GoalsCard({ goals, funnel }: { goals?: Goals | null; funnel?: DashStats["funnel"] }) {
  const { colors } = useTheme();
  const stages = funnel?.["30"]?.stages ?? [];
  const max = Math.max(1, ...stages.map((x) => x.count));
  const bar = (label: string, value: number, target: number) => {
    const pct = target > 0 ? Math.min(1, value / target) : 0;
    return (
      <View key={label} style={{ marginBottom: 10 }}>
        <Text style={{ fontSize: 13 }}>{`${label}: ${value} of ${target}`}</Text>
        <Svg width="100%" height={10} viewBox="0 0 100 10" preserveAspectRatio="none" accessibilityLabel={`${label}: ${value} of ${target}`}>
          <Rect x="0" y="0" width="100" height="10" rx="5" fill={colors.surfaceAlt} />
          <Rect x="0" y="0" width={Math.max(pct * 100, pct > 0 ? 4 : 0)} height="10" rx="5" fill={colors.accent} />
        </Svg>
      </View>
    );
  };
  if (!goals && stages.every((x) => x.count === 0)) return null;
  return (
    <FoldCard title={goals ? "Today" : "Last 30 days"} defaultOpen={!!goals}>
      {goals ? (
        <>
          {goals.daily_target > 0 ? bar("Today", goals.today, goals.daily_target) : null}
          {goals.weekly_target > 0 ? bar("This week", goals.week, goals.weekly_target) : null}
          <Text style={{ color: colors.textMuted, fontSize: 12, marginBottom: 6 }}>{`Streak: ${goals.current_streak} ${goals.current_streak === 1 ? "day" : "days"} (best ${goals.best_streak}).`}</Text>
        </>
      ) : null}
      {stages.length > 0 ? (
        <View>
          {stages.map((x, i) => (
            <View key={x.key} style={{ marginBottom: 6 }}>
              <Text style={{ fontSize: 12, color: colors.textMuted }}>{`${x.label}: ${x.count}`}</Text>
              <Svg width="100%" height={8} viewBox="0 0 100 8" preserveAspectRatio="none">
                <Rect x="0" y="0" width={Math.max((x.count / max) * 100, x.count > 0 ? 3 : 0)} height="8" rx="4" fill={colors.chart[i % colors.chart.length]} />
              </Svg>
            </View>
          ))}
        </View>
      ) : null}
    </FoldCard>
  );
}

export function ThisWeekCard({ stats }: { stats: DashStats }) {
  const { colors } = useTheme();
  const go = useGo();
  if (!stats.has_jobs || !stats.week) return null;
  const tiles = [
    { label: "New jobs", value: stats.week.found },
    { label: "Fits checked", value: stats.week.checked },
    { label: "Applied", value: stats.week.applied },
    { label: "Waiting for a reply", value: stats.waiting?.count ?? 0 },
  ];
  return (
    <FoldCard title="This week">
      {stats.summary_text ? <Text style={{ marginBottom: 8 }}>{stats.summary_text}</Text> : null}
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
        {tiles.map((t) => (
          <View key={t.label} style={{ flexBasis: "47%", flexGrow: 1, backgroundColor: colors.surfaceAlt, borderRadius: radius.control, padding: 10 }}>
            <Text style={{ fontSize: 20, fontWeight: "700" }}>{t.value}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 12 }}>{t.label}</Text>
          </View>
        ))}
      </View>
      <TouchableOpacity onPress={() => go("/insights")} style={{ minHeight: 44, justifyContent: "center" }}>
        <Text style={{ color: colors.accent, fontWeight: "600" }}>See all your numbers</Text>
      </TouchableOpacity>
    </FoldCard>
  );
}

/** The last search: progress while it runs, a one-line result after, and the log of each source on request. */
export function LastSearchCard({ scan, starting, canScan, error }: { scan: ScanStatus | null; starting: boolean; canScan: boolean; error: string }) {
  const { colors } = useTheme();
  const [log, setLog] = useState<ScanLog | null>(null);
  const [logError, setLogError] = useState("");
  const running = starting || !!scan?.running;
  const loadLog = async () => {
    setLogError("");
    try {
      setLog(await scanLog());
    } catch (e) {
      setLogError(errorText(e));
    }
  };
  return (
    <FoldCard title="Last search" defaultOpen={running || !!error}>
      {!scan && !starting ? (
        <Text style={{ color: colors.textMuted }}>{canScan ? "You have not searched yet. Press Find jobs now and we look through your job sources for roles that fit you." : "No search has run yet."}</Text>
      ) : (
        <View>
          <Text style={{ fontWeight: "600" }}>{starting && !scan?.running ? "Starting the search…" : scan ? scanTitle(scan) : ""}</Text>
          {running ? (
            <>
              <Svg width="100%" height={8} viewBox="0 0 100 8" preserveAspectRatio="none" style={{ marginTop: 8 }}>
                <Rect x="0" y="0" width="100" height="8" rx="4" fill={colors.surfaceAlt} />
                <Rect x="0" y="0" width={starting && !scan?.running ? 3 : Math.max(3, scan ? scanPercent(scan) : 3)} height="8" rx="4" fill={colors.accent} />
              </Svg>
              <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 6 }}>Usually about a minute. You can keep using StillOpen: the first jobs show up here by themselves.</Text>
            </>
          ) : null}
          {scan?.note ? <Text style={{ color: colors.textMuted, marginTop: 6 }}>{scan.note}</Text> : null}
          {scan?.error ? <Text style={{ color: colors.danger, marginTop: 6 }}>{scan.error}</Text> : null}
        </View>
      )}
      {error ? <Text style={{ color: colors.danger, marginTop: 6 }}>{error}</Text> : null}
      {scan ? (
        <View style={{ marginTop: 8 }}>
          <Button label={log ? "Refresh the log" : "Where it searched"} variant="ghost" onPress={loadLog} />
          {logError ? <Text style={{ color: colors.danger, fontSize: 12 }}>{logError}</Text> : null}
          {log?.entries.length === 0 ? <Text style={{ color: colors.textMuted, fontSize: 12 }}>No sources checked yet.</Text> : null}
          {log?.entries.map((e, i) => (
            <View key={`${e.source}-${i}`} style={{ marginTop: 6 }}>
              <Text style={{ fontSize: 13 }}>{`${e.source} (${e.connector})`}</Text>
              <Text style={{ fontSize: 12, color: e.error ? colors.danger : colors.textMuted }}>{entryText(e)}</Text>
            </View>
          ))}
        </View>
      ) : null}
    </FoldCard>
  );
}

/** One-time suggestion to follow this device's time zone. Nothing changes unless the person presses the button. */
export function TimezonePrompt({ saved, site, onDone, onKeep }: { saved: string; site: string; onDone: () => void; onKeep: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const device = deviceZone();
  return (
    <Notice>
      <Text style={{ fontWeight: "700" }}>Is this the right time zone for you?</Text>
      <Text style={{ marginTop: 4 }}>{`This phone says ${device}, but your days (today's date, follow-ups, deadlines) follow ${saved || site}. Switch if you want them to follow where you are.`}</Text>
      {error ? <Text style={{ marginTop: 4 }}>{error}</Text> : null}
      <View style={{ flexDirection: "row", gap: 8, marginTop: 10 }}>
        <Button
          label={`Use ${device}`}
          busy={busy}
          style={{ flex: 1 }}
          onPress={async () => {
            setBusy(true);
            setError("");
            try {
              await saveTimezone(device);
              onDone();
            } catch (e) {
              setError(errorText(e));
            } finally {
              setBusy(false);
            }
          }}
        />
        <Button label={`Keep ${saved || site}`} variant="secondary" style={{ flex: 1 }} onPress={onKeep} />
      </View>
    </Notice>
  );
}

/** Jobs the person archived: kept out of the list and its counts, each with a way back. */
export function ArchivedSection({ items, onRestore }: { items: ArchivedJob[]; onRestore: (id: number) => void }) {
  const { colors } = useTheme();
  if (items.length === 0) return null;
  return (
    <FoldCard title="Archived" badge={String(items.length)}>
      <Text style={{ color: colors.textMuted, fontSize: 12, marginBottom: 8 }}>These are kept, but they are not on your list or in your numbers. Restore one to bring it back exactly as it was.</Text>
      {items.map((a) => (
        <View key={a.id} style={{ flexDirection: "row", alignItems: "center", gap: 8, minHeight: 52 }}>
          <View style={{ flex: 1 }}>
            <Text style={{ fontWeight: "600" }}>{a.role}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 12 }}>{`${a.company} · ${a.status}`}</Text>
          </View>
          <Button label="Restore" variant="secondary" onPress={() => onRestore(a.id)} />
        </View>
      ))}
    </FoldCard>
  );
}

export { checklistSteps };
