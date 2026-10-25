"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { SelectField, TextAreaField, TextField } from "@/components/form";
import { Button } from "@/components/ui";
import { useAssistStatus } from "@/features/assist/api";
import { extrasApi } from "@/features/assist/extras-api";
import { findingsText, messageText } from "@/features/assist/logic";
import { AiNotice, CopyButton, ProblemLine } from "@/features/assist/ui";
import { errorText } from "@/lib/api";
import type { Contact, JobChoice } from "./api";


/** The job to open the draft with: the job of the contact's newest referral if it has one, else the first job in the list. */
export function defaultReferralJob(contact: Pick<Contact, "referrals">, jobs: JobChoice[]): string {
  const ids = new Set(jobs.map((j) => j.id));
  const fromReferral = contact.referrals.find((r) => ids.has(r.job.id));
  const id = fromReferral ? fromReferral.job.id : jobs[0]?.id;
  return id === undefined ? "" : String(id);
}

/** "Draft a referral request" on a contact: a short polite message (free template, or polished by the person's own AI). Never sent. */
export function ReferralDraft({ contact, jobs }: { contact: Contact; jobs: JobChoice[] }) {
  const status = useAssistStatus();
  const [open, setOpen] = useState(false);
  const [job, setJob] = useState(() => defaultReferralJob(contact, jobs));
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const write = useMutation({
    mutationFn: (polish: boolean) => extrasApi.referralDraft(contact.id, Number(job), polish),
    onSuccess: (data) => {
      setSubject(data.subject);
      setBody(data.body);
    },
  });
  if (jobs.length === 0) return null;
  if (!open) {
    return (
      <Button variant="outline" small onClick={() => setOpen(true)} aria-label={`Draft a referral request to ${contact.name}`}>
        Draft a referral request
      </Button>
    );
  }
  const ai = status.data?.ai ?? false;
  return (
    <div className="mt-3 w-full border-t border-border pt-3" data-testid="referral-draft">
      <h4 className="mb-2 font-medium">Referral request to {contact.name}</h4>
      <SelectField label="For which job" value={job} onChange={(e) => setJob(e.target.value)} className="max-w-sm">
        {jobs.map((j) => (
          <option key={j.id} value={j.id}>
            {j.label}
          </option>
        ))}
      </SelectField>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" disabled={write.isPending || !job} onClick={() => write.mutate(false)}>
          {write.isPending && !write.variables ? "Writing…" : "Write a draft (free)"}
        </Button>
        {ai && (
          <Button variant="outline" disabled={write.isPending || !job} onClick={() => write.mutate(true)}>
            {write.isPending && write.variables ? "Polishing…" : "Polish it with AI"}
          </Button>
        )}
        <Button variant="ghost" onClick={() => setOpen(false)}>
          Close
        </Button>
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
          <p className="mt-2 text-xs text-muted">Replace [Your name] if it is showing. It is never sent for you: paste it into your own email or message.</p>
          {write.data.method === "ai" && <AiNotice>{write.data.notice}</AiNotice>}
        </div>
      )}
    </div>
  );
}
