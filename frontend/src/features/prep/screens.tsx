"use client";

import { CameUpTally, CameUpTick } from "@/features/pipeline/came-up";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, buttonClass, Card, ErrorBox, Loading, Notice, PageHeader, Progress, SourceLinks } from "@/components/ui";
import { errorText } from "@/lib/api";
import { Link, navigate } from "@/lib/router";
import { notify } from "@/lib/toast";
import { cn } from "@/lib/utils";
import { prepApi, type Lesson, type Plan, type Question } from "./api";

const LIST = ["prep", "plans"] as const;

export function PrepList() {
  const query = useQuery({ queryKey: LIST, queryFn: prepApi.list });
  if (query.isPending) return <Loading what="your prep plans" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load your prep plans.")} onRetry={() => query.refetch()} />;
  const plans = query.data.plans;
  return (
    <>
      <PageHeader title="Prep plans" />
      <p className="mb-4 text-sm text-muted">
        A prep plan is a short study plan that closes the gaps a job showed: a few weeks of lessons with links to the official documentation, and quiz questions that cite their source. It is
        written from your CV and the job by your own AI account, and nothing starts until you have read it and said yes.
      </p>
      {plans.length === 0 ? (
        <Card className="py-10 text-center">
          <h2 className="font-semibold">No prep plans yet</h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted">Check how well a job fits you on your dashboard. If it shows skills you are missing, press Prepare on its card.</p>
          <Link to="/" className={cn(buttonClass("primary"), "mt-4")}>
            Go to my dashboard
          </Link>
        </Card>
      ) : (
        <ul className="space-y-3">
          {plans.map((plan) => (
            <li key={plan.id}>
              <Card className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="font-semibold">
                    <Link to={`/prep/${plan.id}`} className="hover:underline">
                      {plan.title || "Prep plan"}
                    </Link>
                  </h2>
                  <p className="text-sm text-muted">
                    {plan.job ? `For ${plan.job.role} at ${plan.job.company} · ` : ""}
                    {plan.status_label}
                    {plan.lessons_total ? ` · ${plan.lessons_done} of ${plan.lessons_total} lessons done` : ""}
                  </p>
                </div>
                <Link to={`/prep/${plan.id}`} className={buttonClass("outline")}>
                  {plan.status === "draft" ? "Review the draft" : "Open"}
                </Link>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function QuestionReview({ question, onRemove, busy }: { question: Question; onRemove: () => void; busy: boolean }) {
  return (
    <div className="mt-2 border-t border-border pt-2 text-sm">
      <div className="flex justify-between gap-2">
        <p>
          <strong>{question.prompt}</strong> <span className="text-muted">({question.kind_label.toLowerCase()})</span>
        </p>
        <Button variant="danger" small onClick={onRemove} disabled={busy}>
          Remove
        </Button>
      </div>
      <ol className="ml-5 list-[upper-alpha]">
        {question.choices.map((choice, i) => (
          <li key={i}>
            {choice} {question.correct.includes(i) && <Badge tone="good">correct</Badge>}
          </li>
        ))}
      </ol>
      <p className="text-muted">{question.explanation}</p>
      <p>
        <SourceLinks sources={question.sources} />
      </p>
    </div>
  );
}

function LessonCard({ lesson, plan, busy, onTick, onRemoveLesson, onRemoveQuestion }: { lesson: Lesson; plan: Plan; busy: boolean; onTick: () => void; onRemoveLesson: () => void; onRemoveQuestion: (id: number) => void }) {
  const started = plan.status === "active" || plan.status === "done";
  return (
    <div className="mb-2 rounded-lg border border-border p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          {started && (
            <Button variant={lesson.done ? "primary" : "outline"} small className="mr-2" aria-pressed={lesson.done} onClick={onTick} disabled={busy}>
              {lesson.done ? "Done" : "Mark done"}
            </Button>
          )}
          <strong>{lesson.title}</strong> {lesson.gap && <Badge tone="brand">{lesson.gap}</Badge>}
          {lesson.topics.length > 0 && <p className="text-sm text-muted">{lesson.topics.join(" · ")}</p>}
        </div>
        {plan.status === "draft" && (
          <Button variant="danger" small onClick={onRemoveLesson} disabled={busy}>
            Remove lesson
          </Button>
        )}
      </div>
      <p className="mt-2 text-sm">
        <span className="text-muted">Read: </span>
        <SourceLinks sources={lesson.sources} />
      </p>
      {plan.status === "draft" && lesson.questions && lesson.questions.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-sm">Quiz questions ({lesson.questions.length})</summary>
          {lesson.questions.map((q) => (
            <QuestionReview key={q.id} question={q} busy={busy} onRemove={() => onRemoveQuestion(q.id)} />
          ))}
        </details>
      )}
    </div>
  );
}

export function PrepPlan({ id }: { id: number }) {
  const client = useQueryClient();
  const key = ["prep", "plan", id] as const;
  const query = useQuery({
    queryKey: key,
    queryFn: () => prepApi.plan(id),
    refetchInterval: (q) => (q.state.data?.status === "generating" ? 6000 : false), // the page updates itself while the plan is being written
  });
  const [message, setMessage] = useState("");
  const refresh = () => {
    client.invalidateQueries({ queryKey: key });
    client.invalidateQueries({ queryKey: LIST });
  };
  const act = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: refresh,
    onError: (e) => setMessage(errorText(e)),
  });
  const run = (fn: () => Promise<unknown>) => {
    setMessage("");
    act.mutate(fn);
  };

  if (query.isPending) return <Loading what="the plan" />;
  if (query.isError) return <ErrorBox message="We could not find that plan." />;
  const plan = query.data;
  const started = plan.status === "active" || plan.status === "done";
  // The new plan is made first and the failed one is only discarded after, so a refused request leaves the old plan (and its reason) on screen.
  const tryAgain = async (jobId: number) => {
    const made = await prepApi.create(jobId);
    if (made.id !== id) {
      try {
        await prepApi.discard(id);
      } catch {
        /* the old plan staying in the list is harmless; the new one is what matters */
      }
    }
    client.invalidateQueries({ queryKey: LIST });
    navigate(`/prep/${made.id}`);
  };
  const discard = () => {
    if (started && !window.confirm("Delete this plan and your progress?")) return;
    act.mutate(() => prepApi.discard(id), {
      onSuccess: () => {
        notify("Prep plan discarded.");
        navigate("/prep");
      },
    });
  };

  return (
    <>
      <PageHeader title={plan.title || "Prep plan"} subtitle={plan.job ? `For ${plan.job.role} at ${plan.job.company}` : undefined} />
      {message && <div className="mb-3"><Notice tone="error">{message}</Notice></div>}

      {plan.status === "generating" && (
        <Card>
          <h2 className="font-semibold">Writing your plan…</h2>
          <p className="my-2 text-sm">{plan.progress || "Starting"}. This takes a few minutes and uses your own AI account. This page updates by itself, and you can leave it and come back.</p>
          <div className="h-2 animate-pulse rounded-full bg-brand/40" />
        </Card>
      )}

      {plan.status === "failed" && (
        <Card className="border-bad">
          <h2 className="font-semibold">This plan could not be written</h2>
          <p className="my-2 text-sm">{plan.error || "Something went wrong."}</p>
          <div className="flex gap-2">
            {plan.job && (
              <Button onClick={() => run(() => tryAgain(plan.job!.id))}>Try again</Button>
            )}
            <Button variant="outline" onClick={discard}>Discard</Button>
          </div>
        </Card>
      )}

      {(plan.status === "draft" || started) && (
        <div className="space-y-3">
          {plan.summary && <p className="text-lg">{plan.summary}</p>}
          {plan.status === "draft" ? (
            <>
              <Notice>
                <strong>This is a draft.</strong> Read it over, take out anything you do not want, then press Start this plan. The AI wrote it from your CV and the job, and every lesson and question cites an
                official source. Quizzes are only as good as the source behind them, so open a link if an answer surprises you.
                {plan.unchecked_links > 0 && ` ${plan.unchecked_links} question${plan.unchecked_links === 1 ? "" : "s"} cite a link we could not open from here. They are marked below; the site may just block automatic visits.`}
              </Notice>
              <div className="flex gap-2">
                <Button onClick={() => run(async () => { await prepApi.start(id); notify("Your prep plan has started. Tick lessons off as you finish them."); })} disabled={act.isPending}>Start this plan</Button>
                <Button variant="outline" onClick={discard}>Discard</Button>
              </div>
            </>
          ) : (
            <Card>
              <div className="mb-1 flex justify-between">
                <strong>{plan.lessons_done} of {plan.lessons_total} lessons done</strong>
                <span className="text-sm text-muted">{plan.hours_per_week} hours a week{plan.status === "done" ? " · finished" : ""}</span>
              </div>
              <Progress value={plan.percent} label="Lessons done" />
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm text-muted">
                  {plan.question_count} quiz question{plan.question_count === 1 ? "" : "s"}
                  {plan.streak ? ` · ${plan.streak} day${plan.streak === 1 ? "" : "s"} in a row` : ""}. Lessons you tick off count as studied for this job the next time you check your fit.
                </p>
                {plan.question_count > 0 && (
                  <Link to={`/prep/${id}/today`} className={buttonClass(plan.done_today ? "outline" : "primary")}>
                    {plan.done_today ? "See today's answers" : "Today's practice"}
                  </Link>
                )}
              </div>
              {plan.weak_topics.length > 0 && (
                <p className="mt-3 text-sm">
                  Worth another look: <strong>{plan.weak_topics.map((t) => t.title).join(", ")}</strong>. You missed different questions on {plan.weak_topics.length === 1 ? "it" : "them"} recently, so they will come up again until you have
                  answered well on three separate days.
                </p>
              )}
            </Card>
          )}

          {plan.gap_skills.length > 0 && (
            <Card>
              <h2 className="mb-1 font-semibold">What this plan closes</h2>
              <ul className="list-disc pl-5 text-sm">
                {plan.gap_skills.map((g) => (
                  <li key={g.skill}>
                    <strong>{g.skill}</strong>: {g.why} <span className="text-muted">(your CV: {g.cv_evidence})</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {plan.weeks.map((week) => (
            <Card key={week.id}>
              <h2 className="font-semibold">
                Week {week.order}: {week.title} <span className="font-normal text-muted">· about {week.hours} hours</span>
              </h2>
              {week.goal && <p className="mb-2 text-sm text-muted">{week.goal}</p>}
              {week.lessons.map((lesson) => (
                <LessonCard
                  key={lesson.id}
                  lesson={lesson}
                  plan={plan}
                  busy={act.isPending}
                  onTick={() => run(() => prepApi.tickLesson(lesson.id))}
                  onRemoveLesson={() => run(() => prepApi.removeLesson(lesson.id))}
                  onRemoveQuestion={(qid) => run(() => prepApi.removeQuestion(qid))}
                />
              ))}
              {week.milestones.length > 0 && (
                <>
                  <h3 className="mt-3 text-sm font-semibold">This week&apos;s tasks</h3>
                  <ul className="mt-1 space-y-1 text-sm">
                    {week.milestones.map((m) => (
                      <li key={m.id}>
                        {started && (
                          <Button variant={m.done ? "primary" : "outline"} small className="mr-2" aria-pressed={m.done} onClick={() => run(() => prepApi.tickMilestone(m.id))} disabled={act.isPending}>
                            {m.done ? "Done" : "Mark done"}
                          </Button>
                        )}
                        <Badge className="mr-1">{m.kind_label}</Badge>
                        {m.text}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </Card>
          ))}

          {started && (
            <Button variant="danger" small onClick={discard}>
              Delete this plan
            </Button>
          )}
          <p className="text-xs text-muted">Written by {plan.generator || "your AI account"}. AI can be wrong, so treat the sources as the truth and the questions as practice.</p>
        </div>
      )}
    </>
  );
}

export function PrepToday({ id }: { id: number }) {
  const client = useQueryClient();
  const key = ["prep", "today", id] as const;
  const query = useQuery({ queryKey: key, queryFn: () => prepApi.today(id) });
  const [picked, setPicked] = useState<Record<number, number[]>>({});
  const [message, setMessage] = useState("");
  const send = useMutation({
    mutationFn: () => prepApi.answer(id, Object.fromEntries(Object.entries(picked).map(([k, v]) => [k, v]))),
    onSuccess: () => {
      setMessage("");
      client.invalidateQueries({ queryKey: key });
      client.invalidateQueries({ queryKey: ["prep", "plan", id] });
    },
    onError: (e) => setMessage(errorText(e)),
  });

  if (query.isPending) return <Loading what="today's practice" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "Start the plan first, then come back for today's practice.")} />;
  const data = query.data;
  const choose = (qid: number, kind: string, index: number) =>
    setPicked((p) => {
      const current = p[qid] ?? [];
      if (kind === "multi") return { ...p, [qid]: current.includes(index) ? current.filter((i) => i !== index) : [...current, index] };
      return { ...p, [qid]: [index] };
    });
  const unanswered = data.rows.filter((r) => (picked[r.id] ?? []).length === 0).length;

  return (
    <>
      <PageHeader
        title="Today's practice"
        subtitle={
          <>
            <Link to={`/prep/${id}`} className="underline">{data.plan.title}</Link>
            {data.streak ? ` · ${data.streak} day${data.streak === 1 ? "" : "s"} in a row` : ""}
          </>
        }
      />
      {data.finished ? (
        <Card className="mb-3">
          <h2 className="font-semibold">{data.right} of {data.total} right</h2>
          <p className="mt-1 text-sm">
            {data.right === data.total ? "All of them. Nicely done." : data.right === 0 ? "None this time, which is useful to know. Read the explanations below; the questions you missed will come back." : "Read the explanations below, especially for the ones you missed. They will come back until they stick."}
          </p>
          <p className="text-sm text-muted">Come back tomorrow for the next set.{data.streak ? ` That keeps your ${data.streak}-day run going.` : ""}</p>
        </Card>
      ) : (
        <p className="mb-3 text-sm text-muted">{data.total} question{data.total === 1 ? "" : "s"}, about five minutes. Answer them all, then send. Nothing here is graded by anyone but you.</p>
      )}
      {!data.finished && data.weak_topics.length > 0 && (
        <div className="mb-3"><Notice>Worth another look: <strong>{data.weak_topics.map((t) => t.title).join(", ")}</strong>. {data.rows[0]?.review && "The first question is from there."}</Notice></div>
      )}
      {message && <div className="mb-3"><Notice tone="error">{message}</Notice></div>}

      {data.finished && <CameUpTally planId={data.plan.id} />}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send.mutate();
        }}
        className="space-y-3"
      >
        {data.rows.map((row, n) => (
          <Card key={row.id} className={cn(data.finished && (row.right ? "border-good" : "border-bad"))}>
            <fieldset>
              <legend className="mb-1 text-xs text-muted">
                Question {n + 1} · {row.topic}
                {row.review ? " · another look" : ""}
              </legend>
              <p className="mb-2 text-lg font-semibold">{row.prompt}</p>
              {!data.finished && row.kind === "multi" && <p className="mb-2 text-sm text-muted">Pick every answer that applies.</p>}
              {row.choices.map((choice, i) =>
                data.finished ? (
                  <p key={i} className="mb-1 text-sm">
                    {row.correct?.includes(i) && <Badge tone="good" className="mr-1">right answer</Badge>}
                    {row.chosen?.includes(i) && <Badge tone="brand" className="mr-1">your pick</Badge>}
                    {choice}
                  </p>
                ) : (
                  <label key={i} className="mb-1 flex items-start gap-2 text-sm">
                    <input
                      type={row.kind === "multi" ? "checkbox" : "radio"}
                      name={`q${row.id}`}
                      checked={(picked[row.id] ?? []).includes(i)}
                      onChange={() => choose(row.id, row.kind, i)}
                      className="mt-1"
                    />
                    <span>{choice}</span>
                  </label>
                ),
              )}
              {data.finished && (
                <>
                  <p className="mt-3 text-sm">{row.explanation}</p>
                  <p className="text-sm">
                    Read more: <SourceLinks sources={row.sources ?? []} />
                  </p>
                  <CameUpTick planId={data.plan.id} questionId={row.id} />
                </>
              )}
            </fieldset>
          </Card>
        ))}
        {!data.finished && (
          <Button type="submit" disabled={send.isPending || unanswered > 0}>
            {unanswered > 0 ? `Answer ${unanswered} more to send` : "Send my answers"}
          </Button>
        )}
      </form>
      <p className="mt-4 text-sm"><Link to={`/prep/${id}`} className="underline">← Back to the plan</Link></p>
    </>
  );
}
