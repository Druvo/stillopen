import { useLocalSearchParams, useRouter } from "expo-router";
import React, { useEffect, useState } from "react";
import { View } from "react-native";

import { prepApi, type Tally } from "../../api/prep";
import { Badge, Body, Button, Card, Empty, ErrorBox, Loading, Muted, Screen, Text, useTheme } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";
import { CameUpTick, Problem, SourceLinks, TickRow } from "./parts";

export default function PrepTodayScreen() {
  const { id: raw } = useLocalSearchParams<{ id: string }>();
  const id = Number(raw);
  const router = useRouter();
  const { colors } = useTheme();
  const act = useAction();
  const { data, error, loading, refreshing, refresh, reload } = useLoad(() => prepApi.today(id), [id]);
  const [picked, setPicked] = useState<Record<number, number[]>>({});
  const [tally, setTally] = useState<Tally | null>(null);
  const finished = data?.finished ?? false;

  useEffect(() => {
    if (finished) prepApi.planTally(id).then(setTally, () => undefined);
  }, [finished, id]);

  const choose = (qid: number, kind: string, index: number) =>
    setPicked((p) => {
      const current = p[qid] ?? [];
      if (kind === "multi") return { ...p, [qid]: current.includes(index) ? current.filter((i) => i !== index) : [...current, index] };
      return { ...p, [qid]: [index] };
    });

  return (
    <Screen title="Today's practice" onRefresh={refresh} refreshing={refreshing}>
      {loading ? (
        <Loading />
      ) : error && !data ? (
        <ErrorBox message={error.includes("Start the plan") ? error : `${error} Start the plan first, then come back for today's practice.`} onRetry={reload} />
      ) : !data ? null : (
        <>
          <Muted style={{ marginBottom: 10 }}>
            {data.plan.title}
            {data.streak ? ` · ${data.streak} day${data.streak === 1 ? "" : "s"} in a row` : ""}
          </Muted>
          {data.rows.length === 0 ? (
            <Empty title="No questions today" hint="This plan has no quiz questions yet. Go back to the plan and keep working through the lessons." action={{ label: "Back to the plan", onPress: () => router.back() }} />
          ) : null}
          {data.finished ? (
            <Card>
              <Text style={{ fontWeight: "700", fontSize: 18 }}>
                {data.right} of {data.total} right
              </Text>
              <Body style={{ marginTop: 6 }}>
                {data.right === data.total
                  ? "All of them. Nicely done."
                  : data.right === 0
                    ? "None this time, which is useful to know. Read the explanations below; the questions you missed will come back."
                    : "Read the explanations below, especially for the ones you missed. They will come back until they stick."}
              </Body>
              <Muted style={{ marginTop: 4 }}>Come back tomorrow for the next set.{data.streak ? ` That keeps your ${data.streak}-day run going.` : ""}</Muted>
            </Card>
          ) : data.rows.length > 0 ? (
            <Muted style={{ marginBottom: 12 }}>
              {data.total} question{data.total === 1 ? "" : "s"}, about five minutes. Answer them all, then send. Nothing here is graded by anyone but you.
            </Muted>
          ) : null}
          {!data.finished && data.weak_topics.length > 0 ? (
            <Card>
              <Body>
                Worth another look: <Text style={{ fontWeight: "700" }}>{data.weak_topics.map((t) => t.title).join(", ")}</Text>. {data.rows[0]?.review ? "The first question is from there." : ""}
              </Body>
            </Card>
          ) : null}
          {data.finished && tally?.text ? <Muted style={{ marginBottom: 8 }}>{tally.text}</Muted> : null}
          <Problem message={act.error} />

          {data.rows.map((row, n) => (
            <Card key={row.id} style={data.finished ? { borderColor: row.right ? colors.good : colors.danger } : undefined}>
              <Muted>
                Question {n + 1} · {row.topic}
                {row.review ? " · another look" : ""}
              </Muted>
              <Text style={{ fontSize: 17, fontWeight: "700", marginVertical: 6 }}>{row.prompt}</Text>
              {!data.finished && row.kind === "multi" ? <Muted style={{ marginBottom: 6 }}>Pick every answer that applies.</Muted> : null}
              {row.choices.map((choice, i) =>
                data.finished ? (
                  <View key={i} style={{ marginBottom: 6, flexDirection: "row", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                    {row.correct?.includes(i) ? <Badge label="right answer" color={colors.good} /> : null}
                    {row.chosen?.includes(i) ? <Badge label="your pick" /> : null}
                    <Text style={{ fontSize: 14, flexShrink: 1 }}>{choice}</Text>
                  </View>
                ) : (
                  <TickRow key={i} label={choice} checked={(picked[row.id] ?? []).includes(i)} onPress={() => choose(row.id, row.kind, i)} />
                ),
              )}
              {data.finished ? (
                <>
                  <Body style={{ marginTop: 8 }}>{row.explanation}</Body>
                  <Muted style={{ marginTop: 6 }}>Read more:</Muted>
                  <SourceLinks sources={row.sources ?? []} />
                  <CameUpTick ticked={tally?.ticked.includes(row.id) ?? false} onSet={async (value) => setTally(await prepApi.setPlanCameUp(row.id, value))} />
                </>
              ) : null}
            </Card>
          ))}

          {!data.finished && data.rows.length > 0 ? (
            (() => {
              const unanswered = data.rows.filter((r) => (picked[r.id] ?? []).length === 0).length;
              return (
                <Button
                  label={unanswered > 0 ? `Answer ${unanswered} more to send` : "Send my answers"}
                  disabled={unanswered > 0}
                  busy={act.busy}
                  onPress={async () => {
                    const sent = await act.run(() => prepApi.answer(id, Object.fromEntries(Object.entries(picked).map(([k, v]) => [k, v]))));
                    if (sent) {
                      setPicked({});
                      await reload();
                    }
                  }}
                />
              );
            })()
          ) : null}
          <Button label="Back to the plan" variant="ghost" style={{ marginTop: 10 }} onPress={() => router.back()} />
        </>
      )}
    </Screen>
  );
}
