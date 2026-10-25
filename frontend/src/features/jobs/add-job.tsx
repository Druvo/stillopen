"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { takePrefill } from "@/features/dashboard/prefill";
import { FormError, TextAreaField, TextField, useSubmit } from "@/components/form";
import { Button, buttonClass, Card, Notice, PageHeader } from "@/components/ui";
import { errorText } from "@/lib/api";
import { Link, navigate } from "@/lib/router";
import { notify } from "@/lib/toast";
import { jobsApi, type Duplicate } from "./api";
import { EmailImportCard } from "./emailimport";
import { ImportCard } from "./import-card";
import { blockedNote } from "./importlogic";
import { LinkedinImportCard } from "./linkedinimport";
import { duplicateMessage, duplicateOf } from "./jobmgmt";
import { mergePrefill } from "./logic";
import { fillFromParsed } from "./paste";
import { PasteFill } from "./paste-fill";

/** After a link on a site that does not let us read it: put the cursor in the description box, so the next thing is to paste the text. */
function focusDescription() {
  window.setTimeout(() => document.getElementById("job-description-field")?.querySelector("textarea")?.focus(), 0);
}

const BLANK: Record<string, string> = { company: "", role: "", url: "", deadline: "", description: "", notes: "" };

export function AddJob() {
  const client = useQueryClient();
  const form = useSubmit();
  const [values, setValues] = useState<Record<string, string>>(BLANK);
  const [link, setLink] = useState("");
  const [reading, setReading] = useState(false);
  const [readNote, setReadNote] = useState<{ tone: "info" | "error"; text: string } | null>(null);
  // The job the person already tracks that this one looks like (asked for by the server; they may open it or add this one anyway).
  const [duplicate, setDuplicate] = useState<Duplicate | null>(null);
  useEffect(() => {
    // The dashboard's quick-add bar read a posting and handed it over: fill the form with it (nothing is saved until Save).
    const found = takePrefill();
    if (found) {
      setValues((v) => mergePrefill(v, found));
      setLink(found.url);
      if (found.blocked_host) {
        setValues((v) => ({ ...v, url: found.url }));
        setReadNote({ tone: "info", text: blockedNote(found.blocked_host, found.message) });
        focusDescription();
      } else {
        setReadNote({ tone: "info", text: "We read this from the link. Please check the company and role before you save." });
      }
    }
  }, []);
  const set = (name: string) => (event: { target: { value: string } }) => {
    if (name === "company" || name === "role" || name === "url") setDuplicate(null);
    setValues((v) => ({ ...v, [name]: event.target.value }));
  };

  /** Saves the job; if the same one is already tracked, asks first (`allow` is the person's "add it anyway"). */
  async function save(allow: boolean) {
    let made;
    try {
      made = await jobsApi.addJob(values, allow);
    } catch (e) {
      const same = duplicateOf(e);
      if (!same) throw e;
      setDuplicate(same);
      return;
    }
    await client.invalidateQueries({ queryKey: ["dashboard"] });
    notify(`Saved ${made.company} - ${made.role}. Next, press Check my fit to see how well it suits you.`);
    navigate("/");
  }

  async function readLink() {
    setReading(true);
    setReadNote(null);
    try {
      const prefill = await jobsApi.quickAdd(link);
      setDuplicate(prefill.duplicate ?? null);
      if (prefill.blocked_host) {
        // LinkedIn, Indeed, Glassdoor...: nothing was fetched. Keep the (cleaned) link and ask for the text.
        setValues((v) => ({ ...v, url: prefill.url }));
        setLink(prefill.url);
        setReadNote({ tone: "info", text: blockedNote(prefill.blocked_host, prefill.message) });
        focusDescription();
        return;
      }
      setValues((v) => mergePrefill(v, prefill));
      setReadNote({ tone: "info", text: "We read this from the link. It is a best guess, so check the company, the role and the description before you save." });
    } catch (e) {
      setReadNote({ tone: "error", text: errorText(e) });
    } finally {
      setReading(false);
    }
  }

  return (
    <>
      <PageHeader title="Add a job" subtitle="Found a role somewhere? Paste its link and we will read it for you, or type it in. Nothing is saved until you press Save." />
      <Card className="mb-4">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (link.trim() && !reading) void readLink();
          }}
          className="flex flex-wrap items-end gap-2"
        >
          <div className="min-w-0 flex-1">
            <TextField label="Paste a link to the job" type="url" autoComplete="off" value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://" />
          </div>
          <Button type="submit" variant="outline" disabled={reading || !link.trim()} className="mb-3">
            {reading ? "Reading…" : "Read the link"}
          </Button>
        </form>
        <p className="text-xs text-muted">LinkedIn, Indeed, Glassdoor and some other sites do not let us read their pages. We keep the link and you paste the job text below.</p>
        {readNote && <div className="mt-2"><Notice tone={readNote.tone === "error" ? "error" : "info"}>{readNote.text}</Notice></div>}
      </Card>

      <Card className="mb-4">
        <form
          onSubmit={form.handle(() => save(false))}
        >
          <TextField label="Company" autoComplete="off" value={values.company} onChange={set("company")} errors={form.fields.company} required />
          <TextField label="Role" autoComplete="off" value={values.role} onChange={set("role")} errors={form.fields.role} required />
          <TextField label="Link to the posting" type="url" autoComplete="off" value={values.url} onChange={set("url")} errors={form.fields.url} />
          <TextField label="Apply by (if it says)" type="date" value={values.deadline} onChange={set("deadline")} errors={form.fields.deadline} className="max-w-56" />
          <div id="job-description-field">
            <TextAreaField
              label="The job description"
              rows={10}
              value={values.description}
              onChange={set("description")}
              errors={form.fields.description}
              hint="Paste the text of the posting here. Or leave this empty and we will read it from the link."
            />
          </div>
          <PasteFill
            text={values.description}
            onFields={(fields) => {
              const result = fillFromParsed(values, fields);
              setValues(result.values);
              if (result.values.company !== values.company || result.values.role !== values.role || result.values.url !== values.url) setDuplicate(null);
              return result.filled;
            }}
          />
          <TextAreaField label="Your own notes" rows={2} value={values.notes} onChange={set("notes")} errors={form.fields.notes} />
          <FormError message={form.error} />
          {duplicate && (
            <div className="mb-3" id="duplicate-warning">
              <Notice tone="info">
                <p>
                  <strong>{duplicateMessage(duplicate)}</strong>
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Link to={`/jobs/${duplicate.id}/edit`} className={buttonClass("outline", true)}>
                    Open it
                  </Link>
                  <Button small variant="outline" disabled={form.busy} onClick={form.handle(() => save(true))}>
                    Add this one anyway
                  </Button>
                </div>
              </Notice>
            </div>
          )}
          <div className="mt-3 flex gap-2">
            <Button type="submit" disabled={form.busy}>
              {form.busy ? "Saving…" : "Save job"}
            </Button>
            <Link to="/" className={buttonClass("ghost")}>
              Cancel
            </Link>
          </div>
        </form>
      </Card>

      <EmailImportCard />
      <LinkedinImportCard />
      <ImportCard />
    </>
  );
}
