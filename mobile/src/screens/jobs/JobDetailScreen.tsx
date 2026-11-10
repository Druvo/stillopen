// The full job page: status, fit, how you match, details, notes, description, history, and every action the website's job card has.
import { useLocalSearchParams, useRouter, type Href } from "expo-router";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { View } from "react-native";

import { jobsApi, type ArchivedJob, type DashboardForJobs, type HistoryData, type JobDetails, type JobFull, type PostingSummary } from "../../api/jobs";
import { FitList, MatchCard } from "../../components/jobs/MatchCard";
import { Badge, Body, Button, Card, Empty, ErrorBox, Field, ListItem, Loading, Muted, Screen, SectionTitle, Select, Text, confirm, notify, useTheme } from "../../ui";
import { errorText, useAction, useLoad } from "../../ui/useApi";
import { applyHref, dateTime, livingBadge, longDate, notForMeStatus, openLink, repostHint, safeWebUrl, shortDate, statusWord } from "./logic";

type Bundle = { dash: DashboardForJobs; job: JobFull | null; archived: ArchivedJob | null; details: JobDetails | null; translate: boolean };

async function loadBundle(id: number): Promise<Bundle> {
  const [dash, me] = await Promise.all([jobsApi.dashboard(), jobsApi.me().catch(() => ({ translate_enabled: false }))]);
  const job = dash.jobs.find((j) => j.id === id) ?? null;
  const archived = dash.archived.find((j) => j.id === id) ?? null;
  if (!job && !archived) throw new Error("We could not find this job. It may have been removed.");
  const details = await jobsApi.details(id).catch(() => null);
  return { dash, job, archived, details, translate: !!me.translate_enabled };
}

/** A card that opens and closes; its content is only built when opened (so the match card and history are fetched on demand). */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <Card>
      <Button label={`${open ? "Hide" : "Show"}: ${title}`} variant="ghost" onPress={() => setOpen(!open)} />
      {open ? <View style={{ marginTop: 10 }}>{children}</View> : null}
    </Card>
  );
}

function History({ jobId }: { jobId: number }) {
  const [data, setData] = useState<HistoryData | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    jobsApi.history(jobId).then(setData).catch((e) => setError(errorText(e)));
  }, [jobId]);
  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  if (data.items.length === 0) return <Muted>Nothing has happened to this job yet. When you move it to another status, apply, add an interview or set a reminder, it is written down here.</Muted>;
  return (
    <View style={{ gap: 10 }}>
      {data.items.map((i) => (
        <View key={i.id}>
          <Muted>
            {shortDate(i.date)} · {i.kind_label}
          </Muted>
          <Body>{i.text}</Body>
        </View>
      ))}
      {data.capped ? <Muted>Showing the latest 100. Older lines are kept.</Muted> : null}
    </View>
  );
}

function SummaryBlock({ jobId, hasDescription }: { jobId: number; hasDescription: boolean }) {
  const { colors } = useTheme();
  const [summary, setSummary] = useState<PostingSummary | null | undefined>(undefined);
  const action = useAction();
  useEffect(() => {
    jobsApi.getSummary(jobId).then((r) => setSummary(r.summary)).catch(() => setSummary(null));
  }, [jobId]);
  const read = async () => {
    const r = await action.run(() => jobsApi.summarise(jobId));
    if (r) setSummary(r.summary);
  };
  if (summary === undefined) return <Loading />;
  const list = (title: string, items: string[]) =>
    items.length ? (
      <View style={{ marginBottom: 8 }}>
        <Text style={{ fontWeight: "700" }}>{title}</Text>
        {items.map((t, i) => (
          <Body key={i}>• {t}</Body>
        ))}
      </View>
    ) : null;
  return (
    <View>
      {summary ? (
        <>
          {list("Must have", summary.must_have)}
          {list("Nice to have", summary.nice_to_have)}
          {(
            [
              ["Level", summary.seniority],
              ["Pay", summary.pay],
              ["Visa", summary.visa],
              ["Relocation", summary.relocation],
              ["Remote", summary.remote],
              ["Deadline", summary.deadline],
            ] as [string, string][]
          ).map(([k, v]) => (v ? <Body key={k}>{k}: {v}</Body> : null))}
          {list("Worth a second look", summary.red_flags.map((f) => f.flag))}
          <Muted>{summary.method === "ai" ? "Read by your AI." : "Read with plain rules."}</Muted>
        </>
      ) : (
        <Muted>{hasDescription ? "Nothing read yet. This lists what the role needs and any plainly worded red flags." : "Add the job description first, then it can be read."}</Muted>
      )}
      {hasDescription ? <Button label={summary ? "Read it again" : "Read the posting"} variant="secondary" busy={action.busy} onPress={read} style={{ marginTop: 8 }} /> : null}
      {action.error ? <Text style={{ marginTop: 6, color: colors.danger }}>{action.error}</Text> : null}
    </View>
  );
}

export default function JobDetailScreen() {
  const { id: idParam } = useLocalSearchParams<{ id: string }>();
  const id = Number(idParam);
  const router = useRouter();
  const { colors } = useTheme();
  const { data, error, loading, refreshing, refresh, reload } = useLoad(() => loadBundle(id), [id]);
  const move = useAction();
  const fit = useAction();
  const notes = useAction();
  const misc = useAction();
  const [statusId, setStatusId] = useState<number | null>(null);
  const [statusNote, setStatusNote] = useState("");
  const [notesText, setNotesText] = useState<string | null>(null);
  const [showDesc, setShowDesc] = useState(false);
  const [translated, setTranslated] = useState("");
  const [lastMove, setLastMove] = useState("");
  const [checking, setChecking] = useState("");
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(
    () => () => {
      if (poll.current) clearInterval(poll.current);
    },
    [],
  );
  useEffect(() => {
    if (data?.job && statusId === null) setStatusId(data.job.status_id);
    if (data && notesText === null) setNotesText(data.details?.values.notes ?? data.job?.notes ?? "");
  }, [data, statusId, notesText]);

  const go = useCallback((path: string) => router.push(path as Href), [router]);

  if (loading) {
    return (
      <Screen title="Job">
        <Loading />
      </Screen>
    );
  }
  if (error || !data) {
    return (
      <Screen title="Job" onRefresh={refresh} refreshing={refreshing}>
        <ErrorBox message={error ?? "We could not load this job."} onRetry={reload} />
      </Screen>
    );
  }

  const { dash, job, archived, details } = data;
  const title = job?.role ?? archived?.role ?? "Job";
  const company = job?.company ?? archived?.company ?? "";
  const url = job?.url ?? archived?.url ?? "";
  const isArchived = !job && !!archived;
  const status = job ? dash.statuses.find((s) => s.id === job.status_id) : undefined;
  const live = job ? livingBadge(job.live_state) : null;
  const tone = (t: "good" | "bad" | "warn") => (t === "good" ? colors.good : t === "bad" ? colors.danger : colors.warn);
  const description = details?.values.description ?? "";
  const canJudge = !!job && (job.has_description || !!job.url);
  const red = { color: colors.danger, marginTop: 6 };

  const changeStatus = async () => {
    if (!job || statusId === null || statusId === job.status_id) return;
    const r = await move.run(() => jobsApi.setStatus(id, statusId, statusNote.trim()));
    if (r) {
      setStatusNote("");
      setLastMove(`Moved to ${r.label}.`);
      await reload();
    }
  };
  const undo = async () => {
    const r = await move.run(() => jobsApi.undoStatus(id));
    if (r) {
      setStatusId(r.status.id);
      setLastMove("");
      await reload();
    }
  };
  const checkFit = async () => {
    const r = await fit.run(() => jobsApi.evaluate(id));
    if (r) await reload();
  };
  const saveNotes = async () => {
    if (!details) return;
    const r = await notes.run(() => jobsApi.saveDetails(id, { ...details.values, notes: notesText ?? "" }));
    if (r) {
      notify("Saved.");
      await reload();
    }
  };
  const translate = async () => {
    const r = await misc.run(() => jobsApi.translate(id));
    if (r) setTranslated(r.translated);
  };
  const checkOpen = async () => {
    setChecking("Checking which jobs are still open…");
    try {
      await jobsApi.startLiveness();
      poll.current = setInterval(async () => {
        try {
          const s = await jobsApi.livenessStatus();
          if (!s.running) {
            if (poll.current) clearInterval(poll.current);
            setChecking("");
            await reload();
          } else setChecking(`Checking… ${s.done} of ${s.total}`);
        } catch (e) {
          if (poll.current) clearInterval(poll.current);
          setChecking(errorText(e));
        }
      }, 2500);
    } catch (e) {
      setChecking(errorText(e));
    }
  };
  const archive = async () => {
    const r = await misc.run(() => (isArchived ? jobsApi.restore(id) : jobsApi.archive(id)));
    if (r) {
      notify(isArchived ? "Brought back to your dashboard." : "Archived. You can bring it back from Archived on the dashboard.");
      if (isArchived) await reload();
      else router.back();
    }
  };
  const notForMe = async () => {
    const s = notForMeStatus(dash.statuses);
    if (!s) return notify("There is no Not for me status to use.");
    const r = await misc.run(() => jobsApi.setStatus(id, s.id));
    if (r) {
      notify("Marked as not for me. You can find it under Closed and skipped.");
      router.back();
    }
  };
  const remove = async () => {
    let text = "This removes the job and what you made for it. This cannot be undone.";
    try {
      const p = await jobsApi.removePreview(id);
      text = `${p.text}\n\n${p.keeps}\n\nThis cannot be undone.`;
    } catch {
      /* the confirmation still works without the list */
    }
    if (!(await confirm(`Remove ${title} for good?`, text, "Remove for good"))) return;
    const r = await misc.run(() => jobsApi.removeJob(id));
    if (r) {
      notify(`Removed ${title} at ${company}.`);
      router.back();
    }
  };
  const followup = async (kind: "done" | "snooze") => {
    const r = await misc.run(() => (kind === "done" ? jobsApi.followupDone(id) : jobsApi.followupSnooze(id, 3)));
    if (r) await reload();
  };

  // statuses grouped by their stage, like the website's board columns
  const options = dash.buckets.flatMap((b) => dash.statuses.filter((s) => s.bucket_key === b.key).map((s) => ({ value: s.id, label: `${b.label}: ${statusWord(s)}` })));
  const apply = job ? applyHref(job.apply_address) : "";
  const appliedLine = job?.applied_date ? [`Applied ${longDate(job.applied_date)}`, job.applied_channel, job.applied_cv ? job.applied_cv.label : ""].filter(Boolean).join(" · ") : "";

  return (
    <Screen title={title} onRefresh={refresh} refreshing={refreshing}>
      <Text style={{ fontSize: 22, fontWeight: "700" }}>{title}</Text>
      <Text style={{ color: colors.accent, fontWeight: "600", marginTop: 2 }} onPress={() => company && go(`/companies/${encodeURIComponent(company)}`)} accessibilityRole="link">
        {company}
      </Text>
      <Muted style={{ marginTop: 4 }}>{[job?.location, job?.arrangement, job?.advertised_pay, job?.source].filter(Boolean).join(" · ")}</Muted>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 10, marginBottom: 12 }}>
        {isArchived ? <Badge label="Archived" color={colors.textMuted} /> : null}
        {status ? <Badge label={statusWord(status)} color={status.color} /> : archived ? <Badge label={archived.status} /> : null}
        {live ? <Badge label={live.text} color={tone(live.tone)} /> : null}
        {job?.deadline ? <Badge label={`Apply by ${shortDate(job.deadline)}`} color={job.overdue ? colors.danger : job.urgent ? colors.warn : colors.textMuted} /> : null}
        {job?.repost ? <Badge label="Possible repost" color={colors.warn} /> : null}
        {job?.skill_matched ? <Badge label="Skill match" /> : null}
        {job?.cv ? <Badge label={job.cv.flagged && !job.cv.approved ? "CV needs review" : "CV ready"} color={job.cv.flagged && !job.cv.approved ? colors.warn : colors.good} /> : null}
      </View>
      {job?.repost ? <Muted style={{ marginBottom: 10 }}>{repostHint(job.repost)}</Muted> : null}
      {job?.live_detail ? <Muted style={{ marginBottom: 10 }}>{job.live_detail}</Muted> : null}

      {isArchived ? (
        <Card>
          <Body>This job is archived: it is off your dashboard and out of its counts.</Body>
          <Button label="Bring it back" onPress={archive} busy={misc.busy} style={{ marginTop: 10 }} />
        </Card>
      ) : null}

      {job ? (
        <Card>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
            {job.percent !== null ? (
              <Text style={{ fontSize: 30, fontWeight: "800", color: job.band?.color ?? colors.accent }} accessibilityLabel={`${job.percent}% match`}>
                {job.percent}%
              </Text>
            ) : (
              <Text style={{ color: colors.textMuted }}>Not checked yet</Text>
            )}
            <View style={{ flex: 1 }}>
              {job.band ? <Text style={{ fontWeight: "700" }}>{job.band.label}</Text> : null}
              <Muted>{job.fit_text || (job.ai_method === "keywords" ? "Worked out by a quick keyword check." : job.ai_method ? "Read by AI." : "")}</Muted>
            </View>
          </View>
          {canJudge ? (
            <Button label={job.evaluated ? "Check again" : "Check my fit"} variant={job.evaluated ? "secondary" : "primary"} busy={fit.busy} onPress={checkFit} style={{ marginTop: 12 }} />
          ) : (
            <Muted style={{ marginTop: 8 }}>Add the job description or its link in Edit details, then check your fit.</Muted>
          )}
          {fit.error ? <Text style={red}>{fit.error}</Text> : null}
          <Button label={job.applied_date && job.applied_cv ? "Your application" : "Get ready to apply"} onPress={() => go(`/jobs/${id}/apply`)} style={{ marginTop: 10 }} />
          {url && safeWebUrl(url) ? <Button label="View the posting" variant="secondary" icon="open-outline" onPress={() => openLink(url)} style={{ marginTop: 10 }} /> : null}
          {apply ? <Button label={`Apply address: ${job.apply_address}`} variant="ghost" onPress={() => openLink(apply)} /> : null}
          {job.credit ? <Muted style={{ marginTop: 8 }}>{job.credit.label}</Muted> : null}
        </Card>
      ) : null}

      {job ? (
        <>
          <SectionTitle>Status</SectionTitle>
          <Card>
            <Select label="Move to" options={options} value={statusId} onChange={(v) => setStatusId(v)} />
            <Field label="Note (optional)" value={statusNote} onChangeText={setStatusNote} placeholder="For example: a line from their reply" maxLength={400} />
            <Button label="Change status" onPress={changeStatus} busy={move.busy} disabled={statusId === job.status_id} />
            {lastMove ? (
              <View style={{ marginTop: 8 }}>
                <Muted>{lastMove}</Muted>
                <Button label="Undo" variant="ghost" onPress={undo} />
              </View>
            ) : null}
            {move.error ? <Text style={red}>{move.error}</Text> : null}
            {appliedLine ? <Muted style={{ marginTop: 8 }}>{appliedLine}</Muted> : null}
            {job.follow_up_date ? (
              <View style={{ marginTop: 8 }}>
                <Body>Follow up on {longDate(job.follow_up_date)}</Body>
                <View style={{ flexDirection: "row", gap: 8, marginTop: 6 }}>
                  <Button label="Done" variant="secondary" onPress={() => followup("done")} busy={misc.busy} />
                  <Button label="Remind me in 3 days" variant="secondary" onPress={() => followup("snooze")} busy={misc.busy} />
                </View>
              </View>
            ) : null}
          </Card>
          {job.next_action ? (
            <Card>
              <Text style={{ fontWeight: "700", marginBottom: 4 }}>Suggested next</Text>
              <Body>{job.next_action}</Body>
            </Card>
          ) : null}
        </>
      ) : null}

      <SectionTitle>Open this job's pages</SectionTitle>
      <ListItem icon="create-outline" title="Edit details" subtitle="Correct the company, place, pay, kind of role" onPress={() => go(`/jobs/${id}/edit`)} />
      <ListItem icon="git-branch-outline" title="Hiring process" subtitle="Interviews, contacts, offers" onPress={() => go(`/jobs/${id}/process`)} />
      <ListItem icon="school-outline" title="Interview prep" onPress={() => go(`/jobs/${id}/prep`)} />
      {job?.prep ? <ListItem icon="checkbox-outline" title={`Prep plan ${job.prep.percent}% done`} onPress={() => go(`/prep/${job.prep!.id}`)} /> : null}
      <ListItem icon="chatbubble-outline" title="Write a message" subtitle="Follow-up, thank you and more. Nothing is sent for you" onPress={() => go(`/jobs/${id}/message`)} />
      <ListItem icon="mail-outline" title="Mail for this job" onPress={() => go(`/jobs/${id}/mail`)} />
      {job?.cv ? <ListItem icon="document-text-outline" title={job.cv.label} subtitle={job.cv.flagged && !job.cv.approved ? "Needs review before download" : "Your tailored CV"} onPress={() => go(`/cv/${job.cv!.id}`)} /> : null}
      {job?.applied_cv && job.applied_cv.id !== job.cv?.id ? <ListItem icon="paper-plane-outline" title={`Sent: ${job.applied_cv.label}`} onPress={() => go(`/cv/${job.applied_cv!.id}`)} /> : null}

      {job ? (
        <>
          <SectionTitle>Fit and match</SectionTitle>
          {details ? (
            <Card>
              <Text style={{ fontWeight: "700", marginBottom: 6 }}>Fit with what you want</Text>
              <FitList checks={details.fit} empty="Nothing to check yet." />
              <Muted style={{ marginTop: 6 }}>Checked against your search areas in Profile. This only flags a job; it never hides one.</Muted>
            </Card>
          ) : null}
          <Section title="How you match">{job.has_description || description ? <MatchCard jobId={id} /> : <Muted>Add the job description first.</Muted>}</Section>
          <Section title="What this role really needs">
            <SummaryBlock jobId={id} hasDescription={!!(job.has_description || description)} />
          </Section>
          {job.strengths.length || job.gaps.length || job.tech_skills.length ? (
            <Section title="Strengths and gaps">
              {job.strengths.length ? <Text style={{ fontWeight: "700" }}>Strengths</Text> : null}
              {job.strengths.map((t, i) => (
                <Body key={`s${i}`}>• {t}</Body>
              ))}
              {job.gaps.length ? <Text style={{ fontWeight: "700", marginTop: 8 }}>Worth knowing</Text> : null}
              {job.gaps.map((t, i) => (
                <Body key={`g${i}`}>• {t}</Body>
              ))}
              {job.tech_skills.length ? (
                <View style={{ marginTop: 8 }}>
                  <Text style={{ fontWeight: "700" }}>Technologies it mentions</Text>
                  <Muted>Named tools from the posting, and whether your CV already covers them.</Muted>
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                    {job.tech_skills.map((t) => (
                      <Badge key={t.name} label={`${t.name}${t.hot ? " ★" : ""}${t.have ? " ✓" : ""}`} color={t.have ? colors.good : colors.textMuted} />
                    ))}
                  </View>
                </View>
              ) : null}
            </Section>
          ) : null}
        </>
      ) : null}

      <SectionTitle>Your notes</SectionTitle>
      <Card>
        {details ? (
          <>
            <Field label="Notes" value={notesText ?? ""} onChangeText={setNotesText} multiline placeholder="Anything you want to remember about this job" />
            <Button label="Save notes" onPress={saveNotes} busy={notes.busy} disabled={(notesText ?? "") === (details.values.notes ?? "")} />
            {notes.error ? <Text style={red}>{notes.error}</Text> : null}
          </>
        ) : (
          <Body>{job?.notes || "No notes yet."}</Body>
        )}
      </Card>

      <SectionTitle>Description</SectionTitle>
      <Card>
        {description ? (
          <>
            {/* a posting is untrusted text: shown as plain text only */}
            <Text selectable numberOfLines={showDesc ? undefined : 12} style={{ fontSize: 15, lineHeight: 22 }}>
              {description}
            </Text>
            <Button label={showDesc ? "Show less" : "Show all"} variant="ghost" onPress={() => setShowDesc(!showDesc)} />
            {data.translate ? <Button label="Translate to English" variant="secondary" busy={misc.busy} onPress={translate} /> : null}
            {translated ? (
              <View style={{ marginTop: 10 }}>
                <Muted>Machine translation, for reading only. It is not saved.</Muted>
                <Text selectable style={{ fontSize: 15, lineHeight: 22 }}>{translated}</Text>
              </View>
            ) : null}
          </>
        ) : (
          <Empty title="No description saved" hint="Open Edit details and paste the text of the posting, so your fit can be checked." action={{ label: "Edit details", onPress: () => go(`/jobs/${id}/edit`) }} />
        )}
      </Card>

      <Section title="History">
        <History jobId={id} />
      </Section>

      {job ? (
        <>
          <SectionTitle>Open or closed</SectionTitle>
          <Card>
            <Muted>{job.live_state ? "The posting was checked before. Check again to see whether it is still open." : "Not checked yet whether the posting is still open."}</Muted>
            <Button label="Are they still open?" variant="secondary" onPress={checkOpen} disabled={checking.startsWith("Checking")} style={{ marginTop: 8 }} />
            {checking ? <Muted style={{ marginTop: 6 }}>{checking} This checks all your jobs.</Muted> : null}
          </Card>
        </>
      ) : null}

      <SectionTitle>Not for you any more?</SectionTitle>
      <Card>
        {!isArchived ? <Button label="Archive" variant="secondary" onPress={archive} busy={misc.busy} /> : null}
        {job ? <Button label="Mark as not for me" variant="secondary" onPress={notForMe} busy={misc.busy} style={{ marginTop: 10 }} /> : null}
        <Button label="Remove for good…" variant="danger" onPress={remove} style={{ marginTop: 10 }} />
        {misc.error ? <Text style={red}>{misc.error}</Text> : null}
        {archived?.archived_at ? <Muted style={{ marginTop: 8 }}>Archived {dateTime(archived.archived_at)}</Muted> : null}
      </Card>
    </Screen>
  );
}
