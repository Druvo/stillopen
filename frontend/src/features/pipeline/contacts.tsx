"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, ErrorBox, Loading, Notice, PageHeader } from "@/components/ui";
import { FormError, SelectField, TextAreaField, TextField, useSubmit } from "@/components/form";
import { errorText } from "@/lib/api";
import { notify } from "@/lib/toast";
import { pipelineApi, type Contact, type ContactList, type ContactValues, type ReferralValues } from "./api";
import { dayLabel } from "./logic";
import { ReferralDraft } from "./referral";

const KEY = ["pipeline", "contacts"] as const;

function ContactForm({ item, onDone }: { item?: Contact; onDone: () => void }) {
  const client = useQueryClient();
  const form = useSubmit();
  const empty: ContactValues = { name: "", company: "", title: "", email: "", link: "", last_contacted: "", notes: "" };
  const [v, setV] = useState<ContactValues>(
    item ? { name: item.name, company: item.company, title: item.title, email: item.email, link: item.link, last_contacted: item.last_contacted, notes: item.notes } : empty,
  );
  const set = (name: keyof ContactValues) => (e: { target: { value: string } }) => setV({ ...v, [name]: e.target.value });
  const submit = form.handle(async () => {
    if (item) await pipelineApi.editContact(item.id, v);
    else await pipelineApi.addContact(v);
    await client.invalidateQueries({ queryKey: KEY });
    notify("Contact saved.");
    if (!item) setV(empty);
    onDone();
  });
  return (
    <form onSubmit={submit}>
      <TextField label="Name" value={v.name} onChange={set("name")} errors={form.fields.name} maxLength={120} required />
      <TextField label="Company" value={v.company} onChange={set("company")} errors={form.fields.company} maxLength={160} />
      <TextField label="Their role" value={v.title} onChange={set("title")} errors={form.fields.title} maxLength={160} />
      <TextField label="Email" type="email" value={v.email} onChange={set("email")} errors={form.fields.email} hint="Kept for you only. StillOpen never writes to anyone." />
      <TextField label="Profile link" type="url" value={v.link} onChange={set("link")} errors={form.fields.link} maxLength={300} />
      <TextField label="Last spoke" type="date" value={v.last_contacted} onChange={set("last_contacted")} errors={form.fields.last_contacted} />
      <TextAreaField label="Notes" rows={2} value={v.notes} onChange={set("notes")} errors={form.fields.notes} maxLength={2000} />
      <FormError message={form.error} />
      <Button type="submit" disabled={form.busy}>
        {form.busy ? "Saving…" : item ? "Save changes" : "Add contact"}
      </Button>
    </form>
  );
}

function ReferralForm({ data, contacts }: { data: ContactList; contacts: Contact[] }) {
  const client = useQueryClient();
  const form = useSubmit();
  const [v, setV] = useState<ReferralValues>({ contact: "", application: "", status: "thinking", note: "" });
  const set = (name: keyof ReferralValues) => (e: { target: { value: string } }) => setV({ ...v, [name]: e.target.value });
  const submit = form.handle(async () => {
    await pipelineApi.addReferral(v);
    await client.invalidateQueries({ queryKey: KEY });
    notify("Referral saved.");
    setV({ contact: "", application: "", status: "thinking", note: "" });
  });
  return (
    <form onSubmit={submit}>
      <SelectField label="Who" value={v.contact} onChange={set("contact")} errors={form.fields.contact} required>
        <option value="">Pick a contact…</option>
        {contacts.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </SelectField>
      <SelectField label="For which job" value={v.application} onChange={set("application")} errors={form.fields.application} required>
        <option value="">Pick a job…</option>
        {data.jobs.map((j) => (
          <option key={j.id} value={j.id}>
            {j.label}
          </option>
        ))}
      </SelectField>
      <SelectField label="Where it stands" value={v.status} onChange={set("status")} errors={form.fields.status}>
        {data.referral_statuses.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </SelectField>
      <TextField label="Note" value={v.note} onChange={set("note")} errors={form.fields.note} maxLength={300} />
      <FormError message={form.error} />
      <Button type="submit" disabled={form.busy}>
        {form.busy ? "Saving…" : "Add referral"}
      </Button>
    </form>
  );
}

function Person({ item, data, onEdit }: { item: Contact; data: ContactList; onEdit: () => void }) {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: KEY });
  const status = useMutation({ mutationFn: (a: { id: number; status: string }) => pipelineApi.referralStatus(a.id, a.status), onSuccess: refresh });
  const deleted = () => {
    notify("Deleted.");
    return refresh();
  };
  const dropReferral = useMutation({ mutationFn: (id: number) => pipelineApi.deleteReferral(id), onSuccess: deleted });
  const remove = useMutation({ mutationFn: () => pipelineApi.deleteContact(item.id), onSuccess: deleted });
  const error = status.error || dropReferral.error || remove.error;
  const details = [item.title, item.company].filter(Boolean).join(" at ");
  return (
    <Card className="mb-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold">{item.name}</h3>
          {details && <p className="text-sm text-muted">{details}</p>}
          <p className="text-sm">
            {item.email && <span className="mr-3">{item.email}</span>}
            {item.link && (
              <a href={item.link} target="_blank" rel="noopener noreferrer" className="text-brand underline">
                Profile
              </a>
            )}
          </p>
          {item.last_contacted && <p className="text-xs text-muted">Last spoke {dayLabel(item.last_contacted)}</p>}
          {item.interviewed_you_for.map((i) => (
            <p key={i.id} className="text-sm">
              Interviewed you for {i.label}, {dayLabel(i.when)}
            </p>
          ))}
          {item.notes && <p className="mt-1 whitespace-pre-wrap text-sm text-muted">{item.notes}</p>}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" small onClick={onEdit}>
            Edit
          </Button>
          <Button
            variant="danger"
            small
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(`Delete ${item.name} and their referrals?`)) remove.mutate();
            }}
          >
            Delete
          </Button>
        </div>
      </div>
      <div className="mt-3">
        <ReferralDraft contact={item} jobs={data.jobs} />
      </div>
      {item.referrals.length > 0 && (
        <ul className="mt-3 space-y-2 border-t border-border pt-3">
          {item.referrals.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <span>
                Referral for {r.job.role} at {r.job.company} {r.note && <span className="text-muted">· {r.note}</span>}
              </span>
              <span className="flex items-center gap-2">
                <Badge tone={r.status === "submitted" || r.status === "agreed" ? "good" : "muted"}>{r.status_label}</Badge>
                <select
                  aria-label={`Where the referral for ${r.job.company} stands`}
                  className="rounded-md border border-border bg-surface px-2 py-1 text-xs"
                  value={r.status}
                  disabled={status.isPending}
                  onChange={(e) => status.mutate({ id: r.id, status: e.target.value })}
                >
                  {data.referral_statuses.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
                <Button variant="ghost" small disabled={dropReferral.isPending} onClick={() => dropReferral.mutate(r.id)}>
                  Remove
                </Button>
              </span>
            </li>
          ))}
        </ul>
      )}
      {error && <p role="alert" className="mt-2 text-sm text-bad">{errorText(error)}</p>}
    </Card>
  );
}

export function Contacts() {
  const query = useQuery({ queryKey: KEY, queryFn: pipelineApi.contacts });
  const [editing, setEditing] = useState<number | null>(null);
  if (query.isPending) return <Loading what="your contacts" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load your contacts.")} onRetry={() => query.refetch()} />;
  const data = query.data;
  const editItem = data.contacts.find((c) => c.id === editing);
  return (
    <>
      <PageHeader title="Contacts and referrals" subtitle="People who can put in a word for you. StillOpen never contacts anyone: it only keeps your notes." />
      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <div>
          {data.contacts.length === 0 ? (
            <Card className="text-sm text-muted">No contacts yet. Add someone you know at a company you are applying to, then note if they could refer you.</Card>
          ) : (
            data.contacts.map((c) => <Person key={c.id} item={c} data={data} onEdit={() => setEditing(c.id)} />)
          )}
        </div>
        <aside className="space-y-4">
          <Card>
            <h2 className="mb-3 font-semibold">{editItem ? "Edit contact" : "Add a contact"}</h2>
            <ContactForm key={editItem?.id ?? "new"} item={editItem} onDone={() => setEditing(null)} />
            {editItem && (
              <Button variant="ghost" small className="mt-2" onClick={() => setEditing(null)}>
                Cancel editing
              </Button>
            )}
          </Card>
          <Card>
            <h2 className="mb-3 font-semibold">Add a referral</h2>
            {data.contacts.length === 0 || data.jobs.length === 0 ? (
              <Notice>Add a contact, and a job to your tracker, to note a referral.</Notice>
            ) : (
              <ReferralForm data={data} contacts={data.contacts} />
            )}
          </Card>
        </aside>
      </div>
    </>
  );
}
