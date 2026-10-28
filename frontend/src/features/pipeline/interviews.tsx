"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, buttonClass, Card, ErrorBox, Loading, Notice, PageHeader } from "@/components/ui";
import { FormError, SelectField, TextAreaField, TextField, useSubmit } from "@/components/form";
import { errorText } from "@/lib/api";
import { notify } from "@/lib/toast";
import { pipelineApi, type Interview, type InterviewList, type InterviewValues } from "./api";
import { InterviewPrepSection } from "@/features/assist/interview-prep";
import { MessageDraft } from "@/features/assist/message-draft";
import { CalendarLinkCard } from "./calendar-link";
import { jobFromSearch, whenLabel } from "./logic";
import { SuggestMove, type Suggestion } from "./suggest";

const KEY = ["pipeline", "interviews"] as const;

function InterviewForm({ data, item, defaultJob, onDone, onSuggest }: { data: InterviewList; item?: Interview; defaultJob: string; onDone: () => void; onSuggest: (s: Suggestion) => void }) {
  const client = useQueryClient();
  const form = useSubmit();
  const [v, setV] = useState<InterviewValues>({
    application: item ? String(item.job.id) : defaultJob,
    scheduled_at: item?.scheduled_local ?? "",
    kind: item?.kind ?? "video",
    where: item?.where ?? "",
    notes: item?.notes ?? "",
  });
  const set = (name: keyof InterviewValues) => (e: { target: { value: string } }) => setV({ ...v, [name]: e.target.value });
  const submit = form.handle(async () => {
    const saved = item ? await pipelineApi.editInterview(item.id, v) : await pipelineApi.addInterview(v);
    if (saved.suggest_status) onSuggest({ jobId: Number(v.application), status: saved.suggest_status });
    await client.invalidateQueries({ queryKey: KEY });
    notify("Interview saved.");
    if (!item) setV({ ...v, scheduled_at: "", where: "", notes: "" });
    onDone();
  });
  return (
    <form onSubmit={submit}>
      <SelectField label="Job" value={v.application} onChange={set("application")} errors={form.fields.application} required>
        <option value="">Pick a job…</option>
        {data.jobs.map((j) => (
          <option key={j.id} value={j.id}>
            {j.label}
          </option>
        ))}
      </SelectField>
      <TextField label="When" type="datetime-local" value={v.scheduled_at} onChange={set("scheduled_at")} errors={form.fields.scheduled_at} hint="In your own time zone." required />
      <SelectField label="Kind" value={v.kind} onChange={set("kind")} errors={form.fields.kind}>
        {data.kinds.map((k) => (
          <option key={k.value} value={k.value}>
            {k.label}
          </option>
        ))}
      </SelectField>
      <TextField label="Where or link" value={v.where} onChange={set("where")} errors={form.fields.where} maxLength={300} />
      <TextAreaField label="Notes" rows={3} value={v.notes} onChange={set("notes")} errors={form.fields.notes} hint="Who you will meet, what to prepare, questions to ask." maxLength={4000} />
      <FormError message={form.error} />
      <Button type="submit" disabled={form.busy}>
        {form.busy ? "Saving…" : item ? "Save changes" : "Add interview"}
      </Button>
    </form>
  );
}

function Row({ item, data, onEdit, upcoming = false }: { item: Interview; data: InterviewList; onEdit: () => void; upcoming?: boolean }) {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: KEY });
  const outcome = useMutation({ mutationFn: (o: string) => pipelineApi.interviewOutcome(item.id, o), onSuccess: refresh });
  const remove = useMutation({
    mutationFn: () => pipelineApi.deleteInterview(item.id),
    onSuccess: () => {
      notify("Deleted.");
      return refresh();
    },
  });
  const error = outcome.error || remove.error;
  const [help, setHelp] = useState<"" | "practise" | "thanks">("");
  return (
    <Card className="mb-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold">
            {item.kind_label} · {item.job.company} - {item.job.role}
          </h3>
          <p className="text-sm text-muted">{whenLabel(item.scheduled_local)}</p>
          {item.where && <p className="text-sm">{item.where}</p>}
          {item.notes && <p className="mt-1 whitespace-pre-wrap text-sm text-muted">{item.notes}</p>}
        </div>
        <Badge tone={item.outcome === "passed" ? "good" : item.outcome === "rejected" ? "bad" : "muted"}>{item.outcome_label}</Badge>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <label className="text-sm">
          <span className="mr-1 text-muted">How did it go?</span>
          <select
            className="rounded-md border border-border bg-surface px-2 py-1 text-sm"
            value={item.outcome}
            disabled={outcome.isPending}
            onChange={(e) => outcome.mutate(e.target.value)}
          >
            {data.outcomes.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        {upcoming && item.outcome === "pending" && (
          <a href={`/interviews/${item.id}/calendar.ics`} className={buttonClass("outline", true)} download>
            Add to calendar
          </a>
        )}
        <Button variant="outline" small onClick={onEdit}>
          Edit
        </Button>
        <Button variant="outline" small aria-expanded={help === "practise"} onClick={() => setHelp(help === "practise" ? "" : "practise")}>
          Practise for this interview
        </Button>
        <Button variant="outline" small aria-expanded={help === "thanks"} onClick={() => setHelp(help === "thanks" ? "" : "thanks")}>
          Draft a thank-you
        </Button>
        <Button
          variant="danger"
          small
          disabled={remove.isPending}
          onClick={() => {
            if (window.confirm("Delete this interview?")) remove.mutate();
          }}
        >
          Delete
        </Button>
      </div>
      {error && <p role="alert" className="mt-2 text-sm text-bad">{errorText(error)}</p>}
      {help === "practise" && <InterviewPrepSection jobId={item.job.id} />}
      {help === "thanks" && (
        <div className="mt-3 border-t border-border pt-3">
          <MessageDraft jobId={item.job.id} interviewId={item.id} defaultKind="thank_you" fixedKind />
        </div>
      )}
    </Card>
  );
}

export function Interviews() {
  const query = useQuery({ queryKey: KEY, queryFn: pipelineApi.interviews });
  const [editing, setEditing] = useState<number | null>(null);
  const [suggest, setSuggest] = useState<Suggestion | null>(null);
  if (query.isPending) return <Loading what="your interviews" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load your interviews.")} onRetry={() => query.refetch()} />;
  const data = query.data;
  const all = [...data.upcoming, ...data.past];
  const editItem = all.find((i) => i.id === editing);
  const noJobs = data.jobs.length === 0;
  return (
    <>
      <PageHeader title="Interviews" subtitle="Keep every conversation in one place: when it is, where, who you meet and what to prepare. Nothing is sent to anyone." />
      {suggest && (
        <div className="mb-4">
          <SuggestMove suggestion={suggest} onDone={() => setSuggest(null)} />
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <div>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">Coming up</h2>
            {data.upcoming.some((i) => i.outcome === "pending") && (
              <a href="/interviews/calendar.ics" className={buttonClass("ghost", true)} download>
                Download all as .ics
              </a>
            )}
          </div>
          {data.upcoming.length === 0 ? (
            <Card className="mb-6 text-sm text-muted">Nothing is booked. When a company invites you to talk, add it here so it shows on your dashboard.</Card>
          ) : (
            data.upcoming.map((i) => <Row key={i.id} item={i} data={data} onEdit={() => setEditing(i.id)} upcoming />)
          )}
          <h2 className="mb-2 mt-6 font-semibold">Earlier</h2>
          {data.past.length === 0 ? (
            <Card className="text-sm text-muted">Interviews that have happened, or were cancelled, will be listed here.</Card>
          ) : (
            data.past.map((i) => <Row key={i.id} item={i} data={data} onEdit={() => setEditing(i.id)} />)
          )}
        </div>
        <aside>
          <Card>
            <h2 className="mb-3 font-semibold">{editItem ? "Edit interview" : "Add an interview"}</h2>
            {noJobs ? (
              <Notice>Add a job to your tracker first, then you can schedule an interview for it.</Notice>
            ) : (
              <InterviewForm
                key={editItem?.id ?? "new"}
                data={data}
                item={editItem}
                defaultJob={jobFromSearch(window.location.search, data.jobs)}
                onDone={() => setEditing(null)}
                onSuggest={setSuggest}
              />
            )}
            {editItem && (
              <Button variant="ghost" small className="mt-2" onClick={() => setEditing(null)}>
                Cancel editing
              </Button>
            )}
          </Card>
          <CalendarLinkCard />
        </aside>
      </div>
    </>
  );
}
