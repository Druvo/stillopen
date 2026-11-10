import { useLocalSearchParams } from "expo-router";
import React, { useState } from "react";
import { View } from "react-native";

import { assistApi, findingsText, KINDS, type MessageDraftResult, type MessageKind } from "../../api/assist";
import { Body, Button, Card, Choice, ErrorBox, Field, Loading, Muted, Screen, Text, useTheme } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";
import { AiNotice, CopyButton, NoKeyLine, Problem } from "./parts";

/** A short email draft for a job: a free template, or the same polished by the person's own AI. Only ever copied, never sent. */
export default function MessageDraftScreen() {
  const { id: raw, kind: kindParam } = useLocalSearchParams<{ id: string; kind?: string }>();
  const jobId = Number(raw);
  const { colors } = useTheme();
  const status = useLoad(() => assistApi.status(), []);
  const initial = KINDS.some((k) => k.value === kindParam) ? (kindParam as MessageKind) : "follow_up";
  const [kind, setKind] = useState<MessageKind>(initial);
  const [note, setNote] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [result, setResult] = useState<MessageDraftResult | null>(null);
  const [polishing, setPolishing] = useState(false);
  const act = useAction();
  const ai = status.data?.ai ?? false;

  const write = async (polish: boolean) => {
    setPolishing(polish);
    const r = await act.run(() => assistApi.message(jobId, { kind, note, polish }));
    if (r) {
      setResult(r);
      setSubject(r.subject);
      setBody(r.body);
    }
  };

  return (
    <Screen title="Write a message" onRefresh={status.refresh} refreshing={status.refreshing}>
      {status.loading ? (
        <Loading />
      ) : status.error && !status.data ? (
        <ErrorBox message={status.error} onRetry={status.reload} />
      ) : (
        <>
          <Card>
            <Choice label="What do you want to write?" options={KINDS} value={kind} onChange={setKind} />
            <Field label="Anything you want it to mention (optional)" value={note} onChangeText={setNote} multiline maxLength={500} />
            <Button label={act.busy && !polishing ? "Writing…" : "Write a draft (free)"} variant="secondary" busy={act.busy && !polishing} disabled={act.busy} onPress={() => write(false)} />
            {ai ? (
              <Button label={act.busy && polishing ? "Polishing…" : "Polish it with AI"} variant="secondary" style={{ marginTop: 8 }} busy={act.busy && polishing} disabled={act.busy} onPress={() => write(true)} />
            ) : (
              <View style={{ marginTop: 12 }}>
                <Muted style={{ marginBottom: 6 }}>Want it polished by AI?</Muted>
                <NoKeyLine />
              </View>
            )}
            <Problem message={act.error} />
          </Card>

          {result ? (
            <Card>
              <Field label="Subject" value={subject} onChangeText={setSubject} />
              <Field label="Message" value={body} onChangeText={setBody} multiline numberOfLines={10} />
              {result.flagged_count > 0 ? (
                <Text style={{ color: colors.warn, fontSize: 13, marginBottom: 8 }}>The AI added things you did not give it: {findingsText(result.flagged)}. Remove them unless they are true.</Text>
              ) : null}
              <CopyButton text={`Subject: ${subject}\n\n${body}`} label="Copy the message" />
              <Body style={{ fontSize: 12, marginTop: 10, color: colors.textMuted }}>Replace [Your name] if it is showing, and check every statement is true. It is never sent for you.</Body>
              {result.method === "ai" ? <AiNotice>{result.notice}</AiNotice> : null}
            </Card>
          ) : null}
        </>
      )}
    </Screen>
  );
}
