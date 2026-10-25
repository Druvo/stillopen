"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { takePrefill } from "@/features/dashboard/prefill";
import { FormError, TextAreaField, TextField, useSubmit } from "@/components/form";
import { Button, buttonClass, Card, Notice, PageHeader } from "@/components/ui";
import { errorText } from "@/lib/api";
import { Link, navigate } from "@/lib/router";
import { notify } from "@/lib/toast";
import { jobsApi } from "./api";
import { mergePrefill } from "./logic";

const BLANK: Record<string, string> = { company: "", role: "", url: "", deadline: "", description: "", notes: "" };

export function AddJob() {
  const client = useQueryClient();
  const form = useSubmit();
  const [values, setValues] = useState<Record<string, string>>(BLANK);
  const [link, setLink] = useState("");
  const [reading, setReading] = useState(false);
  const [readNote, setReadNote] = useState<{ tone: "info" | "error"; text: string } | null>(null);
  useEffect(() => {
    // The dashboard's quick-add bar read a posting and handed it over: fill the form with it (nothing is saved until Save).
    const found = takePrefill();
    if (found) {
      setValues((v) => mergePrefill(v, found));
      setLink(found.url);
      setReadNote({ tone: "info", text: "We read this from the link. Please check the company and role before you save." });
    }
  }, []);
  const set = (name: string) => (event: { target: { value: string } }) => setValues((v) => ({ ...v, [name]: event.target.value }));

  async function readLink() {
    setReading(true);
    setReadNote(null);
    try {
      const prefill = await jobsApi.quickAdd(link);
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
            <TextField label="Paste a link to the job" type="url" value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://" />
          </div>
          <Button type="submit" variant="outline" disabled={reading || !link.trim()} className="mb-3">
            {reading ? "Reading…" : "Read the link"}
          </Button>
        </form>
        <p className="text-xs text-muted">LinkedIn and some other sites do not let us read their pages. If that happens, paste the job text below.</p>
        {readNote && <div className="mt-2"><Notice tone={readNote.tone === "error" ? "error" : "info"}>{readNote.text}</Notice></div>}
      </Card>

      <Card>
        <form
          onSubmit={form.handle(async () => {
            const made = await jobsApi.addJob(values);
            await client.invalidateQueries({ queryKey: ["dashboard"] });
            notify(`Saved ${made.company} - ${made.role}. Next, press Check my fit to see how well it suits you.`);
            navigate("/");
            return made;
          })}
        >
          <TextField label="Company" value={values.company} onChange={set("company")} errors={form.fields.company} required />
          <TextField label="Role" value={values.role} onChange={set("role")} errors={form.fields.role} required />
          <TextField label="Link to the posting" type="url" value={values.url} onChange={set("url")} errors={form.fields.url} />
          <TextField label="Apply by (if it says)" type="date" value={values.deadline} onChange={set("deadline")} errors={form.fields.deadline} className="max-w-56" />
          <TextAreaField
            label="The job description"
            rows={10}
            value={values.description}
            onChange={set("description")}
            errors={form.fields.description}
            hint="Paste the text of the posting here. Or leave this empty and we will read it from the link."
          />
          <TextAreaField label="Your own notes" rows={2} value={values.notes} onChange={set("notes")} errors={form.fields.notes} />
          <FormError message={form.error} />
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
    </>
  );
}
