// "This came up": tick the interview-prep questions that were really asked, and save one to the question bank.
// <CameUpTick jobId qkey />, <CameUpTally jobId />, <SaveToBank question jobId />, <PracticeQuestions jobId /> (the stored prep list with ticks; makes nothing new).
import React, { useCallback, useEffect, useState } from "react";
import { TouchableOpacity, View } from "react-native";

import { pipelineApi, type PrepGroup, type Tally } from "../../api/pipeline";
import { Button, Ionicons, Loading, Muted, Text, useTheme } from "../../ui";
import { errorText } from "../../ui/useApi";

export function CameUpTick({ jobId, qkey, tally, onTally }: { jobId: number; qkey: string; tally: Tally | null; onTally: (t: Tally) => void }) {
  const { colors } = useTheme();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ticked = tally?.ticked.includes(qkey) ?? false;
  const toggle = async () => {
    setBusy(true);
    setError("");
    try {
      onTally(await pipelineApi.setJobCameUp(jobId, qkey, !ticked));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <View>
      <TouchableOpacity onPress={toggle} disabled={busy || !tally} accessibilityRole="checkbox" accessibilityState={{ checked: ticked }} style={{ flexDirection: "row", alignItems: "center", gap: 10, minHeight: 44 }}>
        <Ionicons name={ticked ? "checkbox" : "square-outline"} size={22} color={ticked ? colors.accent : colors.textMuted} />
        <Text>This came up</Text>
      </TouchableOpacity>
      {error ? <Text style={{ color: colors.danger, fontSize: 12 }}>{error}</Text> : null}
    </View>
  );
}

export function SaveToBank({ question, jobId }: { question: string; jobId?: number }) {
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (saved) return <Muted>In your question bank</Muted>;
  return (
    <View>
      <Button
        label="Save to my question bank"
        variant="secondary"
        busy={busy}
        onPress={async () => {
          setBusy(true);
          setError("");
          try {
            await pipelineApi.addBank({ question: question.slice(0, 400), answer: "", tags: [], job_ids: jobId ? [jobId] : [], interview_ids: [] });
            setSaved(true);
          } catch (e) {
            setError(errorText(e));
          } finally {
            setBusy(false);
          }
        }}
      />
      {error ? <Muted>{error}</Muted> : null}
    </View>
  );
}

/** The job's saved interview-prep questions, each with its tick and a save-to-bank button. Shows a hint when none have been made yet. */
export function PracticeQuestions({ jobId, onOpenPrep }: { jobId: number; onOpenPrep: () => void }) {
  const [groups, setGroups] = useState<PrepGroup[] | null>(null);
  const [tally, setTally] = useState<Tally | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      const [prep, t] = await Promise.all([pipelineApi.storedPrep(jobId), pipelineApi.jobTally(jobId)]);
      setGroups(prep.prep?.groups ?? []);
      setTally(t);
    } catch (e) {
      setError(errorText(e));
    }
  }, [jobId]);
  useEffect(() => {
    load();
  }, [load]);
  if (error) return <Muted>{error}</Muted>;
  if (!groups) return <Loading />;
  if (groups.length === 0 || groups.every((g) => g.questions.length === 0)) {
    return (
      <View>
        <Muted style={{ marginBottom: 8 }}>No practice questions for this job yet. Make them first, then come back to tick the ones that really came up.</Muted>
        <Button label="Open interview prep" variant="secondary" onPress={onOpenPrep} />
      </View>
    );
  }
  return (
    <View>
      {tally?.text ? <Muted style={{ marginBottom: 8 }}>{tally.text}</Muted> : null}
      {groups.map((g) => (
        <View key={g.key} style={{ marginBottom: 10 }}>
          <Text style={{ fontWeight: "700", marginBottom: 4 }}>{g.title}</Text>
          {g.questions.map((q) => (
            <View key={q.id} style={{ marginBottom: 10 }}>
              <Text>{q.question}</Text>
              <CameUpTick jobId={jobId} qkey={q.id} tally={tally} onTally={setTally} />
              <SaveToBank question={q.question} jobId={jobId} />
            </View>
          ))}
        </View>
      ))}
    </View>
  );
}
