"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, ErrorBox, Loading, Notice, PageHeader } from "@/components/ui";
import { FormError, SelectField, TextAreaField, TextField, useSubmit } from "@/components/form";
import { errorText } from "@/lib/api";
import { notify } from "@/lib/toast";
import { pipelineApi, type Offer, type OfferList, type OfferValues } from "./api";
import { dayLabel, formatMoney, jobFromSearch } from "./logic";
import { SuggestMove, type Suggestion } from "./suggest";
import { CompareInWords } from "./compare";
import { toggleOffer } from "./compare-logic";

const KEY = ["pipeline", "offers"] as const;

function Line({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function OfferForm({ data, item, defaultJob, onDone, onSuggest }: { data: OfferList; item?: Offer; defaultJob: string; onDone: () => void; onSuggest: (s: Suggestion) => void }) {
  const client = useQueryClient();
  const form = useSubmit();
  const [v, setV] = useState<OfferValues>({
    application: item ? String(item.job.id) : defaultJob,
    base: item?.base ?? "",
    period: item?.period ?? "year",
    currency: item?.currency ?? "USD",
    bonus: item?.bonus ?? "0",
    equity: item?.equity ?? "0",
    other_benefits: item?.other_benefits ?? "0",
    signing: item?.signing ?? "0",
    deadline: item?.deadline ?? "",
    notes: item?.notes ?? "",
  });
  const set = (name: keyof OfferValues) => (e: { target: { value: string } }) => setV({ ...v, [name]: e.target.value });
  const submit = form.handle(async () => {
    const saved = item ? await pipelineApi.editOffer(item.id, v) : await pipelineApi.addOffer(v);
    if (saved.suggest_status) onSuggest({ jobId: Number(v.application), status: saved.suggest_status });
    await client.invalidateQueries({ queryKey: KEY });
    notify("Offer saved.");
    if (!item) setV({ ...v, base: "", bonus: "0", equity: "0", other_benefits: "0", signing: "0", deadline: "", notes: "" });
    onDone();
  });
  const money = (name: "base" | "bonus" | "equity" | "other_benefits" | "signing", label: string, hint?: string) => (
    <TextField label={label} hint={hint} type="number" min="0" step="0.01" inputMode="decimal" value={v[name]} onChange={set(name)} errors={form.fields[name]} />
  );
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
      {money("base", "Base pay")}
      <SelectField label="Base pay is" value={v.period} onChange={set("period")} errors={form.fields.period}>
        {data.periods.map((p) => (
          <option key={p.value} value={p.value}>
            {p.label}
          </option>
        ))}
      </SelectField>
      <TextField label="Currency" value={v.currency} onChange={set("currency")} errors={form.fields.currency} maxLength={3} hint="Three letters, e.g. USD, BDT, MYR, AED." />
      {money("bonus", "Yearly bonus")}
      {money("equity", "Yearly value of shares or options")}
      {money("other_benefits", "Other yearly benefits worth counting", "Allowances, insurance, pension match: only what you would otherwise pay for.")}
      {money("signing", "One-off signing bonus")}
      <TextField label="Reply by" type="date" value={v.deadline} onChange={set("deadline")} errors={form.fields.deadline} />
      <TextAreaField label="Notes" rows={2} value={v.notes} onChange={set("notes")} errors={form.fields.notes} maxLength={2000} />
      <FormError message={form.error} />
      <Button type="submit" disabled={form.busy}>
        {form.busy ? "Saving…" : item ? "Save changes" : "Add offer"}
      </Button>
    </form>
  );
}

export function Offers() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: KEY, queryFn: pipelineApi.offers });
  const [editing, setEditing] = useState<number | null>(null);
  const [suggest, setSuggest] = useState<Suggestion | null>(null);
  const [ticked, setTicked] = useState<number[]>([]);
  const refresh = () => client.invalidateQueries({ queryKey: KEY });
  const status = useMutation({ mutationFn: (a: { id: number; status: string }) => pipelineApi.offerStatus(a.id, a.status), onSuccess: refresh });
  const remove = useMutation({
    mutationFn: (id: number) => pipelineApi.deleteOffer(id),
    onSuccess: () => {
      notify("Deleted.");
      return refresh();
    },
  });
  if (query.isPending) return <Loading what="your offers" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load your offers.")} onRetry={() => query.refetch()} />;
  const data = query.data;
  const editItem = data.offers.find((o) => o.id === editing);
  const error = status.error || remove.error;
  return (
    <>
      <PageHeader title="Offers" subtitle="Put each offer in plain numbers and see them side by side." />
      <p className="mb-4 text-sm text-muted">
        The yearly total counts base pay, bonus, shares and benefits you would otherwise pay for; a one-off signing bonus is shown separately. Offers in different currencies are never converted for you, so each currency is compared on its
        own. Declined offers drop out of the comparison.
      </p>
      {suggest && (
        <div className="mb-4">
          <SuggestMove suggestion={suggest} onDone={() => setSuggest(null)} />
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <div>
          {error && <Notice tone="error">{errorText(error)}</Notice>}
          {data.groups.map((g) => (
            <section key={g.currency} className="mb-6" aria-label={`Offers in ${g.currency}`}>
              <h2 className="mb-2 font-semibold">Compared in {g.currency}</h2>
              <p className="mb-2 text-xs text-muted">Best yearly total first. The signing bonus is one-off, so it is left out of the yearly total.</p>
              {g.rows.map(({ offer, behind, best }) => (
                <Card key={offer.id} className="mb-2 text-sm">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <strong>
                        {offer.job.company} - {offer.job.role}
                      </strong>{" "}
                      {best && <Badge tone="good">highest</Badge>}
                      <p className="text-lg font-semibold">{formatMoney(offer.yearly_total, offer.currency)} a year</p>
                      {Number(behind) > 0 && <p className="text-muted">{formatMoney(behind, offer.currency)} less than the highest</p>}
                    </div>
                    <Badge>{offer.status_label}</Badge>
                  </div>
                  <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3">
                    <Line label="Base per year" value={formatMoney(offer.yearly_base, offer.currency)} />
                    <Line label="Bonus" value={formatMoney(offer.bonus, offer.currency)} />
                    <Line label="Shares" value={formatMoney(offer.equity, offer.currency)} />
                    <Line label="Benefits" value={formatMoney(offer.other_benefits, offer.currency)} />
                    <Line label="Signing (one-off)" value={formatMoney(offer.signing, offer.currency)} />
                    <Line label="Reply by" value={offer.deadline ? dayLabel(offer.deadline) : "—"} />
                  </dl>
                  {offer.notes && <p className="mt-2 whitespace-pre-wrap text-muted">{offer.notes}</p>}
                </Card>
              ))}
            </section>
          ))}
          {data.offers.length >= 2 && <CompareInWords offers={data.offers} selected={ticked} onClear={() => setTicked([])} />}
          <h2 className="mb-2 font-semibold">All offers</h2>
          {data.offers.length === 0 ? (
            <Card className="text-sm text-muted">No offers yet. When one arrives, record it here to compare it with the others and keep its reply-by date in view. Declined offers drop out of the comparison.</Card>
          ) : (
            data.offers.map((o) => (
              <Card key={o.id} className="mb-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <h3 className="font-semibold">
                      {o.job.company} - {o.job.role}
                    </h3>
                    <p className="text-sm">
                      Base {formatMoney(o.base, o.currency)} {o.period_label} · bonus {formatMoney(o.bonus, o.currency)} · shares {formatMoney(o.equity, o.currency)} · other{" "}
                      {formatMoney(o.other_benefits, o.currency)} · signing {formatMoney(o.signing, o.currency)}
                    </p>
                    <p className="text-sm text-muted">
                      First year {formatMoney(o.first_year_total, o.currency)}
                      {o.deadline && ` · reply by ${dayLabel(o.deadline)}`}
                    </p>
                    {o.notes && <p className="mt-1 whitespace-pre-wrap text-sm text-muted">{o.notes}</p>}
                  </div>
                  <Badge tone={o.status === "accepted" ? "good" : o.status === "declined" ? "bad" : "muted"}>{o.status_label}</Badge>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <label className="text-sm">
                    <span className="mr-1 text-muted">Decision</span>
                    <select
                      className="rounded-md border border-border bg-surface px-2 py-1 text-sm"
                      value={o.status}
                      disabled={status.isPending}
                      onChange={(e) => status.mutate({ id: o.id, status: e.target.value })}
                    >
                      {data.statuses.map((s) => (
                        <option key={s.value} value={s.value}>
                          {s.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  {data.offers.length >= 2 && (
                    <label className="flex min-h-11 items-center gap-1 text-sm sm:min-h-6">
                      <input type="checkbox" checked={ticked.includes(o.id)} onChange={() => setTicked((t) => toggleOffer(t, o.id))} aria-label={`Compare the offer from ${o.job.company}`} />
                      <span>Compare</span>
                    </label>
                  )}
                  <Button variant="outline" small onClick={() => setEditing(o.id)}>
                    Edit
                  </Button>
                  <Button
                    variant="danger"
                    small
                    disabled={remove.isPending}
                    onClick={() => {
                      if (window.confirm("Delete this offer?")) remove.mutate(o.id);
                    }}
                  >
                    Delete
                  </Button>
                </div>
              </Card>
            ))
          )}
        </div>
        <aside>
          <Card>
            <h2 className="mb-3 font-semibold">{editItem ? "Edit offer" : "Record an offer"}</h2>
            {data.jobs.length === 0 ? (
              <Notice>Add a job to your tracker first, then record its offer.</Notice>
            ) : (
              <OfferForm key={editItem?.id ?? "new"} data={data} item={editItem} defaultJob={jobFromSearch(window.location.search, data.jobs)} onDone={() => setEditing(null)} onSuggest={setSuggest} />
            )}
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
