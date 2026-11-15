// Add a job: paste a link to read it, or type it in. Nothing is saved until Save.
import { useLocalSearchParams, useRouter, type Href } from "expo-router";
import React, { useEffect, useState } from "react";
import { View } from "react-native";

import { jobsApi, type Duplicate } from "../../api/jobs";
import { DateField } from "../../components/jobs/DateField";
import { Body, Button, Card, Field, Muted, Screen, SectionTitle, Text, notify, useTheme } from "../../ui";
import { errorText, useAction } from "../../ui/useApi";
import { duplicateMessage, fillFromParsed, filledMessage, mergePrefill } from "./logic";

const BLANK: Record<string, string> = { company: "", role: "", url: "", deadline: "", description: "", notes: "" };

export default function AddJobScreen() {
  const router = useRouter();
  const { colors } = useTheme();
  const { url: urlParam } = useLocalSearchParams<{ url?: string }>();
  const [values, setValues] = useState<Record<string, string>>(BLANK);
  const [link, setLink] = useState("");
  const [reading, setReading] = useState(false);
  const [readNote, setReadNote] = useState<{ error: boolean; text: string } | null>(null);
  const [duplicate, setDuplicate] = useState<Duplicate | null>(null);
  const [fillNote, setFillNote] = useState("");
  const [filling, setFilling] = useState(false);
  const save = useAction();

  const set = (name: string) => (v: string) => {
    if (name === "company" || name === "role" || name === "url") setDuplicate(null);
    setValues((s) => ({ ...s, [name]: v }));
  };

  async function readLinkFor(target: string) {
    setReading(true);
    setReadNote(null);
    try {
      const prefill = await jobsApi.quickAdd(target.trim());
      setDuplicate(prefill.duplicate ?? null);
      if (prefill.blocked_host) {
        setValues((v) => ({ ...v, url: prefill.url }));
        setLink(prefill.url);
        setReadNote({ error: false, text: prefill.message || `${prefill.blocked_host} does not let other apps read its pages. We kept the link: paste the text of the job into the description box below.` });
        return;
      }
      setValues((v) => mergePrefill(v, prefill));
      setReadNote({ error: false, text: "We read this from the link. It is a best guess, so check the company, the role and the description before you save." });
    } catch (e) {
      setReadNote({ error: true, text: errorText(e) });
    } finally {
      setReading(false);
    }
  }

  useEffect(() => {
    // opened with ?url=... (the browser extension or a shared link): read it straight away
    if (urlParam) {
      setLink(urlParam);
      void readLinkFor(urlParam);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlParam]);

  async function fillFromText() {
    setFilling(true);
    setFillNote("");
    try {
      const r = await jobsApi.parseText(values.description);
      const result = fillFromParsed(values, r.fields);
      setValues(result.values);
      if (result.values.company !== values.company || result.values.role !== values.role || result.values.url !== values.url) setDuplicate(null);
      setFillNote(filledMessage(result.filled, r.notice));
    } catch (e) {
      setFillNote(errorText(e));
    } finally {
      setFilling(false);
    }
  }

  async function submit(allow: boolean) {
    const r = await save.run(() => jobsApi.addJob(values, allow));
    if (!r) return;
    if (!r.ok) {
      setDuplicate(r.duplicate);
      return;
    }
    notify(`Saved ${r.data.company} - ${r.data.role}.`, "Next, open it and press Check my fit to see how well it suits you.");
    router.replace(`/job/${r.data.id}` as Href);
  }

  return (
    <Screen title="Add a job">
      <Muted style={{ marginBottom: 12 }}>Found a role somewhere? Paste its link and we will read it for you, or type it in. Nothing is saved until you press Save.</Muted>
      <Card>
        <Field label="Paste a link to the job" value={link} onChangeText={setLink} placeholder="https://" autoCapitalize="none" autoCorrect={false} keyboardType="url" />
        <Button label="Read the link" variant="secondary" busy={reading} disabled={!link.trim()} onPress={() => readLinkFor(link)} />
        <Muted style={{ marginTop: 8 }}>LinkedIn, Indeed, Glassdoor and some other sites do not let us read their pages. We keep the link and you paste the job text below.</Muted>
        {readNote ? <Text style={{ marginTop: 8, color: readNote.error ? colors.danger : colors.text }}>{readNote.text}</Text> : null}
      </Card>

      <SectionTitle>The job</SectionTitle>
      <Card>
        <Field label="Company" value={values.company} onChangeText={set("company")} error={save.fields?.company} autoCorrect={false} />
        <Field label="Role" value={values.role} onChangeText={set("role")} error={save.fields?.role} />
        <Field label="Link to the posting" value={values.url} onChangeText={set("url")} error={save.fields?.url} autoCapitalize="none" keyboardType="url" />
        <DateField label="Apply by (if it says)" value={values.deadline} onChange={set("deadline")} error={save.fields?.deadline} />
        <Field
          label="The job description"
          value={values.description}
          onChangeText={set("description")}
          error={save.fields?.description}
          multiline
          hint="Paste the text of the posting here. Or leave this empty and we will read it from the link."
          style={{ minHeight: 160 }}
        />
        <Button label="Fill the form from pasted text" variant="secondary" busy={filling} disabled={values.description.trim().length < 20} onPress={fillFromText} />
        {values.description.trim().length < 20 ? <Muted style={{ marginTop: 4 }}>Paste the job text in the box above first, then press this.</Muted> : null}
        {fillNote ? <Body style={{ marginTop: 8 }}>{fillNote}</Body> : null}
        <View style={{ height: 14 }} />
        <Field label="Your own notes" value={values.notes} onChangeText={set("notes")} error={save.fields?.notes} multiline />
        {save.error && !duplicate ? <Text style={{ color: colors.danger, marginBottom: 10 }}>{save.error}</Text> : null}
        {duplicate ? (
          <Card style={{ borderColor: colors.warn }}>
            <Text style={{ fontWeight: "700" }}>{duplicateMessage(duplicate)}</Text>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
              <Button label="Open it" variant="secondary" onPress={() => router.push(`/job/${duplicate.id}` as Href)} />
              <Button label="Add this one anyway" variant="secondary" busy={save.busy} onPress={() => submit(true)} />
            </View>
          </Card>
        ) : null}
        <Button label="Save job" busy={save.busy} onPress={() => submit(false)} />
        <Button label="Cancel" variant="ghost" onPress={() => router.back()} />
      </Card>
      <Muted style={{ marginTop: 8 }}>Importing a whole spreadsheet, LinkedIn export or saved-job email needs a file or a long preview: use the website for those.</Muted>
    </Screen>
  );
}
