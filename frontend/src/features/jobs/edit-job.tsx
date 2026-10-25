"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { FormError, SelectField, TextAreaField, TextField, useSubmit } from "@/components/form";
import { Button, buttonClass, Card, ErrorBox, Loading, Notice, PageHeader } from "@/components/ui";
import { errorText } from "@/lib/api";
import { Link } from "@/lib/router";
import { cn } from "@/lib/utils";
import { jobsApi, type Check, type JobDetails } from "./api";

export function FitList({ checks, empty }: { checks: Check[]; empty: string }) {
  if (checks.length === 0) return <p className="text-sm text-muted">{empty}</p>;
  return (
    <ul className="space-y-1.5 text-sm">
      {checks.map((c, i) => (
        <li key={i}>
          <strong className={cn("mr-1", c.level === "ok" ? "text-good" : c.level === "warn" ? "text-warn" : "text-muted")} aria-hidden>
            {c.level === "ok" ? "✓" : c.level === "warn" ? "!" : "i"}
          </strong>
          <span className="sr-only">{c.level === "ok" ? "Good: " : c.level === "warn" ? "Take care: " : "Note: "}</span>
          {c.text}
        </li>
      ))}
    </ul>
  );
}

const SELECTS = ["arrangement", "sponsorship", "relocation", "employment_type", "seniority"] as const;
const SELECT_LABELS: Record<(typeof SELECTS)[number], string> = {
  arrangement: "Where the work is done",
  sponsorship: "Visa sponsorship",
  relocation: "Relocation help",
  employment_type: "Kind of contract",
  seniority: "Level",
};

export function EditJob({ id }: { id: number }) {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["job-details", id], queryFn: () => jobsApi.details(id) });
  const form = useSubmit();
  const [values, setValues] = useState<Record<string, string> | null>(null);
  const [notice, setNotice] = useState("");
  const [redetecting, setRedetecting] = useState(false);
  const [redetectError, setRedetectError] = useState("");

  useEffect(() => {
    if (query.data && values === null) setValues(query.data.values);
  }, [query.data, values]);

  if (query.isPending || !values) {
    if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load this job.")} onRetry={() => query.refetch()} />;
    return <Loading what="this job" />;
  }
  const data = query.data as JobDetails;
  const set = (name: string) => (event: { target: { value: string } }) => setValues((v) => ({ ...(v ?? {}), [name]: event.target.value }));

  function accept(next: JobDetails) {
    client.setQueryData(["job-details", id], next);
    setValues(next.values);
    void client.invalidateQueries({ queryKey: ["dashboard"] });
  }

  async function redetect() {
    setRedetecting(true);
    setRedetectError("");
    setNotice("");
    try {
      const result = await jobsApi.redetect(id);
      accept(result);
      setNotice("Re-read the posting." + (result.changed.length ? ` Updated: ${result.changed.join(", ").replaceAll("_", " ")}.` : " Nothing to change."));
    } catch (e) {
      setRedetectError(errorText(e));
    } finally {
      setRedetecting(false);
    }
  }

  return (
    <>
      <PageHeader
        title={data.company}
        subtitle={data.role}
        actions={
          <Link to="/" className={buttonClass("ghost")}>
            ← Dashboard
          </Link>
        }
      />
      <p className="mb-4 text-sm text-muted">Correct anything about this job. Where it is and what kind of role it is decides whether it fits what you are looking for.</p>

      <Card className="mb-4">
        <h2 className="mb-2 font-semibold">Fit with what you want</h2>
        <FitList checks={data.fit} empty="Nothing to check yet." />
        <p className="mt-2 text-xs text-muted">
          Checked against your search areas in <Link to="/profile#areas" className="text-brand underline">Profile</Link>. This only flags a job; it never hides one.
        </p>
      </Card>

      <Card className="mb-4">
        <form
          onSubmit={form.handle(async () => {
            accept(await jobsApi.saveDetails(id, values));
            setNotice("Saved.");
          })}
        >
          <h2 className="mb-2 font-semibold">The job</h2>
          <TextField label="Company" value={values.company} onChange={set("company")} errors={form.fields.company} required />
          <TextField label="Role" value={values.role} onChange={set("role")} errors={form.fields.role} required />
          <TextField label="Link to the posting" type="url" value={values.url} onChange={set("url")} errors={form.fields.url} />
          <TextField label="Apply by (if it says)" type="date" value={values.deadline} onChange={set("deadline")} errors={form.fields.deadline} className="max-w-56" />
          <TextField label="Pay it advertises" value={values.advertised_pay} onChange={set("advertised_pay")} errors={form.fields.advertised_pay} />

          <h2 className="mb-1 mt-5 font-semibold">Where it is and what kind of role</h2>
          {data.details_source === "detected" && <p className="mb-2 text-xs text-muted">These were suggested by reading the posting. Check them and correct what is wrong.</p>}
          {data.details_source === "manual" && <p className="mb-2 text-xs text-muted">You set these yourself.</p>}
          <TextField label="Where it is" value={values.location_text} onChange={set("location_text")} errors={form.fields.location_text} />
          <TextField
            label="Country (where you must be based)"
            value={values.country}
            onChange={set("country")}
            errors={form.fields.country}
            hint="A name like Malaysia or a code like MY. Leave blank if the posting does not say, or for remote work open worldwide."
          />
          {SELECTS.map((name) => (
            <SelectField key={name} label={SELECT_LABELS[name]} value={values[name]} onChange={set(name)} errors={form.fields[name]}>
              {data.options[name].map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </SelectField>
          ))}

          <h2 className="mb-2 mt-5 font-semibold">Description and notes</h2>
          <TextAreaField label="The job description" rows={10} value={values.description} onChange={set("description")} errors={form.fields.description} />
          <TextAreaField label="Your own notes" rows={2} value={values.notes} onChange={set("notes")} errors={form.fields.notes} />
          <FormError message={form.error} />
          {notice && !form.error && <Notice tone="success">{notice}</Notice>}
          <div className="mt-3">
            <Button type="submit" disabled={form.busy}>
              {form.busy ? "Saving…" : "Save"}
            </Button>
          </div>
        </form>
      </Card>

      <Card>
        <h2 className="font-semibold">Read the posting again</h2>
        <p className="my-2 text-sm text-muted">Fills in the location, work arrangement, sponsorship, relocation, type and level from the description. Anything you set by hand is left alone.</p>
        <Button variant="outline" onClick={redetect} disabled={redetecting}>
          {redetecting ? "Reading…" : "Read it again"}
        </Button>
        {redetectError && <div className="mt-2"><Notice tone="error">{redetectError}</Notice></div>}
      </Card>
    </>
  );
}
