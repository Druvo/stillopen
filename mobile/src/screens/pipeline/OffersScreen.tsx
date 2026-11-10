import React, { useState } from "react";
import { TouchableOpacity, View } from "react-native";

import { pipelineApi, type Offer, type OfferList, type OfferNote, type OfferValues } from "../../api/pipeline";
import { Badge, Button, Card, confirm, Empty, ErrorBox, Field, Ionicons, Loading, Muted, notify, Row, Screen, Select, SectionTitle, Text, useTheme } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";
import { canCompare, compareHint, dayLabel, formatMoney, messageText, toggleOffer } from "./logic";
import { CopyButton, DateField, FormSheet, SuggestMove, type Suggestion } from "./parts";

const MONEY: { key: "bonus" | "equity" | "other_benefits" | "signing"; label: string; hint?: string }[] = [
  { key: "bonus", label: "Yearly bonus" },
  { key: "equity", label: "Yearly value of shares or options" },
  { key: "other_benefits", label: "Other yearly benefits worth counting", hint: "Allowances, insurance, pension match: only what you would otherwise pay for." },
  { key: "signing", label: "One-off signing bonus" },
];

function OfferForm({ data, item, onDone, onSuggest }: { data: OfferList; item?: Offer; onDone: () => void; onSuggest: (s: Suggestion) => void }) {
  const act = useAction();
  const [v, setV] = useState<OfferValues>({
    application: item ? String(item.job.id) : "",
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
  const f = act.fields ?? {};
  return (
    <View>
      <Select label="Job" value={v.application || null} onChange={(x) => setV({ ...v, application: String(x) })} options={data.jobs.map((j) => ({ value: String(j.id), label: j.label }))} placeholder="Pick a job…" />
      {f.application ? <Text style={{ marginBottom: 10 }}>{f.application}</Text> : null}
      <Field label="Base pay" value={v.base} onChangeText={(x) => setV({ ...v, base: x })} keyboardType="decimal-pad" error={f.base} />
      <Select label="Base pay is" value={v.period} onChange={(x) => setV({ ...v, period: String(x) })} options={data.periods.map((p) => ({ value: p.value, label: p.label }))} />
      <Field label="Currency" value={v.currency} onChangeText={(x) => setV({ ...v, currency: x.toUpperCase() })} maxLength={3} autoCapitalize="characters" hint="Three letters, e.g. USD, BDT, MYR, AED." error={f.currency} />
      {MONEY.map((m) => (
        <Field key={m.key} label={m.label} hint={m.hint} value={v[m.key]} onChangeText={(x) => setV({ ...v, [m.key]: x })} keyboardType="decimal-pad" error={f[m.key]} />
      ))}
      <DateField label="Reply by" value={v.deadline} onChange={(x) => setV({ ...v, deadline: x })} clearable error={f.deadline} />
      <Field label="Notes" value={v.notes} onChangeText={(x) => setV({ ...v, notes: x })} multiline maxLength={2000} error={f.notes} />
      {act.error && !act.fields ? <ErrorBox message={act.error} /> : null}
      <Button
        label={item ? "Save changes" : "Add offer"}
        busy={act.busy}
        onPress={async () => {
          const saved = await act.run(() => (item ? pipelineApi.editOffer(item.id, v) : pipelineApi.addOffer(v)));
          if (!saved) return;
          if (saved.suggest_status) onSuggest({ jobId: Number(v.application), status: saved.suggest_status });
          notify("Offer saved.");
          onDone();
        }}
      />
    </View>
  );
}

function Line({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ width: "50%", marginBottom: 6 }}>
      <Muted>{label}</Muted>
      <Text>{value}</Text>
    </View>
  );
}

/** "Compare these offers in words": differences per currency (never converted), what to ask, and an optional counter-offer note. Nothing saved or sent. */
function CompareInWords({ offers, selected, onClear }: { offers: Offer[]; selected: number[]; onClear: () => void }) {
  const act = useAction();
  const chosen = offers.filter((o) => selected.includes(o.id));
  const [focus, setFocus] = useState<number | null>(null);
  const [note, setNote] = useState<OfferNote | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const run = async () => {
    const r = await act.run(() => pipelineApi.compareOffers(selected, focus && selected.includes(focus) ? focus : null));
    if (r) {
      setNote(r);
      setSubject(r.counter_note?.subject ?? "");
      setBody(r.counter_note?.body ?? "");
    }
  };
  return (
    <Card>
      <Text style={{ fontWeight: "700", marginBottom: 4 }}>Compare these offers in words</Text>
      <Muted style={{ marginBottom: 10 }}>{compareHint(selected.length)} Offers in different currencies are compared within each currency and never converted.</Muted>
      {chosen.length >= 2 ? (
        <Select
          label="If you want a counter-offer note, it is about"
          value={focus ?? chosen[0].id}
          onChange={(x) => setFocus(Number(x))}
          options={chosen.map((o) => ({ value: o.id, label: `${o.job.company} - ${o.job.role}` }))}
        />
      ) : null}
      <Row style={{ flexWrap: "wrap" }}>
        <Button label="Compare in words" busy={act.busy} disabled={!canCompare(selected)} onPress={run} />
        {selected.length > 0 ? <Button label="Clear ticks" variant="ghost" onPress={onClear} /> : null}
      </Row>
      {act.error ? <ErrorBox message={act.error} /> : null}
      {note ? (
        <View style={{ marginTop: 14 }}>
          <Text style={{ fontWeight: "700", marginBottom: 4 }}>The differences</Text>
          {note.differences.map((d) => (
            <View key={d.currency} style={{ marginBottom: 8 }}>
              <Text style={{ fontWeight: "600" }}>In {d.currency}</Text>
              {d.lines.map((l) => (
                <Text key={l}>• {l}</Text>
              ))}
            </View>
          ))}
          <Text style={{ fontWeight: "700", marginBottom: 4, marginTop: 6 }}>What to ask about</Text>
          {note.ask_about.map((a) => (
            <Text key={a}>• {a}</Text>
          ))}
          <Text style={{ fontWeight: "700", marginBottom: 4, marginTop: 10 }}>A counter-offer note</Text>
          {!note.ai ? <Muted>Set up your own AI in Profile to get a draft counter-offer note.</Muted> : null}
          {note.counter_note ? (
            <View>
              <Field label="Subject" value={subject} onChangeText={setSubject} />
              <Field label="Message" value={body} onChangeText={setBody} multiline />
              {note.counter_note.flagged_count > 0 ? (
                <Muted style={{ marginBottom: 8 }}>The AI added things you did not give it: {note.counter_note.flagged.map((x) => x.text).join(", ")}. Remove them unless they are true.</Muted>
              ) : null}
              <CopyButton text={messageText({ subject, body })} label="Copy the note" />
              <Muted style={{ marginTop: 8 }}>It names no figure you did not enter. It is never sent for you.</Muted>
              {note.notice ? <Muted>{note.notice}</Muted> : null}
            </View>
          ) : null}
        </View>
      ) : null}
    </Card>
  );
}

export default function OffersScreen() {
  const { colors } = useTheme();
  const load = useLoad(() => pipelineApi.offers());
  const act = useAction();
  const [editing, setEditing] = useState<Offer | "new" | null>(null);
  const [suggest, setSuggest] = useState<Suggestion | null>(null);
  const [ticked, setTicked] = useState<number[]>([]);
  const data = load.data;
  return (
    <Screen title="Offers" onRefresh={load.refresh} refreshing={load.refreshing}>
      {load.loading ? <Loading /> : load.error && !data ? <ErrorBox message={load.error} onRetry={load.reload} /> : null}
      {data ? (
        <>
          <Muted style={{ marginBottom: 12 }}>
            Put each offer in plain numbers and see them side by side. The yearly total counts base pay, bonus, shares and benefits you would otherwise pay for; a one-off signing bonus is shown separately. Offers in different currencies are never converted for you, so each currency is compared on its own. Declined offers drop out of the comparison.
          </Muted>
          <Button label="Record an offer" onPress={() => setEditing("new")} />
          {suggest ? (
            <View style={{ marginTop: 12 }}>
              <SuggestMove suggestion={suggest} onDone={() => setSuggest(null)} />
            </View>
          ) : null}
          {act.error ? <Text style={{ color: colors.danger, marginTop: 8 }}>{act.error}</Text> : null}

          {data.groups.map((g) => (
            <View key={g.currency}>
              <SectionTitle>Compared in {g.currency}</SectionTitle>
              <Muted style={{ marginBottom: 8 }}>Best yearly total first. The signing bonus is one-off, so it is left out of the yearly total.</Muted>
              {g.rows.map(({ offer, behind, best }) => (
                <Card key={offer.id}>
                  <Row style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontWeight: "700" }}>
                        {offer.job.company} - {offer.job.role}
                      </Text>
                      <Text style={{ fontSize: 20, fontWeight: "700", marginTop: 2 }}>{formatMoney(offer.yearly_total, offer.currency)} a year</Text>
                      {Number(behind) > 0 ? <Muted>{formatMoney(behind, offer.currency)} less than the highest</Muted> : null}
                    </View>
                    <View style={{ gap: 6, alignItems: "flex-end" }}>
                      {best ? <Badge label="highest" color={colors.good} /> : null}
                      <Badge label={offer.status_label} color={colors.textMuted} />
                    </View>
                  </Row>
                  <View style={{ flexDirection: "row", flexWrap: "wrap", marginTop: 10 }}>
                    <Line label="Base per year" value={formatMoney(offer.yearly_base, offer.currency)} />
                    <Line label="Bonus" value={formatMoney(offer.bonus, offer.currency)} />
                    <Line label="Shares" value={formatMoney(offer.equity, offer.currency)} />
                    <Line label="Benefits" value={formatMoney(offer.other_benefits, offer.currency)} />
                    <Line label="Signing (one-off)" value={formatMoney(offer.signing, offer.currency)} />
                    <Line label="Reply by" value={offer.deadline ? dayLabel(offer.deadline) : "-"} />
                  </View>
                  {offer.notes ? <Muted>{offer.notes}</Muted> : null}
                </Card>
              ))}
            </View>
          ))}

          {data.offers.length >= 2 ? (
            <>
              <SectionTitle>Compare in words</SectionTitle>
              <CompareInWords offers={data.offers} selected={ticked} onClear={() => setTicked([])} />
            </>
          ) : null}

          <SectionTitle>All offers</SectionTitle>
          {data.offers.length === 0 ? (
            <Empty
              title="No offers yet"
              hint="When one arrives, record it here to compare it with the others and keep its reply-by date in view."
              action={data.jobs.length > 0 ? { label: "Record an offer", onPress: () => setEditing("new") } : undefined}
            />
          ) : (
            data.offers.map((o) => (
              <Card key={o.id}>
                <Row style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontWeight: "700" }}>
                      {o.job.company} - {o.job.role}
                    </Text>
                    <Text style={{ marginTop: 4 }}>
                      Base {formatMoney(o.base, o.currency)} {o.period_label} · bonus {formatMoney(o.bonus, o.currency)} · shares {formatMoney(o.equity, o.currency)} · other {formatMoney(o.other_benefits, o.currency)} · signing {formatMoney(o.signing, o.currency)}
                    </Text>
                    <Muted>
                      First year {formatMoney(o.first_year_total, o.currency)}
                      {o.deadline ? ` · reply by ${dayLabel(o.deadline)}` : ""}
                    </Muted>
                    {o.notes ? <Muted style={{ marginTop: 4 }}>{o.notes}</Muted> : null}
                  </View>
                  <Badge label={o.status_label} color={o.status === "accepted" ? colors.good : o.status === "declined" ? colors.danger : colors.textMuted} />
                </Row>
                <View style={{ marginTop: 12 }}>
                  <Select
                    label="Decision"
                    value={o.status}
                    onChange={async (s) => {
                      if (await act.run(() => pipelineApi.offerStatus(o.id, String(s)))) load.reload();
                    }}
                    options={data.statuses.map((s) => ({ value: s.value, label: s.label }))}
                  />
                </View>
                {data.offers.length >= 2 ? (
                  <TouchableOpacity
                    onPress={() => setTicked((t) => toggleOffer(t, o.id))}
                    accessibilityRole="checkbox"
                    accessibilityState={{ checked: ticked.includes(o.id) }}
                    accessibilityLabel={`Compare the offer from ${o.job.company}`}
                    style={{ flexDirection: "row", alignItems: "center", gap: 10, minHeight: 44 }}
                  >
                    <Ionicons name={ticked.includes(o.id) ? "checkbox" : "square-outline"} size={22} color={ticked.includes(o.id) ? colors.accent : colors.textMuted} />
                    <Text>Compare</Text>
                  </TouchableOpacity>
                ) : null}
                <Row style={{ marginTop: 6 }}>
                  <Button label="Edit" variant="secondary" onPress={() => setEditing(o)} />
                  <Button
                    label="Delete"
                    variant="danger"
                    onPress={async () => {
                      if (!(await confirm("Delete this offer?"))) return;
                      if (await act.run(() => pipelineApi.deleteOffer(o.id))) {
                        notify("Deleted.");
                        setTicked((t) => t.filter((x) => x !== o.id));
                        load.reload();
                      }
                    }}
                  />
                </Row>
              </Card>
            ))
          )}
          <FormSheet visible={editing !== null} title={editing && editing !== "new" ? "Edit offer" : "Record an offer"} onClose={() => setEditing(null)}>
            {data.jobs.length === 0 && editing === "new" ? (
              <Empty title="No jobs yet" hint="Add a job to your tracker first, then record its offer." />
            ) : editing ? (
              <OfferForm
                key={editing === "new" ? "new" : editing.id}
                data={data}
                item={editing === "new" ? undefined : editing}
                onSuggest={setSuggest}
                onDone={() => {
                  setEditing(null);
                  load.reload();
                }}
              />
            ) : null}
          </FormSheet>
        </>
      ) : null}
    </Screen>
  );
}
