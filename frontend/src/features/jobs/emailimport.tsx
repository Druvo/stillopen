"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Button, Card, Notice } from "@/components/ui";
import { errorText } from "@/lib/api";
import { navigate } from "@/lib/router";
import { notify } from "@/lib/toast";
import { jobsApi, type EmailDone, type EmailPreview } from "./api";
import { doneMessage, initiallyOff, previewHeadline, rowNotes, ticked } from "./importlogic";

const MAX_BYTES = 500 * 1024;

/**
 * "Import from an email": the person pastes one of their own job-alert emails (or copies a LinkedIn results or notifications list by hand),
 * or chooses a saved .eml file. We read the text, never open a link, and show what was found before anything is added.
 */
export function EmailImportCard() {
  const client = useQueryClient();
  const textId = useId();
  const fileId = useId();
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<EmailPreview | null>(null);
  const [off, setOff] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function reset() {
    setPreview(null);
    setError("");
  }

  function chooseFile(next: File | null) {
    setFile(next);
    reset();
    if (next && next.size > MAX_BYTES) setError("That email is bigger than 500 KB. Paste just the part with the jobs.");
  }

  async function check() {
    setBusy(true);
    setError("");
    try {
      const found = await jobsApi.importEmail<EmailPreview>({ text, file }, true);
      setPreview(found);
      setOff(initiallyOff(found));
    } catch (e) {
      setPreview(null);
      setError(errorText(e, "We could not read that email."));
    } finally {
      setBusy(false);
    }
  }

  async function add() {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      const done = await jobsApi.importEmail<EmailDone>({ text, file }, false, ticked(preview.rows, off));
      await Promise.all([client.invalidateQueries({ queryKey: ["dashboard"] }), client.invalidateQueries({ queryKey: ["stats"] })]);
      notify(doneMessage(done), done.stopped ? "info" : "success");
      navigate("/");
    } catch (e) {
      setError(errorText(e, "The import did not work. Nothing was added."));
      setBusy(false);
    }
  }

  const chosen = preview ? ticked(preview.rows, off).length : 0;
  const empty = !text.trim() && !file;
  return (
    <Card className="mb-4" role="region" aria-labelledby="email-import-title">
      <h2 id="email-import-title" className="font-semibold">
        Import from an email
      </h2>
      <p className="mt-1 text-sm text-muted">
        Get job alerts from LinkedIn, Indeed, Glassdoor or Google? Bring those jobs in without retyping them. Paste the email below, or choose a saved .eml file (that keeps the real links). We only read the text you give us and never open a link.
      </p>
      <details className="mt-2 text-sm">
        <summary className="cursor-pointer">Why we do not read LinkedIn directly, and how to turn on a LinkedIn job alert</summary>
        <p className="mt-2 text-muted">
          LinkedIn, Indeed and Glassdoor do not allow other programs to read their pages, and signing in for you could get your account blocked, so we never do either. A job alert is LinkedIn emailing <em>you</em>, which is fine to use.
        </p>
        <ol className="mt-1 list-decimal pl-5 text-muted">
          <li>On LinkedIn, search for the jobs you want (for example a title and a place).</li>
          <li>
            Switch on <strong>Set alert</strong> at the top of the results, and pick how often you want the email.
          </li>
          <li>When an alert email arrives, open it, select everything (Ctrl+A or Cmd+A), copy, and paste it here. Or save the email as an .eml file and choose it.</li>
        </ol>
        <p className="mt-2 text-muted">
          You can also copy a list from LinkedIn&apos;s Jobs page or notifications by hand and paste it here. Those jobs have no link, so each one is saved with a &quot;Find it on LinkedIn&quot; search link in its notes.
        </p>
      </details>
      <div className="mt-3">
        <label htmlFor={textId} className="mb-1 block text-sm font-medium">
          Paste the email here: select all in your mail app, copy, paste
        </label>
        <textarea
          id={textId}
          rows={6}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            reset();
          }}
          className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm"
        />
      </div>
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <div className="min-w-0">
          <label htmlFor={fileId} className="mb-1 block text-sm font-medium">
            Or choose a saved email (.eml)
          </label>
          <input id={fileId} type="file" accept=".eml,message/rfc822" onChange={(e) => chooseFile(e.target.files?.[0] ?? null)} className="block max-w-full text-sm" />
        </div>
        <Button variant="outline" onClick={check} disabled={busy || empty || (file?.size ?? 0) > MAX_BYTES}>
          {busy && !preview ? "Reading…" : "Check"}
        </Button>
      </div>
      {error && (
        <div className="mt-3">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
      {preview && (
        <div className="mt-4" aria-live="polite">
          <p className="font-medium">{previewHeadline(preview)}</p>
          {preview.problems.map((p) => (
            <p key={p} className="mt-1 text-sm text-muted">
              {p}
            </p>
          ))}
          {preview.rows.length > 0 && (
            <div className="mt-2 max-h-96 overflow-auto rounded-lg border border-border">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Jobs found in the email</caption>
                <thead className="sticky top-0 bg-surface-2">
                  <tr>
                    <th scope="col" className="px-2 py-1.5">
                      Add
                    </th>
                    <th scope="col" className="px-2 py-1.5">
                      Job
                    </th>
                    <th scope="col" className="px-2 py-1.5">
                      Notes
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {preview.rows.map((r) => (
                    <tr key={r.index} data-testid="email-row">
                      <td className="px-2 py-1.5 align-top">
                        <input
                          type="checkbox"
                          aria-label={`Add ${r.title}`}
                          checked={!off.has(r.index)}
                          onChange={(e) =>
                            setOff((o) => {
                              const next = new Set(o);
                              if (e.target.checked) next.delete(r.index);
                              else next.add(r.index);
                              return next;
                            })
                          }
                        />
                      </td>
                      <td className="px-2 py-1.5">
                        <strong>{r.title}</strong>
                        <div className="text-muted">{[r.company, r.location, r.salary].filter(Boolean).join(" · ") || "Company not found"}</div>
                      </td>
                      <td className="px-2 py-1.5 text-muted">
                        {rowNotes(r).map((note) => (
                          <p key={note} className={r.duplicate && note.startsWith("You already") ? "font-medium text-warn" : undefined}>
                            {note}
                          </p>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            {preview.rows.length > 0 && (
              <Button onClick={add} disabled={busy || chosen === 0}>
                {busy ? "Adding…" : `Add selected (${chosen})`}
              </Button>
            )}
            <Button variant="ghost" onClick={reset} disabled={busy}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
