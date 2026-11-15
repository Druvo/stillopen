import { useRouter, type Href } from "expo-router";
import React, { useMemo, useState } from "react";
import { Linking, StyleSheet, TouchableOpacity, View } from "react-native";

import { createPrep, tailorCv, type Job, type StatusInfo } from "../../api/dashboard";
import { applyHref, appliedParts, cvBadgeText, deadlineText, FIT_BADGE_TEXT, livingBadge, repostTitle, statusLabel, truncate } from "../../screens/dashboard/logic";
import { radius } from "../../theme";
import { Ionicons, Text, useStyles, useTheme } from "../../ui";
import { errorText } from "../../ui/useApi";
import { MatchRing } from "./MatchRing";
import { Sheet, type SheetOption } from "./Sheet";

export type CardExtras = {
  judgeLabel: string;
  prepEnabled: boolean;
  notForMe?: (job: Job) => void;
  archive?: (job: Job) => void;
  remove?: (job: Job) => void;
};

type Tone = "muted" | "good" | "bad" | "warn" | "brand";

function Pill({ children, tone = "muted", onPress, label }: { children: React.ReactNode; tone?: Tone; onPress?: () => void; label?: string }) {
  const { colors } = useTheme();
  const tint = { muted: colors.textMuted, good: colors.good, bad: colors.danger, warn: colors.warn, brand: colors.accent }[tone];
  const body = (
    <View style={{ backgroundColor: colors.surfaceAlt, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 4, flexDirection: "row", alignItems: "center", gap: 4 }}>
      <Text style={{ color: tint, fontSize: 12 }}>{children}</Text>
    </View>
  );
  return onPress ? (
    <TouchableOpacity onPress={onPress} accessibilityRole="button" accessibilityLabel={label} hitSlop={6}>
      {body}
    </TouchableOpacity>
  ) : (
    body
  );
}

/** One job on the Home tab. Tap to open it; in "choose several" mode a tap ticks it instead. */
export function JobCard({
  job,
  statuses,
  extras,
  onMove,
  onCheckFit,
  checking,
  compact = false,
  select,
}: {
  job: Job;
  statuses: StatusInfo[];
  extras: CardExtras;
  onMove: (job: Job, statusId: number) => void;
  onCheckFit: (job: Job) => void;
  checking: boolean;
  compact?: boolean;
  select?: { checked: boolean; onToggle: () => void };
}) {
  const router = useRouter();
  const { colors } = useTheme();
  const [statusOpen, setStatusOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [more, setMore] = useState(false);
  const [working, setWorking] = useState<string | null>(null);
  const [problem, setProblem] = useState("");
  const s = useStyles((c) => StyleSheet.create({
    card: { backgroundColor: c.surface, borderRadius: radius.card, borderWidth: 1, borderColor: c.border, padding: 14, marginBottom: 10 },
    top: { flexDirection: "row", gap: 12, alignItems: "flex-start" },
    role: { fontSize: 16, fontWeight: "700" },
    muted: { color: c.textMuted, fontSize: 13 },
    small: { color: c.textMuted, fontSize: 12 },
    pills: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 8 },
    actions: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 12 },
    status: { flex: 1, minHeight: 44, flexDirection: "row", alignItems: "center", borderWidth: 1, borderColor: c.border, borderRadius: radius.control, paddingHorizontal: 10, backgroundColor: c.surfaceAlt },
    primary: { minHeight: 44, borderRadius: radius.control, paddingHorizontal: 14, alignItems: "center", justifyContent: "center", backgroundColor: c.accent },
    dots: { width: 44, height: 44, borderRadius: radius.control, borderWidth: 1, borderColor: c.border, alignItems: "center", justifyContent: "center" },
    box: { width: 26, height: 26, borderRadius: 7, borderWidth: 2, alignItems: "center", justifyContent: "center", marginTop: 2 },
    h: { fontWeight: "700", marginTop: 10, marginBottom: 2, fontSize: 13 },
  }));

  const status = statuses.find((x) => x.id === job.status_id);
  const live = livingBadge(job.live_state);
  const deadline = deadlineText(job);
  const applied = appliedParts(job);
  const canJudge = job.has_description || !!job.url;
  const needsFit = canJudge && !job.ai_evaluated;
  const hasDetails = job.strengths.length > 0 || job.gaps.length > 0 || job.tech_skills.length > 0 || !!job.notes || job.documents.length > 0 || applied.length > 0 || !!job.next_action || !!job.ai_method || !!job.summary;
  const name = `${job.role} at ${job.company}`;
  const go = (href: string) => router.push(href as Href);

  const run = async (busy: string, doIt: () => Promise<string>) => {
    setWorking(busy);
    setProblem("");
    try {
      go(await doIt());
    } catch (e) {
      setProblem(errorText(e));
    } finally {
      setWorking(null);
    }
  };

  type Action = "again" | "apply" | "tailor" | "prep" | "process" | "edit" | "view" | "notforme" | "archive" | "remove";
  const actions = useMemo(() => {
    const list: SheetOption<Action>[] = [];
    if (canJudge && job.ai_evaluated) list.push({ value: "again", label: "Check again" });
    list.push({ value: "apply", label: job.applied_date && job.applied_cv ? "Your application" : "Get ready to apply" });
    if (canJudge) list.push({ value: "tailor", label: "Tailor my CV" });
    if (extras.prepEnabled && job.gaps.length > 0 && job.has_description) list.push({ value: "prep", label: "Prepare for this job" });
    list.push({ value: "process", label: "Hiring process" });
    list.push({ value: "edit", label: "Edit details" });
    if (job.url) list.push({ value: "view", label: "View the posting" });
    if (extras.notForMe) list.push({ value: "notforme", label: "Not for me" });
    if (extras.archive) list.push({ value: "archive", label: "Archive" });
    if (extras.remove) list.push({ value: "remove", label: "Remove for good…", danger: true });
    return list;
  }, [job, canJudge, extras]);

  const onAction = (a: Action) => {
    if (a === "again") onCheckFit(job);
    else if (a === "apply") go(`/jobs/${job.id}/apply`);
    else if (a === "tailor") void run("Tailoring your CV…", async () => `/cv/${(await tailorCv(job.id)).id}`);
    else if (a === "prep") void run("Preparing your plan…", async () => `/prep/${(await createPrep(job.id)).id}`);
    else if (a === "process") go(`/jobs/${job.id}/process`);
    else if (a === "edit") go(`/jobs/${job.id}/edit`);
    else if (a === "view") void Linking.openURL(job.url);
    else if (a === "notforme") extras.notForMe?.(job);
    else if (a === "archive") extras.archive?.(job);
    else if (a === "remove") extras.remove?.(job);
  };

  const apply = applyHref(job.apply_address);
  const open = () => (select ? select.onToggle() : go(`/job/${job.id}`));

  return (
    <View style={[s.card, job.urgent ? { borderColor: colors.warn } : null, compact && { width: "100%" }]} accessibilityLabel={name}>
      <TouchableOpacity activeOpacity={0.7} onPress={open} accessibilityRole="button" accessibilityLabel={select ? `${select.checked ? "Unselect" : "Select"} ${name}` : `Open ${name}`}>
        <View style={s.top}>
          {select ? (
            <View style={[s.box, { borderColor: select.checked ? colors.accent : colors.border, backgroundColor: select.checked ? colors.accent : "transparent" }]}>
              {select.checked ? <Ionicons name="checkmark" size={16} color={colors.accentContrast} /> : null}
            </View>
          ) : null}
          <MatchRing job={job} showBand={!compact} />
          <View style={{ flex: 1 }}>
            <Text style={s.role}>{job.role}</Text>
            <Text style={s.muted}>
              {job.company}
              {job.location ? ` · ${job.location}` : ""}
            </Text>
            {job.source || job.advertised_pay || job.applied_date ? (
              <Text style={s.small}>{[job.source, job.advertised_pay, job.applied_date ? `Applied ${applied.length ? "" : ""}${job.applied_date}` : ""].filter(Boolean).join(" · ")}</Text>
            ) : null}
            {job.credit ? <Text style={s.small}>{job.credit.label}</Text> : null}
          </View>
        </View>
        <View style={s.pills}>
          {live ? <Pill tone={live.tone}>{live.text}</Pill> : null}
          {deadline ? <Pill tone={job.overdue ? "bad" : job.urgent ? "warn" : "muted"}>{deadline}</Pill> : null}
          {job.repost ? <Pill tone="warn">{`Possible repost`}</Pill> : null}
          {job.skill_matched ? <Pill tone="brand">Skill match</Pill> : null}
          {job.fit_badge ? <Pill tone={job.fit_badge === "fits" ? "good" : job.fit_badge === "check" ? "warn" : "muted"}>{FIT_BADGE_TEXT[job.fit_badge]}</Pill> : null}
          {job.cv ? (
            <Pill tone={job.cv.flagged && !job.cv.approved ? "warn" : "good"} onPress={() => go(`/cv/${job.cv!.id}`)} label={`Open CV ${job.cv.label}`}>
              {cvBadgeText(job.cv)}
            </Pill>
          ) : null}
          {job.decision ? <Pill>{truncate(job.decision, 28)}</Pill> : null}
          {job.risk ? <Pill>{`Risk: ${job.risk}`}</Pill> : null}
        </View>
        {!compact && job.summary ? (
          <Text numberOfLines={2} style={{ marginTop: 8, fontSize: 14 }}>
            {job.summary}
          </Text>
        ) : null}
        {job.next_action ? <Text style={[s.small, { marginTop: 6 }]}>{`Suggested next: ${job.next_action}`}</Text> : null}
      </TouchableOpacity>

      {job.repost ? <Text style={[s.small, { marginTop: 6 }]}>{repostTitle(job.repost)}</Text> : null}
      {!compact && apply ? (
        <TouchableOpacity onPress={() => void Linking.openURL(apply)} accessibilityRole="link" style={{ marginTop: 6 }}>
          <Text style={{ color: colors.accent, fontSize: 13 }}>{`Apply address: ${job.apply_address}`}</Text>
        </TouchableOpacity>
      ) : null}

      {!select ? (
        <View style={s.actions}>
          <TouchableOpacity style={s.status} onPress={() => setStatusOpen(true)} accessibilityRole="button" accessibilityLabel={`Status of ${name}: ${statusLabel(status)}. Change it`}>
            <View style={{ width: 4, alignSelf: "stretch", backgroundColor: status?.color ?? colors.border, borderRadius: 2, marginRight: 8, marginVertical: 8 }} />
            <Text numberOfLines={1} style={{ flex: 1, fontSize: 14 }}>
              {statusLabel(status)}
            </Text>
            <Ionicons name="chevron-down" size={16} color={colors.textMuted} />
          </TouchableOpacity>
          {needsFit ? (
            <TouchableOpacity style={[s.primary, checking && { opacity: 0.6 }]} disabled={checking} onPress={() => onCheckFit(job)} accessibilityRole="button" accessibilityLabel={`Check my fit for ${name}`}>
              <Text style={{ color: colors.accentContrast, fontWeight: "700", fontSize: 14 }}>{checking ? "Reading…" : "Check my fit"}</Text>
            </TouchableOpacity>
          ) : (
            <TouchableOpacity style={s.primary} onPress={() => go(`/jobs/${job.id}/apply`)} accessibilityRole="button">
              <Text style={{ color: colors.accentContrast, fontWeight: "700", fontSize: 14 }}>{job.applied_date && job.applied_cv ? "Your application" : "Get ready"}</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity style={s.dots} onPress={() => setMenuOpen(true)} accessibilityRole="button" accessibilityLabel={`More actions for ${name}`}>
            <Ionicons name="ellipsis-horizontal" size={20} color={colors.text} />
          </TouchableOpacity>
        </View>
      ) : null}

      {working ? <Text style={[s.small, { marginTop: 8 }]}>{working}</Text> : null}
      {problem ? <Text style={{ color: colors.danger, fontSize: 12, marginTop: 8 }}>{problem}</Text> : null}

      {hasDetails && !select ? (
        <>
          <TouchableOpacity onPress={() => setMore((v) => !v)} accessibilityRole="button" accessibilityState={{ expanded: more }} style={{ minHeight: 40, justifyContent: "center", marginTop: 4 }}>
            <Text style={{ color: colors.accent, fontWeight: "600", fontSize: 13 }}>{more ? "Hide details" : "Details"}</Text>
          </TouchableOpacity>
          {more ? (
            <View>
              {compact && job.summary ? <Text style={{ marginBottom: 6 }}>{job.summary}</Text> : null}
              {job.ai_method ? <Text style={s.small}>{job.ai_method === "keywords" ? "Fit worked out by a quick keyword check." : "Fit read by AI."}</Text> : null}
              {job.prep ? (
                <TouchableOpacity onPress={() => go(`/prep/${job.prep!.id}`)}>
                  <Text style={{ color: colors.accent, marginTop: 6 }}>{`Prep plan ${job.prep.percent}% done`}</Text>
                </TouchableOpacity>
              ) : null}
              {applied.length > 0 ? <Text style={[s.small, { marginTop: 6 }]}>{applied.join(" · ")}</Text> : null}
              {job.strengths.length > 0 ? (
                <>
                  <Text style={s.h}>Strengths</Text>
                  {job.strengths.map((t, i) => (
                    <Text key={i} style={{ fontSize: 14 }}>{`• ${t}`}</Text>
                  ))}
                </>
              ) : null}
              {job.gaps.length > 0 ? (
                <>
                  <Text style={s.h}>Worth knowing</Text>
                  {job.gaps.map((t, i) => (
                    <Text key={i} style={{ fontSize: 14 }}>{`• ${t}`}</Text>
                  ))}
                </>
              ) : null}
              {job.tech_skills.length > 0 ? (
                <>
                  <Text style={s.h}>Technologies this posting names</Text>
                  <Text style={s.small}>Green ones are already on your CV.</Text>
                  <View style={s.pills}>
                    {job.tech_skills.map((t) => (
                      <Pill key={t.name} tone={t.have ? "good" : "muted"}>{`${t.name}${t.hot ? " ★" : ""}`}</Pill>
                    ))}
                  </View>
                </>
              ) : null}
              {job.notes ? <Text style={[s.muted, { marginTop: 8 }]}>{job.notes}</Text> : null}
              {job.documents.length > 0 ? (
                <>
                  <Text style={s.h}>Documents</Text>
                  {job.documents.map((d) => (
                    <Text key={d.id} style={s.muted}>{`${d.kind}: ${d.title}`}</Text>
                  ))}
                </>
              ) : null}
            </View>
          ) : null}
        </>
      ) : null}

      <Sheet
        visible={statusOpen}
        title={`Status of ${name}`}
        options={statuses.map((x) => ({ value: x.id, label: statusLabel(x), color: x.color }))}
        value={job.status_id}
        onPick={(id) => onMove(job, id)}
        onClose={() => setStatusOpen(false)}
      />
      <Sheet visible={menuOpen} title={name} options={actions} onPick={onAction} onClose={() => setMenuOpen(false)} />
    </View>
  );
}
