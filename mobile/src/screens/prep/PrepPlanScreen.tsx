import { useLocalSearchParams, useRouter } from "expo-router";
import React, { useEffect, useState } from "react";
import { View } from "react-native";

import { ApiError } from "../../api/client";
import { prepApi, type Lesson, type Plan, type Question } from "../../api/prep";
import { Badge, Body, Button, Card, confirm, Empty, ErrorBox, Loading, Muted, notify, Screen, SectionTitle, Text, useTheme } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";
import { Bar, Problem, SourceLinks, TickRow } from "./parts";
import { PREP_OFF_HINT, PREP_OFF_TITLE } from "./PrepListScreen";

function QuestionReview({ question, busy, onRemove }: { question: Question; busy: boolean; onRemove: () => void }) {
  const { colors } = useTheme();
  return (
    <View style={{ marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: colors.border }}>
      <Text style={{ fontWeight: "700", fontSize: 14 }}>
        {question.prompt} <Text style={{ fontWeight: "400", color: colors.textMuted }}>({question.kind_label.toLowerCase()})</Text>
      </Text>
      {question.choices.map((choice, i) => (
        <Text key={i} style={{ fontSize: 14, marginTop: 4 }}>
          {String.fromCharCode(65 + i)}. {choice} {question.correct.includes(i) ? "(correct)" : ""}
        </Text>
      ))}
      <Muted style={{ marginTop: 6 }}>{question.explanation}</Muted>
      <SourceLinks sources={question.sources} />
      <Button label="Remove this question" variant="danger" disabled={busy} onPress={onRemove} />
    </View>
  );
}

function LessonCard({ lesson, plan, busy, onTick, onRemoveLesson, onRemoveQuestion }: { lesson: Lesson; plan: Plan; busy: boolean; onTick: () => void; onRemoveLesson: () => void; onRemoveQuestion: (id: number) => void }) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  const started = plan.status === "active" || plan.status === "done";
  return (
    <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 12, padding: 12, marginTop: 10 }}>
      {started ? <TickRow label={lesson.title} checked={lesson.done} disabled={busy} onPress={onTick} /> : <Text style={{ fontWeight: "700", fontSize: 15 }}>{lesson.title}</Text>}
      {lesson.gap ? (
        <View style={{ marginTop: 4 }}>
          <Badge label={lesson.gap} />
        </View>
      ) : null}
      {lesson.topics.length > 0 ? <Muted style={{ marginTop: 4 }}>{lesson.topics.join(" · ")}</Muted> : null}
      <Text style={{ color: colors.textMuted, fontSize: 13, marginTop: 8 }}>Read:</Text>
      <SourceLinks sources={lesson.sources} />
      {plan.status === "draft" && lesson.questions && lesson.questions.length > 0 ? (
        <>
          <Button label={open ? "Hide quiz questions" : `Quiz questions (${lesson.questions.length})`} variant="ghost" onPress={() => setOpen(!open)} />
          {open ? lesson.questions.map((q) => <QuestionReview key={q.id} question={q} busy={busy} onRemove={() => onRemoveQuestion(q.id)} />) : null}
        </>
      ) : null}
      {plan.status === "draft" ? <Button label="Remove lesson" variant="danger" disabled={busy} onPress={onRemoveLesson} /> : null}
    </View>
  );
}

export default function PrepPlanScreen() {
  const { id: raw } = useLocalSearchParams<{ id: string }>();
  const id = Number(raw);
  const router = useRouter();
  const { colors } = useTheme();
  const act = useAction();
  const { data, error, loading, refreshing, refresh, reload } = useLoad(async () => {
    try {
      return { off: false, plan: await prepApi.plan(id) };
    } catch (e) {
      // A plan that is not there and a feature that is switched off both answer 404; the list screen tells them apart.
      if (e instanceof ApiError && e.status === 404) {
        try {
          await prepApi.list();
          return { off: false, plan: null as Plan | null };
        } catch {
          return { off: true, plan: null as Plan | null };
        }
      }
      throw e;
    }
  }, [id]);
  const plan = data?.plan ?? null;

  // The page updates itself while the plan is being written.
  const generating = plan?.status === "generating";
  useEffect(() => {
    if (!generating) return;
    const timer = setInterval(() => void reload(), 6000);
    return () => clearInterval(timer);
  }, [generating, reload]);

  const run = async (fn: () => Promise<unknown>) => {
    const done = await act.run(async () => {
      await fn();
      return true;
    });
    if (done) await reload();
  };

  const started = plan?.status === "active" || plan?.status === "done";
  const discard = async () => {
    if (started && !(await confirm("Delete this plan and your progress?", "This cannot be undone.", "Delete"))) return;
    const ok = await act.run(async () => {
      await prepApi.discard(id);
      return true;
    });
    if (ok) {
      notify("Prep plan discarded.");
      router.replace("/prep" as never);
    }
  };
  // The new plan is made first and the failed one only discarded after, so a refused request leaves the old plan (and its reason) on screen.
  const tryAgain = async (jobId: number) => {
    const made = await act.run(() => prepApi.create(jobId));
    if (!made) return;
    if (made.id !== id) await prepApi.discard(id).catch(() => undefined);
    router.replace(`/prep/${made.id}` as never);
  };

  return (
    <Screen title={plan?.title || "Prep plan"} onRefresh={refresh} refreshing={refreshing}>
      {loading ? (
        <Loading />
      ) : data?.off ? (
        <Empty title={PREP_OFF_TITLE} hint={PREP_OFF_HINT} />
      ) : error && !plan ? (
        <ErrorBox message={error} onRetry={reload} />
      ) : !plan ? (
        <Empty title="We could not find that plan" hint="It may have been discarded. Go back to your prep plans." action={{ label: "My prep plans", onPress: () => router.replace("/prep" as never) }} />
      ) : (
        <>
          {plan.job ? <Muted style={{ marginBottom: 8 }}>{`For ${plan.job.role} at ${plan.job.company}`}</Muted> : null}
          <Problem message={act.error} />

          {plan.status === "generating" ? (
            <Card>
              <Text style={{ fontWeight: "700", fontSize: 16 }}>Writing your plan…</Text>
              <Body style={{ marginVertical: 8 }}>{plan.progress || "Starting"}. This takes a few minutes and uses your own AI account. This page updates by itself, and you can leave it and come back.</Body>
              <Bar percent={35} />
            </Card>
          ) : null}

          {plan.status === "failed" ? (
            <Card style={{ borderColor: colors.danger }}>
              <Text style={{ fontWeight: "700", fontSize: 16 }}>This plan could not be written</Text>
              <Body style={{ marginVertical: 8 }}>{plan.error || "Something went wrong."}</Body>
              {plan.job ? <Button label="Try again" busy={act.busy} onPress={() => tryAgain(plan.job!.id)} /> : null}
              <Button label="Discard" variant="secondary" style={{ marginTop: 8 }} onPress={discard} />
            </Card>
          ) : null}

          {plan.status === "draft" || started ? (
            <>
              {plan.summary ? <Body style={{ fontSize: 17, marginBottom: 12 }}>{plan.summary}</Body> : null}
              {plan.status === "draft" ? (
                <Card>
                  <Body>
                    <Text style={{ fontWeight: "700" }}>This is a draft. </Text>
                    Read it over, take out anything you do not want, then press Start this plan. The AI wrote it from your CV and the job, and every lesson and question cites an official source. Quizzes are only as good
                    as the source behind them, so open a link if an answer surprises you.
                    {plan.unchecked_links > 0 ? ` ${plan.unchecked_links} question${plan.unchecked_links === 1 ? "" : "s"} cite a link we could not open from here. They are marked below; the site may just block automatic visits.` : ""}
                  </Body>
                  <Button
                    label="Start this plan"
                    busy={act.busy}
                    style={{ marginTop: 12 }}
                    onPress={() =>
                      run(async () => {
                        await prepApi.start(id);
                        notify("Your prep plan has started. Tick lessons off as you finish them.");
                      })
                    }
                  />
                  <Button label="Discard" variant="secondary" style={{ marginTop: 8 }} onPress={discard} />
                </Card>
              ) : (
                <Card>
                  <Text style={{ fontWeight: "700", fontSize: 16 }}>
                    {plan.lessons_done} of {plan.lessons_total} lessons done
                  </Text>
                  <Muted>
                    {plan.hours_per_week} hours a week{plan.status === "done" ? " · finished" : ""}
                  </Muted>
                  <Bar percent={plan.percent} />
                  <Muted>
                    {plan.question_count} quiz question{plan.question_count === 1 ? "" : "s"}
                    {plan.streak ? ` · ${plan.streak} day${plan.streak === 1 ? "" : "s"} in a row` : ""}. Lessons you tick off count as studied for this job the next time you check your fit.
                  </Muted>
                  {plan.question_count > 0 ? (
                    <Button
                      label={plan.done_today ? "See today's answers" : "Today's practice"}
                      variant={plan.done_today ? "secondary" : "primary"}
                      style={{ marginTop: 12 }}
                      onPress={() => router.push(`/prep/${id}/today` as never)}
                    />
                  ) : null}
                  {plan.weak_topics.length > 0 ? (
                    <Body style={{ marginTop: 12 }}>
                      Worth another look: <Text style={{ fontWeight: "700" }}>{plan.weak_topics.map((t) => t.title).join(", ")}</Text>. You missed different questions on {plan.weak_topics.length === 1 ? "it" : "them"} recently, so
                      they will come up again until you have answered well on three separate days.
                    </Body>
                  ) : null}
                </Card>
              )}

              {plan.gap_skills.length > 0 ? (
                <Card>
                  <Text style={{ fontWeight: "700", fontSize: 16, marginBottom: 6 }}>What this plan closes</Text>
                  {plan.gap_skills.map((g) => (
                    <Body key={g.skill} style={{ marginBottom: 6 }}>
                      <Text style={{ fontWeight: "700" }}>{g.skill}</Text>: {g.why} <Text style={{ color: colors.textMuted }}>(your CV: {g.cv_evidence})</Text>
                    </Body>
                  ))}
                </Card>
              ) : null}

              {plan.weeks.map((week) => (
                <Card key={week.id}>
                  <Text style={{ fontWeight: "700", fontSize: 16 }}>
                    Week {week.order}: {week.title} <Text style={{ fontWeight: "400", color: colors.textMuted }}>· about {week.hours} hours</Text>
                  </Text>
                  {week.goal ? <Muted style={{ marginTop: 4 }}>{week.goal}</Muted> : null}
                  {week.lessons.map((lesson) => (
                    <LessonCard
                      key={lesson.id}
                      lesson={lesson}
                      plan={plan}
                      busy={act.busy}
                      onTick={() => run(() => prepApi.tickLesson(lesson.id))}
                      onRemoveLesson={() => run(() => prepApi.removeLesson(lesson.id))}
                      onRemoveQuestion={(qid) => run(() => prepApi.removeQuestion(qid))}
                    />
                  ))}
                  {week.milestones.length > 0 ? (
                    <>
                      <SectionTitle>This week&apos;s tasks</SectionTitle>
                      {week.milestones.map((m) =>
                        started ? (
                          <TickRow key={m.id} label={`${m.kind_label}: ${m.text}`} checked={m.done} disabled={act.busy} onPress={() => run(() => prepApi.tickMilestone(m.id))} />
                        ) : (
                          <Body key={m.id} style={{ marginBottom: 6 }}>
                            {m.kind_label}: {m.text}
                          </Body>
                        ),
                      )}
                    </>
                  ) : null}
                </Card>
              ))}

              {started ? <Button label="Delete this plan" variant="danger" onPress={discard} /> : null}
              <Muted style={{ marginTop: 12 }}>Written by {plan.generator || "your AI account"}. AI can be wrong, so treat the sources as the truth and the questions as practice.</Muted>
            </>
          ) : null}
        </>
      )}
    </Screen>
  );
}
