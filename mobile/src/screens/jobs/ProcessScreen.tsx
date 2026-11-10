import { useLocalSearchParams, useRouter, type Href } from "expo-router";
import React, { useState } from "react";
import { View } from "react-native";

import { pipelineApi, type Stage } from "../../api/pipeline";
import { Badge, Button, Card, Empty, ErrorBox, Loading, Muted, Row, Screen, Select, Text, useTheme } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";
import { whenLabel } from "../pipeline/logic";
import { SuggestMove, type Suggestion } from "../pipeline/parts";

const OUTCOMES = [
  { value: "pending", label: "Scheduled" },
  { value: "done", label: "Completed, waiting to hear" },
  { value: "passed", label: "Passed" },
  { value: "rejected", label: "Failed" },
  { value: "noshow", label: "No-show" },
  { value: "cancelled", label: "Cancelled" },
];

function StageItem({ stage, jobId, last, onSuggest, onChanged }: { stage: Stage; jobId: number; last: boolean; onSuggest: (s: Suggestion) => void; onChanged: () => void }) {
  const { colors } = useTheme();
  const act = useAction();
  const dot: Record<string, { border: string; fill: string }> = {
    pending: { border: colors.border, fill: colors.surface },
    done: { border: colors.accent, fill: colors.accentSoft },
    passed: { border: colors.good, fill: colors.good },
    rejected: { border: colors.danger, fill: colors.danger },
    noshow: { border: colors.warn, fill: colors.warn },
    cancelled: { border: colors.border, fill: colors.surfaceAlt },
  };
  const d = dot[stage.outcome] ?? dot.pending;
  const change = async (outcome: string) => {
    const r = await act.run(() => pipelineApi.interviewOutcome(stage.id, outcome));
    if (!r) return;
    // The outcome only SUGGESTS a status; the person confirms it.
    if (r.suggest_status) onSuggest({ jobId, status: r.suggest_status });
    onChanged();
  };
  return (
    <View style={{ flexDirection: "row" }}>
      <View style={{ alignItems: "center", width: 24 }}>
        <View style={{ width: 16, height: 16, borderRadius: 8, borderWidth: 2, borderColor: d.border, backgroundColor: d.fill, marginTop: 3 }} />
        {!last ? <View style={{ flex: 1, width: 2, backgroundColor: colors.border }} /> : null}
      </View>
      <View style={{ flex: 1, paddingLeft: 10, paddingBottom: last ? 0 : 20 }}>
        <Row style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
          <View style={{ flex: 1 }}>
            <Text style={{ fontWeight: "700" }}>{stage.name}</Text>
            <Muted>{whenLabel(stage.scheduled_local)}</Muted>
          </View>
          <Badge label={stage.outcome_label} color={stage.outcome === "passed" ? colors.good : stage.outcome === "rejected" ? colors.danger : colors.textMuted} />
        </Row>
        {stage.interviewers.length > 0 ? <Text style={{ marginTop: 4 }}>With {stage.interviewers.map((c) => c.name).join(", ")}</Text> : null}
        {stage.where ? <Muted>{stage.where}</Muted> : null}
        <View style={{ marginTop: 8 }}>
          <Select label={`Outcome of ${stage.name}`} value={stage.outcome} onChange={(o) => change(String(o))} options={OUTCOMES} />
        </View>
        {act.error ? <Text style={{ color: colors.danger }}>{act.error}</Text> : null}
      </View>
    </View>
  );
}

/** One job's hiring process: every stage in date order, who you met, and how each went. */
export default function ProcessScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const jobId = Number(id);
  const router = useRouter();
  const load = useLoad(() => pipelineApi.process(jobId), [jobId]);
  const [suggest, setSuggest] = useState<Suggestion | null>(null);
  const data = load.data;
  return (
    <Screen title="Hiring process" onRefresh={load.refresh} refreshing={load.refreshing}>
      {load.loading ? <Loading /> : load.error && !data ? <ErrorBox message={load.error} onRetry={load.reload} /> : null}
      {data ? (
        <>
          <Text style={{ fontSize: 20, fontWeight: "700" }}>{data.job.role}</Text>
          <Text style={{ marginTop: 2 }} onPress={() => router.push(`/companies/${encodeURIComponent(data.job.company)}` as Href)} accessibilityRole="link">
            {data.job.company}
          </Text>
          <Muted style={{ marginBottom: 10 }}>Currently {data.job.status}</Muted>
          <Text style={{ fontSize: 16, fontWeight: "600", marginBottom: 12 }}>{data.summary}</Text>
          {suggest ? <SuggestMove suggestion={suggest} onDone={() => { setSuggest(null); load.reload(); }} /> : null}
          <Button label="Add a stage" onPress={() => router.push(`/interviews?job=${jobId}` as Href)} />
          <View style={{ height: 12 }} />
          {data.stages.length === 0 ? (
            <Empty title="Nothing here yet" hint="When a company invites you to talk, add the first stage and it will show up on this timeline." />
          ) : (
            <Card>
              {data.stages.map((s, i) => (
                <StageItem key={s.id} stage={s} jobId={jobId} last={i === data.stages.length - 1} onSuggest={setSuggest} onChanged={load.reload} />
              ))}
            </Card>
          )}
          {data.offers.length > 0 ? (
            <Row style={{ flexWrap: "wrap" }}>
              <Text>
                You have {data.offers.length} offer{data.offers.length === 1 ? "" : "s"} for this job.
              </Text>
              <Button label="See offers" variant="ghost" onPress={() => router.push("/offers" as Href)} />
            </Row>
          ) : null}
        </>
      ) : null}
    </Screen>
  );
}
