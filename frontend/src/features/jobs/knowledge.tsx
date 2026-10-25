"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Field, FormError, SelectField, TextAreaField, TextField, useSubmit } from "@/components/form";
import { Badge, Button, Card, ErrorBox, Loading, Notice, PageHeader } from "@/components/ui";
import { errorText } from "@/lib/api";
import { Link } from "@/lib/router";
import { notify } from "@/lib/toast";
import { jobsApi, type DocumentRow, type Documents } from "./api";
import { fileSize } from "./logic";

const KEY = ["documents"] as const;

function AddDocument({ data }: { data: Documents }) {
  const client = useQueryClient();
  const form = useSubmit();
  const fileInput = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("project");
  const [text, setText] = useState("");
  const [added, setAdded] = useState("");

  return (
    <Card className="mb-4">
      <form
        onSubmit={form.handle(async () => {
          const body = new FormData();
          body.set("title", title);
          body.set("kind", kind);
          body.set("text", text);
          const file = fileInput.current?.files?.[0];
          if (file) body.set("file", file);
          const made = await jobsApi.addDocument(body);
          await client.invalidateQueries({ queryKey: KEY });
          setTitle("");
          setText("");
          if (fileInput.current) fileInput.current.value = "";
          setAdded(`Added ${made.title}.`);
        })}
      >
        <TextField label="Title" value={title} onChange={(e) => setTitle(e.target.value)} errors={form.fields.title} maxLength={160} required />
        <SelectField label="What it is" value={kind} onChange={(e) => setKind(e.target.value)} errors={form.fields.kind}>
          {data.kinds.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </SelectField>
        <TextAreaField label="Text" rows={8} value={text} onChange={(e) => setText(e.target.value)} errors={form.fields.text} hint="Paste it here, or upload a file below." />
        <Field label="Or upload a file" htmlFor="doc-file" hint={`A .txt, .md or .pdf file, up to ${fileSize(data.limits.max_file_bytes)}. We read the text and then discard the file.`} errors={form.fields.file}>
          <input id="doc-file" ref={fileInput} type="file" accept=".txt,.md,.markdown,.pdf" className="text-sm" />
        </Field>
        <FormError message={form.error} />
        {added && !form.error && <Notice tone="success">{added}</Notice>}
        <Button type="submit" disabled={form.busy} className="mt-3">
          {form.busy ? "Adding…" : "Add document"}
        </Button>
      </form>
    </Card>
  );
}

function Row({ doc }: { doc: DocumentRow }) {
  const client = useQueryClient();
  const [error, setError] = useState("");
  const done = { onSuccess: () => client.invalidateQueries({ queryKey: KEY }), onError: (e: unknown) => setError(errorText(e)) };
  const toggle = useMutation({
    mutationFn: () => jobsApi.toggleDocument(doc.id),
    ...done,
    onSuccess: (r: { enabled: boolean }) => {
      notify(r.enabled ? `"${doc.title}" will be used again.` : `"${doc.title}" is hidden from the AI.`);
      return client.invalidateQueries({ queryKey: KEY });
    },
  });
  const remove = useMutation({
    mutationFn: () => jobsApi.deleteDocument(doc.id),
    ...done,
    onSuccess: () => {
      notify("Deleted.");
      return client.invalidateQueries({ queryKey: KEY });
    },
  });
  const busy = toggle.isPending || remove.isPending;
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 border-b border-border py-3 last:border-0">
      <div>
        <p className="font-semibold">
          {doc.title} {!doc.enabled && <Badge>Hidden from the AI</Badge>}
        </p>
        <p className="text-sm text-muted">
          {doc.kind_label} · {doc.characters.toLocaleString()} characters · {doc.passages} passages
        </p>
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      </div>
      <div className="flex gap-2">
        <Button small variant="outline" disabled={busy} onClick={() => toggle.mutate()}>
          {doc.enabled ? "Hide from the AI" : "Use again"}
        </Button>
        <Button
          small
          variant="danger"
          disabled={busy}
          onClick={() => {
            if (window.confirm(`Delete "${doc.title}"?`)) remove.mutate();
          }}
        >
          Delete
        </Button>
      </div>
    </li>
  );
}

export function Knowledge() {
  const query = useQuery({ queryKey: KEY, queryFn: jobsApi.documents });
  if (query.isPending) return <Loading what="your documents" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load your documents.")} onRetry={() => query.refetch()} />;
  const data = query.data;
  return (
    <>
      <PageHeader title="Documents about you" />
      <p className="mb-4 text-sm text-muted">
        Projects, work history details, certificates, cover letters. For each job, only the passages that matter are used. Uploaded files are read for their text and then discarded; only the text is kept.
      </p>
      <p className="mb-4 text-sm">
        {data.cv.present ? (
          <>
            <Badge tone="good">Your CV is included</Badge> It comes from your <Link to="/profile" className="text-brand underline">profile</Link> and is always used.
          </>
        ) : (
          <>
            <Badge tone="warn">No CV yet</Badge> Add your CV in your <Link to="/profile" className="text-brand underline">profile</Link> so tailoring and fit checks have something to work from.
          </>
        )}
      </p>
      {data.sources.length >= data.limits.max_documents ? (
        <div className="mb-4"><Notice tone="info">You have reached the limit of {data.limits.max_documents} documents. Delete one to add another.</Notice></div>
      ) : (
        <AddDocument data={data} />
      )}
      <Card>
        {data.sources.length === 0 ? (
          <p className="text-sm text-muted">Nothing added yet. Use the form above to add a project write-up, a certificate or anything else that shows what you can do.</p>
        ) : (
          <ul>
            {data.sources.map((doc) => (
              <Row key={doc.id} doc={doc} />
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
