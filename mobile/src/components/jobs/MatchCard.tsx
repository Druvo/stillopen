// "How you match": what the posting asks for, each ask ticked only when the person's own material says it (with where), else a gap.
import React, { useCallback, useEffect, useState } from "react";
import { View } from "react-native";

import { jobsApi, type MatchCardData, type MatchRow } from "../../api/jobs";
import { Button, Card, ErrorBox, Field, Loading, Muted, Text, notify, useTheme } from "../../ui";
import { errorText } from "../../ui/useApi";

function AddFact({ jobId, row, onDone }: { jobId: number; row: MatchRow; onDone: (c: MatchCardData) => void }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  if (!open) return <Button label="Add to my profile" variant="secondary" onPress={() => setOpen(true)} />;
  const save = async () => {
    if (!text.trim()) return setProblem("Write the fact in your own words first.");
    setBusy(true);
    setProblem("");
    try {
      const done = await jobsApi.addFact(jobId, text);
      notify(done.message);
      onDone(done.card);
    } catch (e) {
      setProblem(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <View style={{ marginTop: 6 }}>
      <Field
        label={`Your own words about: ${row.text.slice(0, 60)}`}
        value={text}
        onChangeText={setText}
        multiline
        maxLength={300}
        placeholder="For example: I have run this in production for two years."
        hint="Only add something that is true. It is saved in your notes, under Facts I added from job matches, and you can delete it any time."
        error={problem || undefined}
      />
      <View style={{ flexDirection: "row", gap: 8 }}>
        <Button label="Save to my notes" busy={busy} onPress={save} />
        <Button label="Cancel" variant="ghost" onPress={() => setOpen(false)} />
      </View>
    </View>
  );
}

export function MatchCard({ jobId }: { jobId: number }) {
  const { colors } = useTheme();
  const [card, setCard] = useState<MatchCardData | null>(null);
  const [error, setError] = useState("");
  const [reading, setReading] = useState(false);
  const [problem, setProblem] = useState("");
  const load = useCallback(async () => {
    try {
      setCard(await jobsApi.matchCard(jobId));
      setError("");
    } catch (e) {
      setError(errorText(e));
    }
  }, [jobId]);
  useEffect(() => {
    void load();
  }, [load]);
  if (error) return <ErrorBox message={error} onRetry={load} />;
  if (!card) return <Loading />;
  const readWithAi = async () => {
    setReading(true);
    setProblem("");
    try {
      setCard(await jobsApi.matchCardAi(jobId));
    } catch (e) {
      setProblem(errorText(e));
    } finally {
      setReading(false);
    }
  };
  const mark = (s: MatchRow["state"]) =>
    s === "covered"
      ? { icon: "✓", words: "Covered", color: colors.good }
      : s === "gap"
        ? { icon: "✗", words: "Not shown in your material", color: colors.warn }
        : { icon: "–", words: "Not checked yet", color: colors.textMuted };
  return (
    <View>
      <Muted style={{ marginBottom: 8 }}>{card.summary}</Muted>
      {card.empty === "no_material" ? <Muted style={{ marginBottom: 8 }}>Add your CV in Profile and these tick themselves.</Muted> : null}
      {card.requirements.map((row) => {
        const m = mark(row.state);
        return (
          <Card key={row.id} style={{ marginBottom: 8, padding: 12 }}>
            <Text accessibilityLabel={`${m.words}: ${row.text}`}>
              <Text style={{ color: m.color, fontWeight: "700" }}>{m.icon} </Text>
              {row.text}
            </Text>
            {row.state === "covered" && row.source ? (
              <Muted style={{ marginTop: 4 }}>
                {row.source.label}
                {row.snippet ? ` · "${row.snippet}"` : ""}
              </Muted>
            ) : null}
            {row.state === "gap" ? (
              <View style={{ marginTop: 4 }}>
                <Muted style={{ marginBottom: 6 }}>{row.hint || "Nothing in your material says this yet."}</Muted>
                <AddFact jobId={jobId} row={row} onDone={setCard} />
              </View>
            ) : null}
          </Card>
        );
      })}
      {card.excerpt ? <Muted>This is only the start of the posting, so some requirements may be missing.</Muted> : null}
      {card.can_ai && card.method === "keywords" && card.empty !== "no_description" ? (
        <View style={{ marginTop: 8 }}>
          <Button label="Read it with my AI" variant="secondary" busy={reading} onPress={readWithAi} />
          <Muted style={{ marginTop: 4 }}>Uses your own AI key. The list always comes from the posting's own words.</Muted>
        </View>
      ) : null}
      {problem ? <Text style={{ color: colors.danger, marginTop: 6 }}>{problem}</Text> : null}
    </View>
  );
}

export function FitList({ checks, empty }: { checks: { level: "ok" | "warn" | "info"; text: string }[]; empty: string }) {
  const { colors } = useTheme();
  if (checks.length === 0) return <Muted>{empty}</Muted>;
  return (
    <View style={{ gap: 6 }}>
      {checks.map((c, i) => (
        <Text key={i} accessibilityLabel={`${c.level === "ok" ? "Good" : c.level === "warn" ? "Take care" : "Note"}: ${c.text}`}>
          <Text style={{ color: c.level === "ok" ? colors.good : c.level === "warn" ? colors.warn : colors.textMuted, fontWeight: "700" }}>
            {c.level === "ok" ? "✓ " : c.level === "warn" ? "! " : "i "}
          </Text>
          {c.text}
        </Text>
      ))}
    </View>
  );
}
