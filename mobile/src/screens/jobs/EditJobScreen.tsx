// Correct anything about a job: company, link, place, kind of role, description, notes.
import { useLocalSearchParams, useRouter, type Href } from "expo-router";
import React, { useEffect, useState } from "react";
import { View } from "react-native";

import { jobsApi, type JobDetails } from "../../api/jobs";
import { DateField } from "../../components/jobs/DateField";
import { FitList } from "../../components/jobs/MatchCard";
import { Body, Button, Card, ErrorBox, Field, Loading, Muted, Screen, SectionTitle, Select, Text, useTheme } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";

const SELECTS = ["arrangement", "sponsorship", "relocation", "employment_type", "seniority"] as const;
const SELECT_LABELS: Record<(typeof SELECTS)[number], string> = {
  arrangement: "Where the work is done",
  sponsorship: "Visa sponsorship",
  relocation: "Relocation help",
  employment_type: "Kind of contract",
  seniority: "Level",
};

export default function EditJobScreen() {
  const { id: idParam } = useLocalSearchParams<{ id: string }>();
  const id = Number(idParam);
  const router = useRouter();
  const { colors } = useTheme();
  const { data, error, loading, refreshing, refresh, reload, setData } = useLoad(() => jobsApi.details(id), [id]);
  const [values, setValues] = useState<Record<string, string> | null>(null);
  const save = useAction();
  const reread = useAction();
  const translate = useAction();
  const [translated, setTranslated] = useState("");
  const [canTranslate, setCanTranslate] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (data && values === null) setValues(data.values);
  }, [data, values]);
  useEffect(() => {
    jobsApi.me().then((m) => setCanTranslate(!!m.translate_enabled)).catch(() => undefined);
  }, []);

  if (loading || (data && !values)) {
    return (
      <Screen title="Edit details">
        <Loading />
      </Screen>
    );
  }
  if (error || !data || !values) {
    return (
      <Screen title="Edit details" onRefresh={refresh} refreshing={refreshing}>
        <ErrorBox message={error ?? "We could not load this job."} onRetry={reload} />
      </Screen>
    );
  }
  const set = (name: string) => (v: string) => setValues((s) => ({ ...(s ?? {}), [name]: v }));
  const accept = (next: JobDetails) => {
    setData(next);
    setValues(next.values);
  };
  const doSave = async () => {
    setNotice("");
    const r = await save.run(() => jobsApi.saveDetails(id, values));
    if (r) {
      accept(r);
      setNotice("Saved.");
    }
  };
  const doReread = async () => {
    setNotice("");
    const r = await reread.run(() => jobsApi.redetect(id));
    if (r) {
      accept(r);
      setNotice("Re-read the posting." + (r.changed.length ? ` Updated: ${r.changed.join(", ").replaceAll("_", " ")}.` : " Nothing to change."));
    }
  };
  const doTranslate = async () => {
    const r = await translate.run(() => jobsApi.translate(id));
    if (r) setTranslated(r.translated);
  };
  const f = save.fields;

  return (
    <Screen title="Edit details" onRefresh={refresh} refreshing={refreshing}>
      <Text style={{ fontSize: 20, fontWeight: "700" }}>{data.company}</Text>
      <Muted style={{ marginBottom: 12 }}>{data.role}. Correct anything below. Where it is and what kind of role it is decides whether it fits what you are looking for.</Muted>

      <Card>
        <Text style={{ fontWeight: "700", marginBottom: 6 }}>Fit with what you want</Text>
        <FitList checks={data.fit} empty="Nothing to check yet." />
        <Muted style={{ marginTop: 6 }}>Checked against your search areas in Profile. This only flags a job; it never hides one.</Muted>
        {data.credit ? <Muted style={{ marginTop: 4 }}>This job was found through {data.credit.label}.</Muted> : null}
      </Card>

      <SectionTitle>The job</SectionTitle>
      <Card>
        <Field label="Company" value={values.company} onChangeText={set("company")} error={f?.company} />
        <Field label="Role" value={values.role} onChangeText={set("role")} error={f?.role} />
        <Field label="Link to the posting" value={values.url} onChangeText={set("url")} error={f?.url} autoCapitalize="none" keyboardType="url" />
        <DateField label="Apply by (if it says)" value={values.deadline} onChange={set("deadline")} error={f?.deadline} />
        <Field label="Pay it advertises" value={values.advertised_pay} onChangeText={set("advertised_pay")} error={f?.advertised_pay} />
      </Card>

      <SectionTitle>Where it is and what kind of role</SectionTitle>
      <Card>
        {data.details_source === "detected" ? <Muted style={{ marginBottom: 8 }}>These were suggested by reading the posting. Check them and correct what is wrong.</Muted> : null}
        {data.details_source === "manual" ? <Muted style={{ marginBottom: 8 }}>You set these yourself.</Muted> : null}
        <Field label="Where it is" value={values.location_text} onChangeText={set("location_text")} error={f?.location_text} />
        <Field
          label="Country (where you must be based)"
          value={values.country}
          onChangeText={set("country")}
          error={f?.country}
          hint="A name like Malaysia or a code like MY. Leave blank if the posting does not say, or for remote work open worldwide."
        />
        {SELECTS.map((name) => (
          <Select key={name} label={SELECT_LABELS[name]} options={data.options[name].map((o) => ({ value: o.value, label: o.label }))} value={values[name] ?? ""} onChange={set(name)} />
        ))}
      </Card>

      <SectionTitle>Description and notes</SectionTitle>
      <Card>
        <Field label="The job description" value={values.description} onChangeText={set("description")} error={f?.description} multiline style={{ minHeight: 180 }} />
        {canTranslate ? (
          <View style={{ marginBottom: 14 }}>
            <Button label="Translate to English" variant="secondary" busy={translate.busy} onPress={doTranslate} />
            {translate.error ? <Text style={{ color: colors.danger, marginTop: 6 }}>{translate.error}</Text> : null}
            {translated ? (
              <View style={{ marginTop: 8 }}>
                <Muted>Machine translation, for reading only. It is not saved.</Muted>
                <Text selectable style={{ fontSize: 15, lineHeight: 22 }}>{translated}</Text>
              </View>
            ) : null}
          </View>
        ) : null}
        <Field label="Your own notes" value={values.notes} onChangeText={set("notes")} error={f?.notes} multiline />
        {save.error ? <Text style={{ color: colors.danger, marginBottom: 10 }}>{save.error}</Text> : null}
        {notice && !save.error ? <Text style={{ color: colors.good, marginBottom: 10 }}>{notice}</Text> : null}
        <Button label="Save" busy={save.busy} onPress={doSave} />
      </Card>

      <SectionTitle>Read the posting again</SectionTitle>
      <Card>
        <Muted style={{ marginBottom: 8 }}>Fills in the location, work arrangement, sponsorship, relocation, type and level from the description. Anything you set by hand is left alone. Save your changes first.</Muted>
        <Button label="Read it again" variant="secondary" busy={reread.busy} onPress={doReread} />
        {reread.error ? <Text style={{ color: colors.danger, marginTop: 6 }}>{reread.error}</Text> : null}
      </Card>
      <Button label="Back to the job" variant="ghost" onPress={() => (router.canGoBack() ? router.back() : router.replace(`/job/${id}` as Href))} style={{ marginTop: 8 }} />
    </Screen>
  );
}


