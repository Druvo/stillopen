"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Star } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { FormError, TextAreaField, TextField, useSubmit } from "@/components/form";
import { errorText } from "@/lib/api";
import { Link } from "@/lib/router";
import { notify } from "@/lib/toast";
import { companyPath, depthApi, type CompanyPage } from "./depth-api";

export function Companies() {
  const query = useQuery({ queryKey: ["companies"], queryFn: depthApi.companies });
  if (query.isPending) return <Loading what="your companies" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load your companies.")} onRetry={() => query.refetch()} />;
  const rows = query.data.companies;
  return (
    <>
      <PageHeader title="Companies" subtitle="Every company in your jobs and contacts, with what you know about it in one place." />
      {rows.length === 0 ? (
        <Card className="text-sm text-muted">No companies yet. Add a job to your tracker and its company will appear here.</Card>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {rows.map((c) => (
            <li key={c.key}>
              <Card>
                <h2 className="font-semibold">
                  <Link to={companyPath(c.name)} className="underline">
                    {c.name}
                  </Link>{" "}
                  {c.watched && <Badge tone="brand">Watching</Badge>}
                </h2>
                <p className="text-sm text-muted">
                  {c.jobs} job{c.jobs === 1 ? "" : "s"} · {c.contacts} contact{c.contacts === 1 ? "" : "s"}
                </p>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function Details({ page }: { page: CompanyPage }) {
  const client = useQueryClient();
  const form = useSubmit();
  const [v, setV] = useState({ notes: page.notes, website: page.website, careers: page.careers, linkedin: page.linkedin });
  const set = (name: keyof typeof v) => (e: { target: { value: string } }) => setV({ ...v, [name]: e.target.value });
  const submit = form.handle(async () => {
    const saved = await depthApi.editCompany(page.name, v);
    client.setQueryData(["company", page.key], saved);
    notify("Saved.");
  });
  return (
    <form onSubmit={submit}>
      <TextAreaField label="Your notes" rows={5} value={v.notes} onChange={set("notes")} maxLength={4000} hint="What you learned, who said what, why you like it." />
      <TextField label="Website" type="url" value={v.website} onChange={set("website")} errors={form.fields.website} maxLength={300} hint="Starts with https://. StillOpen only keeps the address; it never opens it." />
      <TextField label="Careers page" type="url" value={v.careers} onChange={set("careers")} errors={form.fields.careers} maxLength={300} />
      <TextField label="LinkedIn page" type="url" value={v.linkedin} onChange={set("linkedin")} errors={form.fields.linkedin} maxLength={300} />
      <FormError message={form.error} />
      <Button type="submit" disabled={form.busy}>
        {form.busy ? "Saving…" : "Save details"}
      </Button>
    </form>
  );
}

function LinkLine({ label, href }: { label: string; href: string }) {
  return href ? (
    <a href={href} target="_blank" rel="noopener noreferrer" className="underline">
      {label}
    </a>
  ) : null;
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-muted">{children}</p>;
}

export function CompanyDetail({ name }: { name: string }) {
  const client = useQueryClient();
  const key = ["company", name.trim().toLowerCase().replace(/\s+/g, " ")];
  const query = useQuery({ queryKey: key, queryFn: () => depthApi.company(name) });
  const watch = useMutation({
    mutationFn: (watched: boolean) => depthApi.editCompany(name, { watched }),
    onSuccess: (saved) => {
      client.setQueryData(key, saved);
      void client.invalidateQueries({ queryKey: ["companies"] });
    },
  });
  if (query.isPending) return <Loading what="this company" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not find that company in your tracker.")} onRetry={() => query.refetch()} />;
  const page = query.data;
  return (
    <>
      <PageHeader
        title={page.name}
        subtitle={
          <Link to="/companies" className="underline">
            All companies
          </Link>
        }
        actions={
          <Button variant={page.watched ? "primary" : "outline"} aria-pressed={page.watched} disabled={watch.isPending} onClick={() => watch.mutate(!page.watched)}>
            <Star className="mr-1 inline size-4" aria-hidden /> {page.watched ? "Watching" : "Watch"}
          </Button>
        }
      />
      <p className="mb-4 flex flex-wrap gap-4 text-sm">
        <LinkLine label="Website" href={page.website} />
        <LinkLine label="Careers" href={page.careers} />
        <LinkLine label="LinkedIn" href={page.linkedin} />
      </p>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <Card>
            <h2 className="mb-2 font-semibold">Jobs</h2>
            {page.jobs.length === 0 ? (
              <Empty>No jobs tracked here. Add one from the dashboard.</Empty>
            ) : (
              <ul className="space-y-1 text-sm">
                {page.jobs.map((j) => (
                  <li key={j.id}>
                    {j.role} <Badge>{j.status}</Badge>{" "}
                    <Link to={`/jobs/${j.id}/process`} className="underline">
                      Hiring process
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card>
            <h2 className="mb-2 font-semibold">People you know here</h2>
            {page.contacts.length === 0 ? (
              <Empty>
                No contacts yet. Add one on the{" "}
                <Link to="/contacts" className="underline">
                  Contacts
                </Link>{" "}
                page and set their company.
              </Empty>
            ) : (
              <ul className="space-y-1 text-sm">
                {page.contacts.map((c) => (
                  <li key={c.id}>
                    {c.name}
                    {c.title && ` · ${c.title}`}
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card>
            <h2 className="mb-2 font-semibold">Interviews</h2>
            {page.interviews.length === 0 ? (
              <Empty>No interviews with them yet.</Empty>
            ) : (
              <ul className="space-y-1 text-sm">
                {page.interviews.map((i) => (
                  <li key={i.id}>
                    {i.name} for {i.role}, {i.when} <Badge>{i.outcome_label}</Badge>
                    {i.interviewers.length > 0 && <span className="text-muted"> with {i.interviewers.join(", ")}</span>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card>
            <h2 className="mb-2 font-semibold">Offers</h2>
            {page.offers.length === 0 ? (
              <Empty>No offers from them.</Empty>
            ) : (
              <ul className="space-y-1 text-sm">
                {page.offers.map((o) => (
                  <li key={o.id}>
                    {o.role}: {o.base} {o.currency} <Badge>{o.status_label}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
        <Card>
          <h2 className="mb-3 font-semibold">Notes and links</h2>
          <Details key={page.key + page.notes + page.website + page.careers + page.linkedin} page={page} />
        </Card>
      </div>
    </>
  );
}
