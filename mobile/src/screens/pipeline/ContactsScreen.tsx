import { useRouter, type Href } from "expo-router";
import * as Linking from "expo-linking";
import React, { useState } from "react";
import { View } from "react-native";

import { pipelineApi, type Contact, type ContactList, type ContactValues, type ReferralDraftResult } from "../../api/pipeline";
import { Badge, Button, Card, confirm, Empty, ErrorBox, Field, Loading, Muted, notify, Row, Screen, Select, SectionTitle, Text, useTheme } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";
import { dayLabel, messageText } from "./logic";
import { CopyButton, DateField, FormSheet } from "./parts";

function ContactForm({ item, onDone }: { item?: Contact; onDone: () => void }) {
  const act = useAction();
  const [v, setV] = useState<ContactValues>(
    item
      ? { name: item.name, company: item.company, title: item.title, email: item.email, link: item.link, last_contacted: item.last_contacted, notes: item.notes }
      : { name: "", company: "", title: "", email: "", link: "", last_contacted: "", notes: "" },
  );
  const f = act.fields ?? {};
  const set = (k: keyof ContactValues) => (x: string) => setV({ ...v, [k]: x });
  return (
    <View>
      <Field label="Name" value={v.name} onChangeText={set("name")} maxLength={120} error={f.name} />
      <Field label="Company" value={v.company} onChangeText={set("company")} maxLength={160} error={f.company} />
      <Field label="Their role" value={v.title} onChangeText={set("title")} maxLength={160} error={f.title} />
      <Field label="Email" value={v.email} onChangeText={set("email")} keyboardType="email-address" autoCapitalize="none" hint="Kept for you only. StillOpen never writes to anyone." error={f.email} />
      <Field label="Profile link" value={v.link} onChangeText={set("link")} keyboardType="url" autoCapitalize="none" maxLength={300} error={f.link} />
      <DateField label="Last spoke" value={v.last_contacted} onChange={set("last_contacted")} clearable error={f.last_contacted} />
      <Field label="Notes" value={v.notes} onChangeText={set("notes")} multiline maxLength={2000} error={f.notes} />
      {act.error && !act.fields ? <ErrorBox message={act.error} /> : null}
      <Button
        label={item ? "Save changes" : "Add contact"}
        busy={act.busy}
        onPress={async () => {
          if (await act.run(() => (item ? pipelineApi.editContact(item.id, v) : pipelineApi.addContact(v)))) {
            notify("Contact saved.");
            onDone();
          }
        }}
      />
    </View>
  );
}

function ReferralForm({ data, contactId, onDone }: { data: ContactList; contactId?: number; onDone: () => void }) {
  const act = useAction();
  const [v, setV] = useState({ contact: contactId ? String(contactId) : "", application: "", status: "thinking", note: "" });
  const f = act.fields ?? {};
  return (
    <View>
      <Select label="Who" value={v.contact || null} onChange={(x) => setV({ ...v, contact: String(x) })} options={data.contacts.map((c) => ({ value: String(c.id), label: c.name }))} placeholder="Pick a contact…" />
      <Select label="For which job" value={v.application || null} onChange={(x) => setV({ ...v, application: String(x) })} options={data.jobs.map((j) => ({ value: String(j.id), label: j.label }))} placeholder="Pick a job…" />
      <Select label="Where it stands" value={v.status} onChange={(x) => setV({ ...v, status: String(x) })} options={data.referral_statuses.map((s) => ({ value: s.value, label: s.label }))} />
      <Field label="Note" value={v.note} onChangeText={(x) => setV({ ...v, note: x })} maxLength={300} error={f.note} />
      {act.error ? <ErrorBox message={act.error} /> : null}
      <Button
        label="Add referral"
        busy={act.busy}
        onPress={async () => {
          if (await act.run(() => pipelineApi.addReferral(v))) {
            notify("Referral saved.");
            onDone();
          }
        }}
      />
    </View>
  );
}

/** "Draft a referral request": a short polite message (free template, or polished by the person's own AI). Never sent: the person copies it. */
function ReferralDraft({ contact, data }: { contact: Contact; data: ContactList }) {
  const act = useAction();
  const status = useLoad(() => pipelineApi.assistStatus());
  const first = contact.referrals.find((r) => data.jobs.some((j) => j.id === r.job.id))?.job.id ?? data.jobs[0]?.id;
  const [job, setJob] = useState(first ? String(first) : "");
  const [result, setResult] = useState<ReferralDraftResult | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const run = async (polish: boolean) => {
    const r = await act.run(() => pipelineApi.referralDraft(contact.id, Number(job), polish));
    if (r) {
      setResult(r);
      setSubject(r.subject);
      setBody(r.body);
    }
  };
  return (
    <View>
      <Select label="For which job" value={job || null} onChange={(x) => setJob(String(x))} options={data.jobs.map((j) => ({ value: String(j.id), label: j.label }))} />
      <Row style={{ flexWrap: "wrap", marginBottom: 12 }}>
        <Button label="Write a draft (free)" variant="secondary" busy={act.busy} disabled={!job} onPress={() => run(false)} />
        {status.data?.ai ? <Button label="Polish it with AI" variant="secondary" busy={act.busy} disabled={!job} onPress={() => run(true)} /> : null}
      </Row>
      {act.error ? <ErrorBox message={act.error} /> : null}
      {result ? (
        <View>
          <Field label="Subject" value={subject} onChangeText={setSubject} />
          <Field label="Message" value={body} onChangeText={setBody} multiline />
          {result.flagged_count > 0 ? <Muted style={{ marginBottom: 8 }}>The AI added things you did not give it: {result.flagged.map((x) => x.text).join(", ")}. Remove them unless they are true.</Muted> : null}
          <CopyButton text={messageText({ subject, body })} label="Copy the message" />
          <Muted style={{ marginTop: 8 }}>Replace [Your name] if it is showing. It is never sent for you: paste it into your own email or message.</Muted>
          {result.method === "ai" && result.notice ? <Muted style={{ marginTop: 4 }}>{result.notice}</Muted> : null}
        </View>
      ) : null}
    </View>
  );
}

function ContactCard({ item, data, onEdit, onDraft, onChanged }: { item: Contact; data: ContactList; onEdit: () => void; onDraft: () => void; onChanged: () => void }) {
  const { colors } = useTheme();
  const act = useAction();
  const details = [item.title, item.company].filter(Boolean).join(" at ");
  const remove = async () => {
    if (!(await confirm(`Delete ${item.name}?`, "Their referrals are deleted too."))) return;
    if (await act.run(() => pipelineApi.deleteContact(item.id))) {
      notify("Deleted.");
      onChanged();
    }
  };
  return (
    <Card>
      <Text style={{ fontWeight: "700", fontSize: 16 }}>{item.name}</Text>
      {details ? <Muted>{details}</Muted> : null}
      {item.email ? <Text style={{ marginTop: 4 }}>{item.email}</Text> : null}
      {item.link ? (
        <Text style={{ color: colors.accent, marginTop: 4 }} onPress={() => Linking.openURL(item.link).catch(() => {})} accessibilityRole="link">
          Profile
        </Text>
      ) : null}
      {item.last_contacted ? <Muted style={{ marginTop: 4 }}>Last spoke {dayLabel(item.last_contacted)}</Muted> : null}
      {item.interviewed_you_for.map((i) => (
        <Text key={i.id} style={{ marginTop: 4 }}>
          Interviewed you for {i.label}, {dayLabel(i.when)}
        </Text>
      ))}
      {item.notes ? <Muted style={{ marginTop: 4 }}>{item.notes}</Muted> : null}
      <Row style={{ flexWrap: "wrap", marginTop: 12 }}>
        <Button label="Edit" variant="secondary" onPress={onEdit} />
        {data.jobs.length > 0 ? <Button label="Draft a referral request" variant="secondary" onPress={onDraft} /> : null}
        <Button label="Delete" variant="danger" onPress={remove} />
      </Row>
      {item.referrals.map((r) => (
        <View key={r.id} style={{ marginTop: 12, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 10 }}>
          <Text>
            Referral for {r.job.role} at {r.job.company}
            {r.note ? ` · ${r.note}` : ""}
          </Text>
          <Row style={{ marginTop: 6 }}>
            <Badge label={r.status_label} color={r.status === "submitted" || r.status === "agreed" ? colors.good : colors.textMuted} />
          </Row>
          <View style={{ marginTop: 8 }}>
            <Select
              label="Where the referral stands"
              value={r.status}
              onChange={async (s) => {
                if (await act.run(() => pipelineApi.referralStatus(r.id, String(s)))) onChanged();
              }}
              options={data.referral_statuses.map((s) => ({ value: s.value, label: s.label }))}
            />
          </View>
          <Button
            label="Remove this referral"
            variant="ghost"
            onPress={async () => {
              if (await act.run(() => pipelineApi.deleteReferral(r.id))) {
                notify("Deleted.");
                onChanged();
              }
            }}
          />
        </View>
      ))}
      {act.error ? <Text style={{ color: colors.danger, marginTop: 8 }}>{act.error}</Text> : null}
    </Card>
  );
}

export default function ContactsScreen() {
  const router = useRouter();
  const load = useLoad(() => pipelineApi.contacts());
  const [sheet, setSheet] = useState<null | { kind: "contact"; item?: Contact } | { kind: "referral" } | { kind: "draft"; item: Contact }>(null);
  const data = load.data;
  const close = () => setSheet(null);
  const done = () => {
    close();
    load.reload();
  };
  return (
    <Screen title="Contacts" onRefresh={load.refresh} refreshing={load.refreshing}>
      {load.loading ? <Loading /> : load.error && !data ? <ErrorBox message={load.error} onRetry={load.reload} /> : null}
      {data ? (
        <>
          <Muted style={{ marginBottom: 12 }}>People who can put in a word for you. StillOpen never contacts anyone: it only keeps your notes.</Muted>
          <Row style={{ flexWrap: "wrap", marginBottom: 12 }}>
            <Button label="Add a contact" onPress={() => setSheet({ kind: "contact" })} />
            <Button label="Add a referral" variant="secondary" onPress={() => setSheet({ kind: "referral" })} />
          </Row>
          {data.contacts.length === 0 ? (
            <Empty title="No contacts yet" hint="Add someone you know at a company you are applying to, then note if they could refer you." action={{ label: "Add a contact", onPress: () => setSheet({ kind: "contact" }) }} />
          ) : (
            <>
              <SectionTitle>{data.contacts.length === 1 ? "1 contact" : `${data.contacts.length} contacts`}</SectionTitle>
              {data.contacts.map((c) => (
                <ContactCard key={c.id} item={c} data={data} onEdit={() => setSheet({ kind: "contact", item: c })} onDraft={() => setSheet({ kind: "draft", item: c })} onChanged={load.reload} />
              ))}
            </>
          )}
          <Button label="See companies" variant="ghost" onPress={() => router.push("/companies" as Href)} />
          <FormSheet visible={sheet?.kind === "contact"} title={sheet?.kind === "contact" && sheet.item ? "Edit contact" : "Add a contact"} onClose={close}>
            {sheet?.kind === "contact" ? <ContactForm key={sheet.item?.id ?? "new"} item={sheet.item} onDone={done} /> : null}
          </FormSheet>
          <FormSheet visible={sheet?.kind === "referral"} title="Add a referral" onClose={close}>
            {data.contacts.length === 0 || data.jobs.length === 0 ? (
              <Empty title="Not yet" hint="Add a contact, and a job to your tracker, to note a referral." />
            ) : sheet?.kind === "referral" ? (
              <ReferralForm data={data} onDone={done} />
            ) : null}
          </FormSheet>
          <FormSheet visible={sheet?.kind === "draft"} title={sheet?.kind === "draft" ? `Referral request to ${sheet.item.name}` : ""} onClose={close}>
            {sheet?.kind === "draft" ? <ReferralDraft contact={sheet.item} data={data} /> : null}
          </FormSheet>
        </>
      ) : null}
    </Screen>
  );
}
