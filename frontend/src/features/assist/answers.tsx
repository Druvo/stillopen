"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { TextAreaField, TextField } from "@/components/form";
import { Button, Card } from "@/components/ui";
import { errorText } from "@/lib/api";
import { assistApi, useAssistStatus } from "./api";
import { findingsText } from "./logic";
import { AiNotice, CopyButton, NoKeyLine, ProblemLine } from "./ui";

/** A draft answer to a question on an application form, from the person's own material. It is only ever copied: never sent. */
export function ApplicationAnswers({ jobId }: { jobId: number }) {
  const status = useAssistStatus();
  const [question, setQuestion] = useState("");
  const [text, setText] = useState("");
  const draft = useMutation({
    mutationFn: () => assistApi.answer(jobId, question),
    onSuccess: (data) => setText(data.answer),
  });
  return (
    <section aria-labelledby="answers-heading">
      <h2 id="answers-heading" className="mb-2 mt-6 text-lg font-semibold">
        Answer an application question
      </h2>
      <Card>
        {status.isSuccess && !status.data.ai ? (
          <NoKeyLine />
        ) : (
          <>
            <TextField
              label="The question from the application form"
              hint="For example: Why do you want this role? Or: Describe a time you led a project."
              value={question}
              maxLength={500}
              onChange={(e) => setQuestion(e.target.value)}
            />
            <Button disabled={draft.isPending || question.trim().length < 5} onClick={() => draft.mutate()}>
              {draft.isPending ? "Writing a draft…" : "Draft an answer"}
            </Button>
            <ProblemLine message={draft.isError ? errorText(draft.error) : ""} />
            {draft.data && (
              <div className="mt-4">
                <TextAreaField label="Your draft (edit it freely)" rows={9} value={text} onChange={(e) => setText(e.target.value)} />
                <p className="text-xs text-muted">
                  {draft.data.words} words. Copy it into the application form yourself; nothing is sent for you.
                </p>
                {draft.data.flagged_count > 0 && (
                  <p role="status" className="mt-2 rounded-md border border-warn p-2 text-sm">
                    We could not match these to your own material: {findingsText(draft.data.flagged)}. Remove or change them unless they are true.
                  </p>
                )}
                <div className="mt-2">
                  <CopyButton text={text} label="Copy the answer" small={false} />
                </div>
                <AiNotice>{draft.data.notice}</AiNotice>
              </div>
            )}
          </>
        )}
      </Card>
    </section>
  );
}
