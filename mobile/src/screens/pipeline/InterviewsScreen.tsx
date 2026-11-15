import * as Clipboard from "expo-clipboard";
import { useLocalSearchParams, useRouter, type Href } from "expo-router";
import React, { useState } from "react";
import { View } from "react-native";

import { pipelineApi, type CalendarLink, type Interview, type InterviewList, type InterviewValues } from "../../api/pipeline";
import { Badge, Button, Card, confirm, Empty, ErrorBox, Field, Loading, Muted, notify, Row, Screen, Select, SectionTitle, Text, useTheme } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";
import { PracticeQuestions } from "./CameUp";
import { whenLabel } from "./logic";
import { DateField, FormSheet, MultiPick, SuggestMove, type Suggestion } from "./parts";

const blank = (job: string): InterviewValues => ({ application: job, scheduled_at: "", kind: "video", where: "", notes: "", custom_label: "", contacts: [] });

function InterviewForm({ data, item, defaultJob, onDone, onSuggest }: { data: InterviewList; item?: Interview; defaultJob: string; onDone: () => void; onSuggest: (s: Suggestion) => void }) {
  const act = useAction();
  const [v, setV] = useState<InterviewValues>(
    item
      ? { application: String(item.job.id), scheduled_at: item.scheduled_local, kind: item.kind, where: item.where, notes: item.notes, custom_label: item.custom_label, contacts: item.interviewers.map((c) => c.id) }
      : blank(defaultJob),
  );
  const f = act.fields ?? {};
  const save = async () => {
    const saved = await act.run(() => (item ? pipelineApi.editInterview(item.id, v) : pipelineApi.addInterview(v)));
    if (!saved) return;
    if (saved.calendar_note) notify(saved.calendar_note);
    if (saved.suggest_status) onSuggest({ jobId: Number(v.application), status: saved.suggest_status });
    onDone();
  };
  return (
    <View>
      <Select label="Job" value={v.application || null} onChange={(x) => setV({ ...v, application: String(x) })} options={data.jobs.map((j) => ({ value: String(j.id), label: j.label }))} placeholder="Pick a job…" />
      {f.application ? <Text style={{ marginBottom: 10 }}>{f.application}</Text> : null}
      <DateField label="When" withTime value={v.scheduled_at} onChange={(x) => setV({ ...v, scheduled_at: x })} error={f.scheduled_at} hint="In your own time zone." />
      <Select label="Kind" value={v.kind} onChange={(x) => setV({ ...v, kind: String(x) })} options={data.kinds.map((k) => ({ value: k.value, label: k.label }))} />
      {v.kind === "other" ? <Field label="Name of this stage" value={v.custom_label} onChangeText={(x) => setV({ ...v, custom_label: x })} maxLength={80} hint="For example: Meet the CEO." error={f.custom_label} /> : null}
      <MultiPick label="Who interviewed you" options={data.contacts} value={v.contacts} onChange={(x) => setV({ ...v, contacts: x })} />
      <Field label="Where or link" value={v.where} onChangeText={(x) => setV({ ...v, where: x })} maxLength={300} error={f.where} autoCapitalize="none" />
      <Field label="Notes" value={v.notes} onChangeText={(x) => setV({ ...v, notes: x })} multiline maxLength={4000} hint="Who you will meet, what to prepare, questions to ask." error={f.notes} />
      {act.error && !act.fields ? <ErrorBox message={act.error} /> : null}
      <Button label={item ? "Save changes" : "Add interview"} busy={act.busy} onPress={save} />
    </View>
  );
}

function InterviewCard({ item, data, onEdit, onChanged, onSuggest }: { item: Interview; data: InterviewList; onEdit: () => void; onChanged: () => void; onSuggest: (s: Suggestion) => void }) {
  const router = useRouter();
  const { colors } = useTheme();
  const act = useAction();
  const [practise, setPractise] = useState(false);
  const tone = item.outcome === "passed" ? colors.good : item.outcome === "rejected" || item.outcome === "noshow" ? colors.danger : colors.textMuted;
  const setOutcome = async (o: string) => {
    const r = await act.run(() => pipelineApi.interviewOutcome(item.id, o));
    if (!r) return;
    if (r.suggest_status) onSuggest({ jobId: item.job.id, status: r.suggest_status });
    onChanged();
  };
  const remove = async () => {
    if (!(await confirm("Delete this interview?", undefined, "Delete"))) return;
    if (await act.run(() => pipelineApi.deleteInterview(item.id))) onChanged();
  };
  return (
    <Card>
      <Row style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <View style={{ flex: 1 }}>
          <Text style={{ fontWeight: "700" }}>{item.stage_name}</Text>
          <Text>
            {item.job.company} - {item.job.role}
          </Text>
          <Muted>{whenLabel(item.scheduled_local)}</Muted>
        </View>
        <Badge label={item.outcome_label} color={tone} />
      </Row>
      {item.interviewers.length > 0 ? <Text style={{ marginTop: 6 }}>With {item.interviewers.map((c) => c.name).join(", ")}</Text> : null}
      {item.where ? <Text style={{ marginTop: 4 }}>{item.where}</Text> : null}
      {item.notes ? <Muted style={{ marginTop: 4 }}>{item.notes}</Muted> : null}
      <View style={{ marginTop: 12 }}>
        <Select label="How did it go?" value={item.outcome} onChange={(o) => setOutcome(String(o))} options={data.outcomes.map((o) => ({ value: o.value, label: o.label }))} />
      </View>
      {act.error ? <Text style={{ color: colors.danger, marginBottom: 8 }}>{act.error}</Text> : null}
      <Row style={{ flexWrap: "wrap" }}>
        <Button label="Hiring process" variant="secondary" onPress={() => router.push(`/jobs/${item.job.id}/process` as Href)} />
        <Button label="Edit" variant="secondary" onPress={onEdit} />
        <Button label={practise ? "Hide practice" : "Practise questions"} variant="secondary" onPress={() => setPractise(!practise)} />
        <Button label="Thank-you note" variant="secondary" onPress={() => router.push(`/jobs/${item.job.id}/message?interview=${item.id}&kind=thank_you` as Href)} />
        <Button label="Delete" variant="danger" onPress={remove} />
      </Row>
      {practise ? (
        <View style={{ marginTop: 12 }}>
          <PracticeQuestions jobId={item.job.id} onOpenPrep={() => router.push(`/jobs/${item.job.id}/prep` as Href)} />
        </View>
      ) : null}
    </Card>
  );
}

/** A private address a calendar app can subscribe to. Dates only, read-only. */
function CalendarLinkCard() {
  const { colors } = useTheme();
  const load = useLoad(() => pipelineApi.calendarLink());
  const act = useAction();
  const link: CalendarLink | null = load.data;
  const [shown, setShown] = useState(false);
  const make = async (replace: boolean) => {
    if (replace && !(await confirm("Make a new link?", "The old link stops working straight away, so you will need to subscribe again with the new one.", "Make a new link"))) return;
    const r = await act.run(() => pipelineApi.makeCalendarLink());
    if (r) {
      load.setData(r);
      notify(replace ? "New link made. The old one no longer works." : "Calendar link made.");
    }
  };
  const stop = async () => {
    const r = await act.run(() => pipelineApi.stopCalendarLink());
    if (r) {
      load.setData(r);
      setShown(false);
      notify("Calendar link turned off.");
    }
  };
  return (
    <Card>
      <Text style={{ fontWeight: "700", marginBottom: 4 }}>Show these dates in your calendar</Text>
      <Muted style={{ marginBottom: 10 }}>
        Add one link to Google Calendar, Apple Calendar or Outlook (look for "subscribe" or "add from web") and your interviews, follow-up days and apply-by days appear there and stay up to date.
      </Muted>
      {!link ? (
        load.error ? <Muted>{load.error}</Muted> : <Loading />
      ) : link.enabled ? (
        <View>
          {shown ? <Text selectable style={{ fontSize: 12, backgroundColor: colors.surfaceAlt, padding: 10, borderRadius: 10, marginBottom: 10 }}>{link.url}</Text> : null}
          <Row style={{ flexWrap: "wrap" }}>
            <Button
              label="Copy link"
              onPress={async () => {
                await Clipboard.setStringAsync(link.url);
                notify("Link copied.");
              }}
            />
            <Button label={shown ? "Hide link" : "Show link"} variant="secondary" onPress={() => setShown(!shown)} />
            <Button label="Make a new link" variant="secondary" busy={act.busy} onPress={() => make(true)} />
            <Button label="Turn off" variant="ghost" busy={act.busy} onPress={stop} />
          </Row>
        </View>
      ) : (
        <Button label="Make my calendar link" busy={act.busy} onPress={() => make(false)} />
      )}
      <Muted style={{ marginTop: 10 }}>
        Anyone who has this link can read these dates, so keep it to yourself. It shows only the day or time, the company and the role: never your notes, the job text, meeting links or contacts. If it leaks, make a new link.
      </Muted>
      {act.error ? <Text style={{ color: colors.danger, marginTop: 8 }}>{act.error}</Text> : null}
    </Card>
  );
}

export default function InterviewsScreen() {
  const params = useLocalSearchParams<{ job?: string }>();
  const load = useLoad(() => pipelineApi.interviews());
  const [editing, setEditing] = useState<Interview | "new" | null>(null);
  const [suggest, setSuggest] = useState<Suggestion | null>(null);
  const data = load.data;
  const defaultJob = data && params.job && data.jobs.some((j) => String(j.id) === params.job) ? String(params.job) : "";
  return (
    <Screen title="Interviews" onRefresh={load.refresh} refreshing={load.refreshing}>
      {load.loading ? <Loading /> : load.error && !data ? <ErrorBox message={load.error} onRetry={load.reload} /> : null}
      {data ? (
        <>
          <Muted style={{ marginBottom: 12 }}>Keep every conversation in one place: when it is, where, who you meet and what to prepare. Nothing is sent to anyone.</Muted>
          {suggest ? <SuggestMove suggestion={suggest} onDone={() => setSuggest(null)} /> : null}
          <SectionTitle action={{ label: "Add interview", onPress: () => setEditing("new") }}>Coming up</SectionTitle>
          {data.upcoming.length === 0 ? (
            <Card>
              <Muted>
                {data.jobs.length === 0
                  ? "Add a job to your tracker first, then you can schedule an interview for it."
                  : "Nothing is booked. When a company invites you to talk, add it here so it shows on your dashboard."}
              </Muted>
            </Card>
          ) : (
            data.upcoming.map((i) => <InterviewCard key={i.id} item={i} data={data} onEdit={() => setEditing(i)} onChanged={load.reload} onSuggest={setSuggest} />)
          )}
          <SectionTitle>Earlier</SectionTitle>
          {data.past.length === 0 ? (
            <Card>
              <Muted>Interviews that have happened, or were cancelled, will be listed here.</Muted>
            </Card>
          ) : (
            data.past.map((i) => <InterviewCard key={i.id} item={i} data={data} onEdit={() => setEditing(i)} onChanged={load.reload} onSuggest={setSuggest} />)
          )}
          <SectionTitle>Your calendar</SectionTitle>
          <CalendarLinkCard />
          <FormSheet visible={editing !== null} title={editing && editing !== "new" ? "Edit interview" : "Add an interview"} onClose={() => setEditing(null)}>
            {data.jobs.length === 0 ? (
              <Empty title="No jobs yet" hint="Add a job to your tracker first, then you can schedule an interview for it." />
            ) : editing ? (
              <InterviewForm
                key={editing === "new" ? "new" : editing.id}
                data={data}
                item={editing === "new" ? undefined : editing}
                defaultJob={defaultJob}
                onDone={() => {
                  setEditing(null);
                  load.reload();
                  notify("Interview saved.");
                }}
                onSuggest={setSuggest}
              />
            ) : null}
          </FormSheet>
        </>
      ) : null}
    </Screen>
  );
}
