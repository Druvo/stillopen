import { useLocalSearchParams, useRouter, type Href } from "expo-router";
import React, { useState } from "react";
import { View } from "react-native";

import { coverApi, settingsApi, type CoverTone } from "../../api/cv";
import { useTheme } from "../../context/ThemeContext";
import { Button, Card, Choice, confirm, ErrorBox, Field, Loading, Muted, notify, Screen, Text } from "../../ui";
import { errorText, useAction, useLoad } from "../../ui/useApi";
import { letterSaid } from "./logic/messages";
import { Collapsible, Findings, RefinePanel, shareTextFile, useFlag, when, WritingCheck } from "./parts";

const TONES: { value: CoverTone; label: string }[] = [
  { value: "warm", label: "Warm" },
  { value: "direct", label: "Direct" },
  { value: "formal", label: "Formal" },
];

export default function CoverLetterScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const coverId = Number(id);
  const router = useRouter();
  const { colors } = useTheme();
  const { data: letter, setData, error, loading, refreshing, refresh, reload } = useLoad(() => coverApi.get(coverId), [coverId]);
  const writingCheck = useFlag(settingsApi.writingCheckEnabled, false);
  const savedTone = useFlag(settingsApi.coverTone, "warm" as CoverTone);
  const [tone, setTone] = useState<CoverTone | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const act = useAction();

  if (loading) return <Screen title="Cover letter"><Loading /></Screen>;
  if (!letter) return <Screen title="Cover letter"><ErrorBox message={error ?? "We could not find that letter."} onRetry={reload} /></Screen>;

  const content = text ?? letter.content;
  const changed = text !== null && text !== letter.content;
  const chosenTone = tone ?? savedTone;

  async function save() {
    const next = await act.run(() => coverApi.save(coverId, content));
    if (next) {
      setData(next);
      setText(null);
      setNote(next.flagged ? "Saved. Some claims are not in your own material, check them above." : "Saved.");
    }
  }

  async function approve() {
    const done = await act.run(() => coverApi.approve(coverId));
    if (done) {
      setNote("Approved.");
      await reload();
    }
  }

  async function remove() {
    if (!(await confirm("Delete this letter?", "This cannot be undone."))) return;
    const done = await act.run(() => coverApi.remove(coverId));
    if (done) router.replace(`/jobs/${letter!.job.id}/apply` as Href);
  }

  async function rewrite() {
    if (!(await confirm("Write a new letter?", `A new ${chosenTone} letter is written for this job and this one is kept.`, "Write it"))) return;
    const made = await act.run(() => coverApi.write(letter!.job.id, "auto", chosenTone));
    if (made) {
      const said = letterSaid(made);
      notify(said.tone === "error" ? "Check this letter" : "New letter ready", said.text);
      router.replace({ pathname: "/cover/[id]", params: { id: String(made.id) } });
    }
  }

  async function download() {
    try {
      await shareTextFile(letter!.content, `cover-letter-${letter!.job.company}.txt`);
    } catch (e) {
      notify("Could not share", errorText(e));
    }
  }

  return (
    <Screen title={`Cover letter for ${letter.job.company}`} onRefresh={refresh} refreshing={refreshing}>
      <Text style={{ color: colors.accent, marginBottom: 6 }} accessibilityRole="link" onPress={() => router.push(`/jobs/${letter.job.id}/apply` as Href)}>
        Back to applying for {letter.job.role}
      </Text>
      <Muted style={{ marginBottom: 10 }}>
        {letter.source_label}
        {letter.provider ? ` (${letter.provider})` : ""} - {when(letter.updated_at)}
      </Muted>
      {act.error ? <ErrorBox message={act.error} /> : null}
      {note ? <Text style={{ color: colors.good, marginBottom: 10 }}>{note}</Text> : null}

      <Findings items={letter.check_report} thing="letter" approved={letter.approved} approvedAt={letter.approved_at} busy={act.busy} onApprove={approve} />

      <Card>
        <Field
          label="Letter"
          value={content}
          onChangeText={setText}
          multiline
          style={{ minHeight: 320, fontSize: 14, lineHeight: 21 }}
          hint="Saving checks the text again. The letter is never sent for you; copy or share it and send it yourself."
          error={act.fields?.content}
        />
        <Button label="Save" onPress={save} busy={act.busy} disabled={!changed} />
      </Card>

      <Card>
        <Text style={{ fontWeight: "700", marginBottom: 8 }}>Download</Text>
        {letter.downloads ? (
          <View style={{ gap: 8 }}>
            <Button label="Share as plain text" icon="share-outline" onPress={download} />
            <Muted>The Word version is available on the website.</Muted>
          </View>
        ) : (
          <Muted>Downloads unlock after you review the flagged items and approve this letter.</Muted>
        )}
      </Card>

      <Collapsible title="Ask for changes">
        <RefinePanel kind="cover" id={coverId} flagged={letter.source === "ai" && !letter.approved ? letter.check_report : []} onLetter={() => { setText(null); reload(); }} />
      </Collapsible>

      <Collapsible title="Write it again in another tone">
        <Choice label="Tone" options={TONES} value={chosenTone} onChange={setTone} />
        <Button label="Write a new letter" variant="secondary" onPress={rewrite} busy={act.busy} />
      </Collapsible>

      {writingCheck ? <WritingCheck run={() => coverApi.writingCheck(coverId)} /> : null}

      <View style={{ marginTop: 8 }}>
        <Button label="Delete this letter" variant="danger" onPress={remove} busy={act.busy} />
      </View>
    </Screen>
  );
}
