"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { CheckField, FormError, SelectField, TextField, useSubmit } from "@/components/form";
import { Badge, Button, buttonClass, Card, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { coverApi, cvApi } from "@/features/cv/api";
import { letterSaid, tailoredSaid, type Said } from "@/features/cv/messages";
import { errorText } from "@/lib/api";
import { Link, navigate } from "@/lib/router";
import { notify } from "@/lib/toast";
import { ApplicationAnswers } from "@/features/assist/answers";
import { InterviewPrepSection } from "@/features/assist/interview-prep";
import { MessageDraftCard } from "@/features/assist/message-draft";
import { FitList } from "./edit-job";
import { jobsApi, type ApplyData } from "./api";
import { appliedMessage } from "./logic";
import { ReplyPaste } from "./reply-paste";
import MatchCard from "./match-card";
import { COVER_TONES } from "./match-logic";
import { usePreferences } from "@/lib/use-preferences";
import { JobMail } from "@/features/google/mail";
import { SendFromGmail } from "@/features/google/send";

/** Makes a new CV version or letter for this job, then opens it so the person can review it. */
function MakeButton({ label, busyLabel, make }: { label: string; busyLabel: string; make: () => Promise<{ path: string; said: Said }> }) {
  const [state, setState] = useState<"idle" | "busy" | string>("idle");
  return (
    <>
      <Button
        variant="outline"
        disabled={state === "busy"}
        onClick={async () => {
          setState("busy");
          try {
            const made = await make();
            notify(made.said.text, made.said.tone);
            navigate(made.path);
          } catch (e) {
            setState(errorText(e));
          }
        }}
      >
        {state === "busy" ? busyLabel : label}
      </Button>
      {state !== "idle" && state !== "busy" && <span role="alert" className="text-sm text-bad">{state}</span>}
    </>
  );
}

function RecordForm({ id, data }: { id: number; data: ApplyData }) {
  const client = useQueryClient();
  const { prefs, update } = usePreferences();
  const form = useSubmit();
  const [cv, setCv] = useState<string>(data.selected !== null ? String(data.selected) : "none");
  const [channel, setChannel] = useState(data.job.channel);
  const [appliedOn, setAppliedOn] = useState(data.job.applied_date);
  const [note, setNote] = useState(data.job.note);
  const [days, setDays] = useState(String(data.followup_days));
  const [confirmClosed, setConfirmClosed] = useState(false);

  return (
    <form
      onSubmit={form.handle(async () => {
        const done = await jobsApi.record(id, {
          cv: cv === "none" ? null : Number(cv),
          channel,
          note,
          days: days.trim() ? Number(days) : null,
          applied_on: appliedOn || null,
          confirm_closed: confirmClosed,
        });
        await client.invalidateQueries({ queryKey: ["dashboard"] });
        notify(appliedMessage(done.follow_up_date));
        navigate("/");
      })}
    >
      <h2 className="mb-2 mt-6 text-lg font-semibold">2. Choose the CV you will send</h2>
      <Card className="mb-3">
        {data.versions.length > 0 ? (
          <div role="radiogroup" aria-label="CV to send">
            {data.versions.map((v) => (
              <div key={v.id} className="border-b border-border py-2 last:border-0">
                <label className="flex items-start gap-2 font-medium">
                  <input type="radio" name="cv" value={v.id} checked={cv === String(v.id)} onChange={() => setCv(String(v.id))} className="mt-1" />
                  <span>
                    {v.label} <Badge>v{v.id}</Badge>
                    <span className="block text-sm font-normal text-muted">
                      {v.kind_label} · {v.created}
                      {v.flagged ? " · you approved the flagged claims" : ""}
                    </span>
                  </span>
                </label>
                <div className="ml-6 mt-1 flex flex-wrap gap-2">
                  <a className={buttonClass("outline", true)} href={v.docx_url}>
                    Word file
                  </a>
                  <a className={buttonClass("outline", true)} href={v.print_url} target="_blank" rel="noopener noreferrer">
                    Print or save as PDF
                  </a>
                  <Link className={buttonClass("outline", true)} to={`/cv/${v.id}`}>
                    Open
                  </Link>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted">
            No CV is ready to send yet. Add your CV in <Link to="/profile" className="text-brand underline">Profile</Link>.
          </p>
        )}
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input type="radio" name="cv" value="none" checked={cv === "none"} onChange={() => setCv("none")} />I am sending a different CV (do not link a version)
        </label>
        {data.has_flagged && <p className="mt-2 text-sm text-muted">Your tailored CV still has claims we could not match to your own material, so it is not offered. Review it first.</p>}
      </Card>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <MakeButton label="Tailor a CV for this job" busyLabel="Tailoring…" make={() => cvApi.tailor(id).then((r) => ({ path: `/cv/${r.id}`, said: tailoredSaid(r) }))} />
        <span className="text-sm text-muted">Makes a new version from your own CV. You review it before it can be sent.</span>
      </div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <label className="text-sm">
          <span className="mr-1">Tone</span>
          <select
            aria-label="Tone of the cover letter"
            value={prefs.cover_tone}
            onChange={(e) => update({ cover_tone: e.target.value as (typeof COVER_TONES)[number]["value"] })}
            className="rounded-lg border border-border bg-surface px-2 py-1 text-sm"
          >
            {COVER_TONES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
        <MakeButton label="Write a cover letter" busyLabel="Writing…" make={() => coverApi.write(id, prefs.cover_tone).then((r) => ({ path: `/cover/${r.id}`, said: letterSaid(r) }))} />
        <span className="text-sm text-muted">Short, from your own material, checked before you can use it.</span>
        {data.cover_letters.map((l) => (
          <Link key={l.id} to={`/cover/${l.id}`} className="text-sm text-brand underline">
            Letter of {l.created}
            {l.needs_review ? " (needs review)" : ""}
          </Link>
        ))}
      </div>

      <h2 className="mb-2 mt-6 text-lg font-semibold">3. Apply on the employer&apos;s site</h2>
      <Card className="mb-3">
        {data.job.url ? (
          <a className={buttonClass("primary")} href={data.job.url} target="_blank" rel="noopener noreferrer">
            Open the job posting
          </a>
        ) : (
          <p className="text-sm text-muted">This job has no link saved. Apply through whatever place you found it on.</p>
        )}
        <details className="mt-3">
          <summary className="cursor-pointer text-sm">Applying by email? Start from this draft</summary>
          <div className="mt-3">
            <TextField label="Subject" value={data.draft.subject} readOnly onClick={(e) => e.currentTarget.select()} />
            <label className="mb-1 block text-sm font-medium" htmlFor="draft-body">
              Message
            </label>
            <textarea id="draft-body" rows={10} value={data.draft.body} readOnly onClick={(e) => e.currentTarget.select()} className="w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm" />
            <p className="mt-1 text-xs text-muted">A starting point only. Replace [Your name], attach the CV, and check every statement is true. It is never sent for you.</p>
          </div>
        </details>
      </Card>
      <SendFromGmail
        jobId={id}
        available={data.google.available}
        connected={data.google.connected}
        suggestedTo={data.google.suggested_to}
        draft={data.draft}
        cv={cv === "none" ? null : Number(cv)}
        cover={data.cover_letters.find((l) => !l.needs_review)?.id ?? null}
      />

      <h2 className="mb-2 mt-6 text-lg font-semibold">4. Record what you sent</h2>
      <Card>
        {data.job.closed && <CheckField label="This posting looks closed, but I applied anyway" checked={confirmClosed} onChange={(e) => setConfirmClosed(e.target.checked)} />}
        <SelectField label="How did you apply?" value={channel} onChange={(e) => setChannel(e.target.value)} errors={form.fields.channel} className="max-w-sm">
          <option value="">Not recorded</option>
          {data.channels.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </SelectField>
        <TextField label="Date applied (blank means today)" type="date" value={appliedOn} onChange={(e) => setAppliedOn(e.target.value)} className="max-w-56" />
        <TextField label="Note (optional)" value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} placeholder="Contact name, reference number, anything you want to remember" />
        <TextField
          label="Remind me to follow up in (days)"
          type="number"
          min={1}
          max={data.max_followup_days}
          value={days}
          onChange={(e) => setDays(e.target.value)}
          className="max-w-32"
        />
        <FormError message={form.error} />
        <Button type="submit" disabled={form.busy} className="mt-2">
          {form.busy ? "Saving…" : "I submitted it: record it"}
        </Button>
        <p className="mt-2 text-xs text-muted">Recording sets the status to Applied, saves which CV you sent and a copy of the job description as it is today, and sets the reminder.</p>
      </Card>
    </form>
  );
}

export function ApplyAssistant({ id }: { id: number }) {
  const query = useQuery({ queryKey: ["apply", id], queryFn: () => jobsApi.apply(id), staleTime: 0, gcTime: 0 });
  if (query.isPending) return <Loading what="the apply page" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load this job.")} onRetry={() => query.refetch()} />;
  const data = query.data;
  return (
    <>
      <PageHeader
        title={`Apply: ${data.job.company}`}
        subtitle={data.job.role}
        actions={
          <Link to="/" className={buttonClass("ghost")}>
            ← Dashboard
          </Link>
        }
      />
      <p className="mb-4 text-sm text-muted">StillOpen does not apply for you. Check the list, choose the CV, apply on the employer&apos;s site, then record it here so you always know what you sent.</p>
      {data.job.applied && (
        <p className="mb-3 text-sm">
          <Badge tone="good">Applied</Badge> {data.job.applied_date && `on ${data.job.applied_date}`}
          {data.job.follow_up_date && ` · follow up on ${data.job.follow_up_date}`}
        </p>
      )}
      <h2 className="mb-2 text-lg font-semibold">1. Before you apply</h2>
      <Card>
        <FitList checks={data.checks} empty="Nothing to check yet." />
      </Card>
      <Card className="mt-3">
        <MatchCard jobId={id} />
      </Card>
      <RecordForm id={id} data={data} />
      <JobMail jobId={id} connected={data.google.connected} thread={data.google.thread} />
      <ReplyPaste jobId={id} />
      <ApplicationAnswers jobId={id} />
      <InterviewPrepSection jobId={id} />
      <MessageDraftCard jobId={id} />
    </>
  );
}
