"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { SelectField, TextAreaField, TextField } from "@/components/form";
import { Button, Card } from "@/components/ui";
import { errorText } from "@/lib/api";
import { assistApi, useAssistStatus, type MessageKind } from "./api";
import { findingsText, messageText } from "./logic";
import { AiNotice, CopyButton, ProblemLine } from "./ui";

const KINDS: { value: MessageKind; label: string }[] = [
  { value: "follow_up", label: "Following up on my application" },
  { value: "thank_you", label: "Thank you after an interview" },
  { value: "withdraw", label: "Withdrawing my application" },
  { value: "accept", label: "Accepting an offer" },
  { value: "decline", label: "Declining an offer" },
];

/** A short email draft for a job: a free template, or the same polished by the person's own AI. It is only ever copied: never sent. */
export function MessageDraft({ jobId, interviewId = null, defaultKind = "follow_up", fixedKind = false }: { jobId: number; interviewId?: number | null; defaultKind?: MessageKind; fixedKind?: boolean }) {
  const status = useAssistStatus();
  const [kind, setKind] = useState<MessageKind>(defaultKind);
  const [note, setNote] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const write = useMutation({
    mutationFn: (polish: boolean) => assistApi.message(jobId, { kind, note, interview_id: interviewId, polish }),
    onSuccess: (data) => {
      setSubject(data.subject);
      setBody(data.body);
    },
  });
  const ai = status.data?.ai ?? false;
  return (
    <div data-testid="message-draft">
      {!fixedKind && (
        <SelectField label="What do you want to write?" value={kind} onChange={(e) => setKind(e.target.value as MessageKind)} className="max-w-sm">
          {KINDS.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </SelectField>
      )}
      <TextAreaField label="Anything you want it to mention (optional)" rows={2} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" disabled={write.isPending} onClick={() => write.mutate(false)}>
          {write.isPending && !write.variables ? "Writing…" : "Write a draft (free)"}
        </Button>
        {ai && (
          <Button variant="outline" disabled={write.isPending} onClick={() => write.mutate(true)}>
            {write.isPending && write.variables ? "Polishing…" : "Polish it with AI"}
          </Button>
        )}
      </div>
      <ProblemLine message={write.isError ? errorText(write.error) : ""} />
      {write.data && (
        <div className="mt-3">
          <TextField label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
          <TextAreaField label="Message" rows={9} value={body} onChange={(e) => setBody(e.target.value)} />
          {write.data.flagged_count > 0 && (
            <p role="status" className="mb-2 rounded-md border border-warn p-2 text-sm">
              The AI added things you did not give it: {findingsText(write.data.flagged)}. Remove them unless they are true.
            </p>
          )}
          <CopyButton text={messageText({ subject, body })} label="Copy the message" small={false} />
          <p className="mt-2 text-xs text-muted">Replace [Your name] if it is showing, and check every statement is true. It is never sent for you.</p>
          {write.data.method === "ai" && <AiNotice>{write.data.notice}</AiNotice>}
        </div>
      )}
    </div>
  );
}

/** The same drafts as a card, for the apply screen's follow-up area. */
export function MessageDraftCard({ jobId }: { jobId: number }) {
  return (
    <section aria-labelledby="message-heading">
      <h2 id="message-heading" className="mb-2 mt-6 text-lg font-semibold">
        Write a follow-up or reply
      </h2>
      <Card>
        <MessageDraft jobId={jobId} />
      </Card>
    </section>
  );
}
