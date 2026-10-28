"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { FormError, TextAreaField, TextField, useSubmit } from "@/components/form";
import { ApiError, errorText } from "@/lib/api";
import { notify } from "@/lib/toast";
import { depthApi, type Bank, type BankItem } from "./depth-api";

function parseTags(text: string): string[] {
  return text.split(",").map((t) => t.trim()).filter(Boolean);
}

function BankForm({ data, item, onDone }: { data: Bank; item?: BankItem; onDone: () => void }) {
  const client = useQueryClient();
  const form = useSubmit();
  const [question, setQuestion] = useState(item?.question ?? "");
  const [answer, setAnswer] = useState(item?.answer ?? "");
  const [tags, setTags] = useState(item?.tags.join(", ") ?? "");
  const [interviews, setInterviews] = useState<number[]>(item?.interviews.map((i) => i.id) ?? []);
  const [jobs, setJobs] = useState<number[]>(item?.jobs.map((j) => j.id) ?? []);
  const pick = (list: number[], set: (v: number[]) => void, id: number) => set(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  const submit = form.handle(async () => {
    const body = { question, answer, tags: parseTags(tags), interview_ids: interviews, job_ids: jobs };
    if (item) await depthApi.editBank(item.id, body);
    else await depthApi.addBank(body);
    await client.invalidateQueries({ queryKey: ["bank"] });
    notify("Question saved.");
    if (!item) {
      setQuestion("");
      setAnswer("");
      setTags("");
      setInterviews([]);
      setJobs([]);
    }
    onDone();
  });
  return (
    <form onSubmit={submit}>
      <TextField label="Question" value={question} onChange={(e) => setQuestion(e.target.value)} errors={form.fields.question} maxLength={400} required />
      <TextAreaField label="Your answer" rows={5} value={answer} onChange={(e) => setAnswer(e.target.value)} maxLength={4000} hint="In your own words. Only you see this." />
      <TextField label="Skill tags" value={tags} onChange={(e) => setTags(e.target.value)} hint="Up to five, separated by commas. For example: python, leadership." />
      {data.jobs.length > 0 && (
        <fieldset className="mb-3">
          <legend className="mb-1 text-sm font-medium">Jobs where it was asked</legend>
          {data.jobs.map((j) => (
            <label key={j.id} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={jobs.includes(j.id)} onChange={() => pick(jobs, setJobs, j.id)} /> {j.label}
            </label>
          ))}
        </fieldset>
      )}
      {data.interviews.length > 0 && (
        <fieldset className="mb-3">
          <legend className="mb-1 text-sm font-medium">Stages where it was asked</legend>
          {data.interviews.map((i) => (
            <label key={i.id} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={interviews.includes(i.id)} onChange={() => pick(interviews, setInterviews, i.id)} /> {i.label}
            </label>
          ))}
        </fieldset>
      )}
      <FormError message={form.error} />
      <Button type="submit" disabled={form.busy}>
        {form.busy ? "Saving…" : item ? "Save changes" : "Save question"}
      </Button>
    </form>
  );
}

function Row({ item, onEdit }: { item: BankItem; onEdit: () => void }) {
  const client = useQueryClient();
  const remove = useMutation({
    mutationFn: async () => {
      try {
        await depthApi.deleteBank(item.id);
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          if (!window.confirm("This question is linked to an interview or a job. Delete it anyway?")) return;
          await depthApi.deleteBank(item.id, true);
        } else throw e;
      }
      notify("Deleted.");
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ["bank"] }),
  });
  return (
    <Card className="mb-3">
      <h3 className="font-semibold">{item.question}</h3>
      {item.answer && <p className="mt-1 whitespace-pre-wrap text-sm">{item.answer}</p>}
      <div className="mt-2 flex flex-wrap gap-1">
        {item.tags.map((t) => (
          <Badge key={t}>{t}</Badge>
        ))}
      </div>
      {(item.jobs.length > 0 || item.interviews.length > 0) && (
        <p className="mt-1 text-sm text-muted">Asked at: {[...item.jobs.map((j) => j.label), ...item.interviews.map((i) => i.label)].join("; ")}</p>
      )}
      <div className="mt-3 flex gap-2">
        <Button variant="outline" small onClick={onEdit}>
          Edit
        </Button>
        <Button variant="danger" small disabled={remove.isPending} onClick={() => remove.mutate()}>
          Delete
        </Button>
      </div>
      {remove.isError && (
        <p role="alert" className="mt-2 text-sm text-bad">
          {errorText(remove.error)}
        </p>
      )}
    </Card>
  );
}

export function QuestionBank() {
  const [search, setSearch] = useState("");
  const [tag, setTag] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const query = useQuery({ queryKey: ["bank", search, tag], queryFn: () => depthApi.bank(search, tag), placeholderData: (prev) => prev });
  if (query.isPending) return <Loading what="your question bank" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load your question bank.")} onRetry={() => query.refetch()} />;
  const data = query.data;
  const editItem = data.questions.find((q) => q.id === editing);
  return (
    <>
      <PageHeader title="Question bank" subtitle="Interview questions you want to be ready for, with your own answers. Save one from any prep list, or add your own." />
      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <div>
          <div className="mb-3 flex flex-wrap gap-3">
            <TextField label="Search" type="search" value={search} onChange={(e) => setSearch(e.target.value)} maxLength={100} />
            <label className="text-sm">
              <span className="mb-1 block font-medium">Tag</span>
              <select className="rounded-md border border-border bg-surface px-2 py-2 text-sm" value={tag} onChange={(e) => setTag(e.target.value)}>
                <option value="">All tags</option>
                {data.tags.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {data.questions.length === 0 ? (
            <Card className="text-sm text-muted">
              {search || tag
                ? "No saved question matches. Clear the search or pick another tag."
                : "Nothing saved yet. Add a question you were asked, or press Save to my question bank on a prep question."}
            </Card>
          ) : (
            data.questions.map((q) => <Row key={q.id} item={q} onEdit={() => setEditing(q.id)} />)
          )}
        </div>
        <aside>
          <Card>
            <h2 className="mb-3 font-semibold">{editItem ? "Edit question" : "Add a question"}</h2>
            <BankForm key={editItem?.id ?? "new"} data={data} item={editItem} onDone={() => setEditing(null)} />
            {editItem && (
              <Button variant="ghost" small className="mt-2" onClick={() => setEditing(null)}>
                Cancel editing
              </Button>
            )}
          </Card>
        </aside>
      </div>
    </>
  );
}
