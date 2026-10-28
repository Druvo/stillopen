"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { TextAreaField } from "@/components/form";
import { Badge, Button, Card } from "@/components/ui";
import { errorText } from "@/lib/api";
import { CameUpTally, CameUpTick, SaveToBank } from "@/features/pipeline/came-up";
import { assistApi, type Feedback, type PrepQuestion } from "./api";
import { canAsk, prepText, questionText, starMissing } from "./logic";
import { AiNotice, CopyButton, NoKeyLine, ProblemLine } from "./ui";

function FeedbackView({ feedback }: { feedback: Feedback }) {
  const missing = starMissing(feedback.star);
  const list = (title: string, items: string[]) =>
    items.length > 0 && (
      <div className="mt-2">
        <strong className="text-sm">{title}</strong>
        <ul className="list-disc pl-5 text-sm">
          {items.map((t, i) => (
            <li key={i}>{t}</li>
          ))}
        </ul>
      </div>
    );
  return (
    <div className="mt-3 rounded-lg border border-border bg-surface-2 p-3" data-testid="answer-feedback">
      {feedback.summary && <p className="text-sm">{feedback.summary}</p>}
      {list("What works", feedback.works)}
      {list("What is vague", feedback.vague)}
      {list("What to add", feedback.add)}
      <p className="mt-2 text-sm">
        <strong>Structure: </strong>
        {missing.length === 0 ? "your answer covers the situation, your task, what you did and the result." : `not clear yet: ${missing.join(", ")}.`}
      </p>
      <p className="mt-1 text-sm">
        <strong>Length: </strong>
        {feedback.length.words} words. {feedback.length.note}
      </p>
      <AiNotice>{feedback.notice}</AiNotice>
    </div>
  );
}

function Practise({ jobId, question }: { jobId: number; question: string }) {
  const [answer, setAnswer] = useState("");
  const ask = useMutation({ mutationFn: () => assistApi.feedback(jobId, question, answer) });
  return (
    <details className="mt-2">
      <summary className="cursor-pointer text-sm text-brand">Practise this answer</summary>
      <div className="mt-2">
        <TextAreaField
          label="Your answer, written the way you would say it"
          hint="Nothing you type here is saved. You get feedback, not a grade."
          rows={5}
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          maxLength={3000}
        />
        <Button variant="outline" small disabled={ask.isPending || !canAsk(answer, 5)} onClick={() => ask.mutate()}>
          {ask.isPending ? "Reading your answer…" : "Get feedback"}
        </Button>
        <ProblemLine message={ask.isError ? errorText(ask.error) : ""} />
        {ask.data && <FeedbackView feedback={ask.data.feedback} />}
      </div>
    </details>
  );
}

function QuestionCard({ jobId, q, canPractise }: { jobId: number; q: PrepQuestion; canPractise: boolean }) {
  return (
    <li className="rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="font-medium">{q.question}</p>
        <CopyButton text={questionText(q)} />
      </div>
      <p className="mt-1 text-sm text-muted">What they are really testing: {q.testing}</p>
      {q.outline.length > 0 ? (
        <div className="mt-2">
          <p className="text-xs font-medium text-muted">Outline to rewrite in your own words (from your own material)</p>
          <ul className="list-disc pl-5 text-sm">
            {q.outline.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="mt-2 text-sm text-muted">Nothing in your material fits this one yet. Think of your own example, and be honest if it is something you are still learning.</p>
      )}
      {q.flags.length > 0 && (
        <p className="mt-1 text-xs text-warn">The job mentions {q.flags.join(", ")}, which your material does not. Only say it if it is true.</p>
      )}
      <CameUpTick jobId={jobId} qkey={q.id} />
      <div className="mt-2">
        <SaveToBank question={q.question} jobId={jobId} />
      </div>
      {canPractise && <Practise jobId={jobId} question={q.question} />}
    </li>
  );
}

/** Likely interview questions for one job, with outlines from the person's own material and a place to practise an answer. */
export function InterviewPrepSection({ jobId }: { jobId: number }) {
  const client = useQueryClient();
  const key = ["assist", "prep", jobId] as const;
  const query = useQuery({ queryKey: key, queryFn: () => assistApi.getPrep(jobId) });
  const make = useMutation({
    mutationFn: () => assistApi.makePrep(jobId),
    onSuccess: (data) => client.setQueryData(key, data),
  });
  const prep = make.data?.prep ?? query.data?.prep ?? null;
  const ai = query.data?.ai ?? false;
  return (
    <section id="prepare" aria-labelledby="prepare-heading">
      <h2 id="prepare-heading" className="mb-2 mt-6 text-lg font-semibold">
        Prepare for interviews
      </h2>
      <Card>
        <p className="mb-3 text-sm text-muted">
          Eight questions this job is likely to bring up, from the posting and your own material. Nothing here is sent or saved as your words.
        </p>
        {query.isPending && <p className="text-sm text-muted">Loading…</p>}
        {query.isError && <ProblemLine message={errorText(query.error, "We could not load this.")} />}
        {query.isSuccess && !ai && <NoKeyLine />}
        {query.isSuccess && ai && (
          <Button variant={prep ? "outline" : "primary"} disabled={make.isPending} onClick={() => make.mutate()}>
            {make.isPending ? "Writing your questions…" : prep ? "Write them again" : "Write my interview questions"}
          </Button>
        )}
        <ProblemLine message={make.isError ? errorText(make.error) : ""} />
        {prep && (
          <div className="mt-4">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <CopyButton text={prepText(prep)} label="Copy all questions" small={false} />
              <Badge>Made {prep.generated_at.slice(0, 10)}</Badge>
            </div>
            <CameUpTally jobId={jobId} />
            {prep.groups
              .filter((g) => g.questions.length > 0)
              .map((g) => (
                <div key={g.key} className="mb-4">
                  <h3 className="mb-2 font-semibold">{g.title}</h3>
                  <ul className="space-y-3">
                    {g.questions.map((q) => (
                      <QuestionCard key={q.id} jobId={jobId} q={q} canPractise={ai} />
                    ))}
                  </ul>
                </div>
              ))}
            {prep.dropped_points > 0 && (
              <p className="text-xs text-muted">
                We left out {prep.dropped_points} outline point{prep.dropped_points === 1 ? "" : "s"} that mentioned things your own material does not show.
              </p>
            )}
            <AiNotice>{prep.notice}</AiNotice>
          </div>
        )}
      </Card>
    </section>
  );
}
