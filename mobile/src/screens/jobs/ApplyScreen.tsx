// The apply assistant: check the list, choose the CV, apply on the employer's site, then record what you did.
// The app never applies for the person and never sends anything: the email draft is plain text to copy.
import * as Clipboard from "expo-clipboard";
import { useLocalSearchParams, useRouter, type Href } from "expo-router";
import React, { useState } from "react";
import { View } from "react-native";

import { jobsApi, type ApplyData } from "../../api/jobs";
import { DateField } from "../../components/jobs/DateField";
import { FitList, MatchCard } from "../../components/jobs/MatchCard";
import { Badge, Body, Button, Card, Choice, ErrorBox, Field, ListItem, Loading, Muted, Screen, SectionTitle, Text, Toggle, notify, useTheme } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";
import { COVER_TONES, appliedMessage, longDate, openLink, safeWebUrl, validIsoDate } from "./logic";

export default function ApplyScreen() {
  const { id: idParam } = useLocalSearchParams<{ id: string }>();
  const id = Number(idParam);
  const { data, error, loading, refreshing, refresh, reload } = useLoad(() => jobsApi.apply(id), [id]);
  if (loading) {
    return (
      <Screen title="Apply">
        <Loading />
      </Screen>
    );
  }
  if (error || !data) {
    return (
      <Screen title="Apply" onRefresh={refresh} refreshing={refreshing}>
        <ErrorBox message={error ?? "We could not load this job."} onRetry={reload} />
      </Screen>
    );
  }
  return <ApplyBody id={id} data={data} refreshing={refreshing} refresh={refresh} reload={reload} />;
}

function ApplyBody({ id, data, refreshing, refresh, reload }: { id: number; data: ApplyData; refreshing: boolean; refresh: () => Promise<void>; reload: () => Promise<void> }) {
  const router = useRouter();
  const { colors } = useTheme();
  const go = (path: string) => router.push(path as Href);
  const record = useAction();
  const make = useAction();
  const [cv, setCv] = useState<string>(data.selected !== null ? String(data.selected) : "none");
  const [channel, setChannel] = useState(data.job.channel);
  const [appliedOn, setAppliedOn] = useState(data.job.applied_date);
  const [note, setNote] = useState(data.job.note);
  const [days, setDays] = useState(String(data.followup_days));
  const [confirmClosed, setConfirmClosed] = useState(false);
  const [tone, setTone] = useState("warm");
  const [localError, setLocalError] = useState("");

  const copy = async (label: string, text: string) => {
    await Clipboard.setStringAsync(text);
    notify(`${label} copied.`);
  };

  const tailor = async () => {
    const r = await make.run(() => jobsApi.tailorCv(id));
    if (r) go(`/cv/${r.id}`);
  };
  const letter = async () => {
    const r = await make.run(() => jobsApi.writeCover(id, tone));
    if (r) go(`/cover/${r.id}`);
  };
  const submit = async () => {
    setLocalError("");
    if (!validIsoDate(appliedOn)) return setLocalError("Write the date as YYYY-MM-DD.");
    const n = days.trim() ? Number(days) : null;
    if (n !== null && (!Number.isInteger(n) || n < 1 || n > data.max_followup_days)) return setLocalError(`Choose a number of days from 1 to ${data.max_followup_days}.`);
    const r = await record.run(() =>
      jobsApi.record(id, { cv: cv === "none" ? null : Number(cv), channel, note, days: n, applied_on: appliedOn || null, confirm_closed: confirmClosed }),
    );
    if (r) {
      notify(appliedMessage(r.follow_up_date));
      router.replace(`/job/${id}` as Href);
    }
  };

  return (
    <Screen title={`Apply: ${data.job.company}`} onRefresh={refresh} refreshing={refreshing}>
      <Text style={{ fontSize: 20, fontWeight: "700" }}>{data.job.role}</Text>
      <Muted style={{ marginBottom: 12 }}>StillOpen does not apply for you. Check the list, choose the CV, apply on the employer's site, then record it here so you always know what you sent.</Muted>
      {data.job.applied ? (
        <View style={{ marginBottom: 12 }}>
          <Badge label="Applied" color={colors.good} />
          <Muted style={{ marginTop: 4 }}>
            {data.job.applied_date ? `On ${longDate(data.job.applied_date)}` : ""}
            {data.job.follow_up_date ? ` · follow up on ${longDate(data.job.follow_up_date)}` : ""}
          </Muted>
        </View>
      ) : null}

      <SectionTitle>1. Before you apply</SectionTitle>
      <Card>
        <FitList checks={data.checks} empty="Nothing to check yet." />
      </Card>
      <Card>
        <Text style={{ fontWeight: "700", marginBottom: 6 }}>How you match</Text>
        <MatchCard jobId={id} />
      </Card>

      <SectionTitle>2. Choose the CV you will send</SectionTitle>
      <Card>
        {data.versions.length > 0 ? (
          data.versions.map((v) => (
            <View key={v.id} style={{ marginBottom: 10 }}>
              <Choice
                options={[{ value: String(v.id), label: `${v.label} (v${v.id})` }]}
                value={cv}
                onChange={setCv}
              />
              <Muted style={{ marginTop: -8 }}>
                {v.kind_label} · {longDate(v.created)}
                {v.flagged ? " · you approved the flagged claims" : ""}
              </Muted>
              <Button label="Open this CV" variant="ghost" onPress={() => go(`/cv/${v.id}`)} />
            </View>
          ))
        ) : (
          <Muted>No CV is ready to send yet. Add your CV in Profile.</Muted>
        )}
        <Choice options={[{ value: "none", label: "I am sending a different CV (do not link a version)" }]} value={cv} onChange={setCv} />
        {data.has_flagged ? <Muted>Your tailored CV still has claims we could not match to your own material, so it is not offered. Review it first.</Muted> : null}
      </Card>
      <Card>
        <Button label="Tailor a CV for this job" variant="secondary" busy={make.busy} onPress={tailor} />
        <Muted style={{ marginTop: 4, marginBottom: 12 }}>Makes a new version from your own CV. You review it before it can be sent.</Muted>
        <Choice label="Tone of the cover letter" options={COVER_TONES} value={tone} onChange={setTone} />
        <Button label="Write a cover letter" variant="secondary" busy={make.busy} onPress={letter} />
        <Muted style={{ marginTop: 4 }}>Short, from your own material, checked before you can use it.</Muted>
        {make.error ? <Text style={{ color: colors.danger, marginTop: 6 }}>{make.error}</Text> : null}
        {data.cover_letters.map((l) => (
          <ListItem key={l.id} title={`Letter of ${longDate(l.created)}`} subtitle={l.needs_review ? "Needs review" : "Ready"} onPress={() => go(`/cover/${l.id}`)} />
        ))}
      </Card>

      <SectionTitle>3. Apply on the employer's site</SectionTitle>
      <Card>
        {data.job.url && safeWebUrl(data.job.url) ? (
          <Button label="Open the job posting" icon="open-outline" onPress={() => openLink(data.job.url)} />
        ) : (
          <Muted>This job has no link saved. Apply through whatever place you found it on.</Muted>
        )}
        <Text style={{ fontWeight: "700", marginTop: 14 }}>Applying by email? Start from this draft</Text>
        <Muted style={{ marginBottom: 8 }}>A starting point only. Replace [Your name], attach the CV, and check every statement is true. It is never sent for you.</Muted>
        <Field label="Subject" value={data.draft.subject} onChangeText={() => undefined} editable={false} />
        <Field label="Message" value={data.draft.body} onChangeText={() => undefined} editable={false} multiline style={{ minHeight: 180 }} />
        <View style={{ flexDirection: "row", gap: 8 }}>
          <Button label="Copy subject" variant="secondary" onPress={() => copy("Subject", data.draft.subject)} />
          <Button label="Copy message" variant="secondary" onPress={() => copy("Message", data.draft.body)} />
        </View>
        {data.google.available ? <ListItem icon="mail-outline" title="Send from my Gmail" subtitle="Preview first. Nothing goes until you confirm" onPress={() => go(`/jobs/${id}/mail`)} /> : null}
      </Card>

      <SectionTitle>4. Record what you sent</SectionTitle>
      <Card>
        {data.job.closed ? <Toggle label="This posting looks closed, but I applied anyway" value={confirmClosed} onChange={setConfirmClosed} /> : null}
        <Choice label="How did you apply?" options={[{ value: "", label: "Not recorded" }, ...data.channels]} value={channel} onChange={setChannel} />
        <DateField label="Date applied (blank means today)" value={appliedOn} onChange={setAppliedOn} />
        <Field label="Note (optional)" value={note} onChangeText={setNote} maxLength={300} placeholder="Contact name, reference number, anything you want to remember" />
        <Field label="Remind me to follow up in (days)" value={days} onChangeText={setDays} keyboardType="number-pad" hint={`1 to ${data.max_followup_days} days`} />
        {localError || record.error ? <Text style={{ color: colors.danger, marginBottom: 10 }}>{localError || record.error}</Text> : null}
        <Button label="I submitted it: record it" busy={record.busy} onPress={submit} />
        <Muted style={{ marginTop: 8 }}>Recording sets the status to Applied, saves which CV you sent and a copy of the job description as it is today, and sets the reminder.</Muted>
      </Card>

      <SectionTitle>More for this job</SectionTitle>
      <ListItem icon="mail-outline" title="Mail for this job" onPress={() => go(`/jobs/${id}/mail`)} />
      <ListItem icon="school-outline" title="Interview prep" onPress={() => go(`/jobs/${id}/prep`)} />
      <ListItem icon="chatbubble-outline" title="Write a message" onPress={() => go(`/jobs/${id}/message`)} />
      <Body style={{ height: 0 }}>{""}</Body>
    </Screen>
  );
}
