"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { Badge, Button, buttonClass, Card, ErrorBox, Loading, Notice, PageHeader } from "@/components/ui";
import { FormError, TextAreaField, TextField, useSubmit } from "@/components/form";
import { errorText } from "@/lib/api";
import { Link, navigate } from "@/lib/router";
import { notify } from "@/lib/toast";
import { cn } from "@/lib/utils";
import { coverApi, cvApi, type CvSummary } from "./api";
import { diffSummary, findingText, parseBlocks, parseInline, type Finding } from "./logic";

const when = (iso: string) => new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

/** A CV or letter as plain React text: headings, bullets, bold, italic and web links. Nothing in it can become markup. */
function Document({ text }: { text: string }) {
  const blocks = parseBlocks(text);
  const out: React.ReactNode[] = [];
  let items: React.ReactNode[] = [];
  const flush = (key: number) => {
    if (items.length) out.push(<ul key={`ul${key}`} className="ml-5 list-disc">{items}</ul>);
    items = [];
  };
  const inline = (line: string) =>
    parseInline(line).map((piece, i) => {
      if (piece.kind === "strong") return <strong key={i}>{piece.text}</strong>;
      if (piece.kind === "em") return <em key={i}>{piece.text}</em>;
      if (piece.kind === "link") {
        return (
          <a key={i} href={piece.href} target="_blank" rel="noopener noreferrer" className="text-brand underline">
            {piece.text}
          </a>
        );
      }
      return <Fragment key={i}>{piece.text}</Fragment>;
    });
  blocks.forEach((block, i) => {
    if (block.kind === "li") {
      items.push(<li key={i}>{inline(block.text)}</li>);
      return;
    }
    flush(i);
    if (block.kind === "hr") out.push(<hr key={i} className="my-2 border-border" />);
    else if (block.kind === "h1") out.push(<h2 key={i} className="mt-2 text-xl font-bold">{inline(block.text)}</h2>);
    else if (block.kind === "h2") out.push(<h3 key={i} className="mt-3 border-b border-border pb-0.5 text-base font-semibold uppercase tracking-wide">{inline(block.text)}</h3>);
    else if (block.kind === "h3") out.push(<h4 key={i} className="mt-2 font-semibold">{inline(block.text)}</h4>);
    else out.push(<p key={i}>{inline(block.text)}</p>);
  });
  flush(blocks.length);
  return <div className="space-y-1 text-sm leading-relaxed">{out}</div>;
}

function Findings({ items, thing, approved, approvedAt, onApprove, busy }: { items: Finding[]; thing: string; approved: boolean; approvedAt: string | null; onApprove: () => void; busy: boolean }) {
  if (items.length === 0) return <Notice tone="success">Fact check passed: nothing here goes beyond your own CV and documents.</Notice>;
  if (approved) {
    return (
      <Notice tone="success">
        You approved this {thing}
        {approvedAt ? ` on ${new Date(approvedAt).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}` : ""} after reviewing {items.length} flagged item{items.length === 1 ? "" : "s"}.
      </Notice>
    );
  }
  return (
    <Card className="border-warn">
      <p>
        <strong>Check these before you use this {thing}.</strong> They are not in your own CV or documents, so they may have been invented.
      </p>
      <ul className="my-2 ml-5 list-disc text-sm">
        {items.map((f, i) => (
          <li key={i}>
            {findingText(f)} <span className="text-muted">(line {f.line})</span>
          </li>
        ))}
      </ul>
      <p className="mb-2 text-sm text-muted">Edit the text to remove anything untrue{thing === "CV" ? ", which makes a new version" : ""}. If everything listed is in fact true, approve it. Downloading is locked until then.</p>
      <Button onClick={onApprove} disabled={busy}>
        Everything listed is true: approve
      </Button>
    </Card>
  );
}

function Row({ v, children }: { v: CvSummary; children?: React.ReactNode }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 py-2">
      <div>
        <Link to={`/cv/${v.id}`} className="font-semibold hover:underline">
          {v.label || `Version ${v.id}`}
        </Link>
        {v.current && <Badge className="ml-2">current</Badge>}
        <p className="text-sm text-muted">
          v{v.id} · {when(v.created_at)} · {v.source_label}
          {v.provider ? ` (${v.provider})` : ""}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </li>
  );
}

export function CvList() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["cv", "list"], queryFn: cvApi.list });
  const [message, setMessage] = useState("");
  const restore = useMutation({
    mutationFn: (id: number) => cvApi.restore(id),
    onSuccess: (made) => {
      client.invalidateQueries({ queryKey: ["cv"] });
      notify("Restored as your current CV. The history is kept.");
      navigate(`/cv/${made.id}`);
    },
    onError: (e) => setMessage(errorText(e)),
  });
  if (query.isPending) return <Loading what="your CVs" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load your CVs.")} onRetry={() => query.refetch()} />;
  const { masters, tailored } = query.data;
  return (
    <>
      <PageHeader title="Your CV versions" actions={<Link to="/cv/build" className={buttonClass("outline")}>Build from questions</Link>} />
      <p className="mb-4 text-sm text-muted">Every change to your CV is kept. Each tailored CV is saved with the job it was made for, so you always know exactly what you sent. Tailor a CV from a job on the dashboard.</p>
      {message && <div className="mb-3"><Notice tone="error">{message}</Notice></div>}

      <h2 className="mb-2 font-semibold">Tailored for jobs</h2>
      <Card className="mb-6">
        {tailored.length === 0 ? (
          <p className="text-sm text-muted">None yet. Press Tailor CV on a job on your dashboard.</p>
        ) : (
          <ul className="divide-y divide-border">
            {tailored.map((v) => (
              <Row key={v.id} v={v}>
                {v.flagged && !v.approved ? <Badge tone="warn">{v.flagged_count} to review</Badge> : v.flagged ? <Badge tone="good">approved</Badge> : <Badge tone="good">checked</Badge>}
              </Row>
            ))}
          </ul>
        )}
      </Card>

      <h2 className="mb-2 font-semibold">Your CV over time</h2>
      <Card>
        {masters.length === 0 ? (
          <p className="text-sm text-muted">
            Add your CV in your <Link to="/profile" className="text-brand underline">profile</Link>, or{" "}
            <Link to="/cv/build" className="text-brand underline">build one from a few questions</Link> if you don&apos;t have one yet.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {masters.map((v, i) => (
              <Row key={v.id} v={v}>
                {i > 0 && (
                  <>
                    <Link to={`/cv/${masters[0].id}/diff?against=${v.id}`} className={buttonClass("outline", true)}>
                      Compare with current
                    </Link>
                    <Button
                      small
                      disabled={restore.isPending}
                      onClick={() => {
                        setMessage("");
                        if (window.confirm("Make this your current CV? Your history is kept.")) restore.mutate(v.id);
                      }}
                    >
                      Restore
                    </Button>
                  </>
                )}
              </Row>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

export function CvDetail({ id }: { id: number }) {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["cv", "one", id], queryFn: () => cvApi.get(id) });
  const [message, setMessage] = useState("");
  const [saved, setSaved] = useState("");
  const form = useSubmit();
  const refresh = () => client.invalidateQueries({ queryKey: ["cv"] });
  const act = useMutation({ mutationFn: (fn: () => Promise<unknown>) => fn(), onSuccess: refresh, onError: (e) => setMessage(errorText(e)) });
  if (query.isPending) return <Loading what="this CV" />;
  if (query.isError) return <ErrorBox message="We could not find that CV." />;
  const v = query.data;
  const master = v.kind === "master";
  return (
    <>
      <PageHeader title={<>{v.label || "CV"} <Badge>v{v.id}</Badge></>} subtitle={<Link to="/cv" className="text-brand underline">All versions</Link>} />
      <p className="mb-3 text-sm text-muted">
        {v.kind_label} · {v.source_label}
        {v.provider ? ` (${v.provider})` : ""} · {when(v.created_at)}
        {v.job && <> · for <strong>{v.job.company} — {v.job.role}</strong></>}
        {v.parent && <> · based on <Link to={`/cv/${v.parent.id}`} className="text-brand underline">v{v.parent.id}</Link></>}
      </p>
      {message && <div className="mb-3"><Notice tone="error">{message}</Notice></div>}
      {saved && <div className="mb-3"><Notice tone="success">{saved}</Notice></div>}

      {!master && (
        <div className="mb-4">
          <Findings
            items={v.check_report}
            thing="CV"
            approved={v.approved}
            approvedAt={v.approved_at}
            busy={act.isPending}
            onApprove={() => {
              setMessage("");
              act.mutate(() => cvApi.approve(id), { onSuccess: () => setSaved("Approved. You can now download or print this version.") });
            }}
          />
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {v.downloads ? (
          <>
            <a className={buttonClass("primary")} href={v.downloads.docx}>Download DOCX</a>
            <a className={buttonClass("outline")} href={v.downloads.print} target="_blank" rel="noopener noreferrer">Print / save as PDF</a>
            <a className={buttonClass("outline")} href={v.downloads.md}>Markdown</a>
          </>
        ) : (
          <span className="text-sm text-muted">Downloads unlock after you review the flagged items.</span>
        )}
        <Link to={`/cv/${v.id}/diff`} className={buttonClass("outline")}>Compare</Link>
        {master ? (
          <Button
            variant="outline"
            disabled={act.isPending}
            onClick={() => {
              if (!window.confirm("Make this your current CV? Your history is kept.")) return;
              setMessage("");
              act.mutate(async () => {
                const made = await cvApi.restore(id);
                notify("Restored as your current CV. The history is kept.");
                navigate(`/cv/${made.id}`);
              });
            }}
          >
            Restore as current
          </Button>
        ) : (
          <Button
            variant="danger"
            disabled={act.isPending}
            onClick={() => {
              if (!window.confirm("Delete this tailored version?")) return;
              setMessage("");
              act.mutate(async () => {
                await cvApi.remove(id);
                notify("Deleted.");
                navigate("/cv");
              });
            }}
          >
            Delete
          </Button>
        )}
      </div>

      <h2 className="mb-2 font-semibold">Preview</h2>
      <Card className="mb-6 bg-white text-neutral-900">
        <Document text={v.content} />
      </Card>

      <h2 className="mb-1 font-semibold">Edit</h2>
      <p className="mb-2 text-sm text-muted">Saving creates a new version; this one stays as it is.{master ? " The saved text becomes your current CV." : ""}</p>
      <Card className="mb-6">
        <EditForm key={v.id} id={id} initial={v.content} form={form} onNoChange={() => setSaved("No changes to save.")} />
      </Card>

      {v.job_snapshot && (
        <Card>
          <details>
            <summary className="cursor-pointer">Job description when this was made</summary>
            <pre className="mt-2 whitespace-pre-wrap text-sm">{v.job_snapshot}</pre>
          </details>
        </Card>
      )}
    </>
  );
}

function EditForm({ id, initial, form, onNoChange }: { id: number; initial: string; form: ReturnType<typeof useSubmit>; onNoChange: () => void }) {
  const client = useQueryClient();
  const [content, setContent] = useState(initial);
  const [label, setLabel] = useState("");
  return (
    <form
      onSubmit={form.handle(async () => {
        const made = await cvApi.edit(id, content, label);
        client.invalidateQueries({ queryKey: ["cv"] });
        if (made.changed) {
          notify("Saved as a new version.");
          navigate(`/cv/${made.id}`);
        }
        else onNoChange();
      })}
    >
      <TextField label="Name for the new version (optional)" maxLength={140} value={label} onChange={(e) => setLabel(e.target.value)} errors={form.fields.label} />
      <TextAreaField
        label="CV (Markdown: # name, ## sections, - bullets, **bold**)"
        rows={22}
        className="font-mono"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        errors={form.fields.content}
      />
      <FormError message={form.error} />
      <Button type="submit" className="mt-2" disabled={form.busy}>
        {form.busy ? "Saving…" : "Save as new version"}
      </Button>
    </form>
  );
}

export function CvDiff({ id }: { id: number }) {
  const initial = typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("against");
  const [against, setAgainst] = useState<number | undefined>(initial && /^\d+$/.test(initial) ? Number(initial) : undefined);
  const query = useQuery({ queryKey: ["cv", "diff", id, against ?? null], queryFn: () => cvApi.diff(id, against) });
  if (query.isPending) return <Loading what="the comparison" />;
  if (query.isError) return <ErrorBox message="We could not compare these versions." />;
  const data = query.data;
  return (
    <>
      <PageHeader title="Compare" subtitle={<Link to={`/cv/${id}`} className="text-brand underline">Back to v{id}</Link>} />
      {!data.other ? (
        <Notice>There is nothing to compare this version with yet. Pick another version below, or save an edit first.</Notice>
      ) : (
        <p className="mb-3 text-sm text-muted">
          <span className="text-bad">Red</span>: in <strong>{data.other.label || "earlier version"}</strong> (v{data.other.id}) only. <span className="text-good">Green</span>: in{" "}
          <strong>{data.version.label || "this version"}</strong> (v{data.version.id}) only. {diffSummary(data.rows)}
        </p>
      )}
      {data.choices.length > 0 && (
        <div className="mb-3 flex items-center gap-2 text-sm">
          <label htmlFor="against">Compare v{id} with</label>
          <select
            id="against"
            value={data.other?.id ?? ""}
            onChange={(e) => {
              const next = Number(e.target.value);
              setAgainst(next);
              navigate(`/cv/${id}/diff?against=${next}`, { replace: true });
            }}
            className="rounded-md border border-border bg-surface px-2 py-1"
          >
            {!data.other && <option value="">Choose a version</option>}
            {data.choices.map((c) => (
              <option key={c.id} value={c.id}>
                v{c.id} · {c.label}
              </option>
            ))}
          </select>
        </div>
      )}
      {data.rows.length > 0 && (
        <Card className="overflow-x-auto font-mono text-[13px]">
          {data.rows.map((row, i) => (
            <div
              key={i}
              className={cn("whitespace-pre-wrap break-words", row.tag === "del" && "bg-bad/15 text-bad", row.tag === "add" && "bg-good/15 text-good")}
            >
              {row.tag === "del" ? "- " : row.tag === "add" ? "+ " : "  "}
              {row.text}
            </div>
          ))}
        </Card>
      )}
    </>
  );
}

export function CoverDetail({ id }: { id: number }) {
  const client = useQueryClient();
  const key = ["cover", id] as const;
  const query = useQuery({ queryKey: key, queryFn: () => coverApi.get(id) });
  const [message, setMessage] = useState("");
  const [saved, setSaved] = useState("");
  const [text, setText] = useState<string | null>(null);
  const form = useSubmit();
  const act = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: () => client.invalidateQueries({ queryKey: key }),
    onError: (e) => setMessage(errorText(e)),
  });
  if (query.isPending) return <Loading what="this letter" />;
  if (query.isError) return <ErrorBox message="We could not find that letter." />;
  const letter = query.data;
  const content = text ?? letter.content;
  return (
    <>
      <PageHeader
        title={`Cover letter for ${letter.job.company}`}
        subtitle={<Link to={`/jobs/${letter.job.id}/apply`} className="text-brand underline">Back to applying for {letter.job.role}</Link>}
      />
      <p className="mb-3 text-sm text-muted">
        {letter.source_label}
        {letter.provider ? ` (${letter.provider})` : ""} · {when(letter.updated_at)}
      </p>
      {message && <div className="mb-3"><Notice tone="error">{message}</Notice></div>}
      {saved && <div className="mb-3"><Notice tone="success">{saved}</Notice></div>}
      <div className="mb-4">
        <Findings
          items={letter.check_report}
          thing="letter"
          approved={letter.approved}
          approvedAt={letter.approved_at}
          busy={act.isPending}
          onApprove={() => {
            setMessage("");
            act.mutate(() => coverApi.approve(id), { onSuccess: () => setSaved("Approved.") });
          }}
        />
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {letter.downloads ? (
          <>
            <a className={buttonClass("primary")} href={letter.downloads.docx}>Download DOCX</a>
            <a className={buttonClass("outline")} href={letter.downloads.txt}>Plain text</a>
          </>
        ) : (
          <span className="text-sm text-muted">Downloads unlock after you review the flagged items.</span>
        )}
        <Button
          variant="danger"
          disabled={act.isPending}
          onClick={() => {
            if (!window.confirm("Delete this letter?")) return;
            setMessage("");
            act.mutate(async () => {
              await coverApi.remove(id);
              notify("Deleted.");
              navigate(`/jobs/${letter.job.id}/apply`);
            });
          }}
        >
          Delete
        </Button>
      </div>
      <Card>
        <form
          onSubmit={form.handle(async () => {
            setSaved("");
            const next = await coverApi.save(id, content);
            client.setQueryData(key, next);
            setText(null);
            setSaved(next.flagged ? "Saved. Some claims are not in your own material, check them above." : "Saved.");
          })}
        >
          <TextAreaField label="Letter" rows={18} value={content} onChange={(e) => setText(e.target.value)} errors={form.fields.content} hint="Saving checks the text again. The letter is never sent for you; copy or download it and send it yourself." />
          <FormError message={form.error} />
          <Button type="submit" className="mt-2" disabled={form.busy}>
            {form.busy ? "Saving…" : "Save"}
          </Button>
        </form>
      </Card>
    </>
  );
}
