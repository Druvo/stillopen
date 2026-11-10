// Where we look for jobs: the person's own company boards and careers pages, and why a place might be empty.
import { useRouter, type Href } from "expo-router";
import React, { useState } from "react";
import { View } from "react-native";

import { sourcesApi, type Coverage, type CoverageArea, type CoverageSearch } from "../../api/jobs";
import { Badge, Body, Button, Card, ErrorBox, Field, Loading, Muted, Screen, SectionTitle, Select, Text, confirm, notify, useTheme } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";
import { sourceHealthText, troubleLine } from "./logic";

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

function countText(area: CoverageArea, days: number): string {
  if (!area.known) return "We could not tell which country this is, so we cannot count jobs there.";
  if (area.postings === 0) return `No jobs listed in the last ${days} days.`;
  return `${plural(area.postings, "job")} listed in the last ${days} days, from ${plural(area.boards, "job source")}.`;
}
function searchText(s: CoverageSearch): string {
  if (s.reason === "needs_key") return `${s.connector_label}: switched off until the site owner adds a free key`;
  if (s.reason === "needs_roles") return `${s.connector_label}: add the roles you want in your profile to use it`;
  return `${s.connector_label}: searches here with your next job search`;
}
const LEVEL = { none: "No jobs yet", thin: "A few jobs", ok: "Well covered", unknown: "Not checked" } as const;

function CoverageCard() {
  const { colors } = useTheme();
  const router = useRouter();
  const { data, error, loading } = useLoad<Coverage>(() => sourcesApi.coverage(), []);
  const tone = { none: colors.danger, thin: colors.warn, ok: colors.good, unknown: colors.textMuted } as const;
  return (
    <Card>
      <Text style={{ fontWeight: "700", marginBottom: 4 }}>Where we find jobs for you</Text>
      {loading ? <Muted>Checking your places…</Muted> : null}
      {error ? <Muted>{error}</Muted> : null}
      {data && !data.has_areas ? (
        <>
          <Muted>Tell us where you would work and we will show how many jobs each place has.</Muted>
          <Button label="Add a place in Profile" variant="secondary" onPress={() => router.push("/profile" as Href)} style={{ marginTop: 8 }} />
        </>
      ) : null}
      {data?.has_areas ? (
        <>
          <Muted style={{ marginBottom: 8 }}>For each place you would work in: the jobs our sources listed in the last {data.days} days, and what is searching there.</Muted>
          {data.areas.map((a) => (
            <View key={a.id} style={{ marginBottom: 10 }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                <Text style={{ fontWeight: "600", flex: 1 }}>{a.label}</Text>
                <Badge label={LEVEL[a.level]} color={tone[a.level]} />
              </View>
              <Body>{countText(a, data.days)}</Body>
              {a.searches.map((s) => (
                <Muted key={s.name}>• {searchText(s)}</Muted>
              ))}
              {a.tip ? <Text style={{ fontWeight: "600", marginTop: 4 }}>{a.tip}</Text> : null}
            </View>
          ))}
        </>
      ) : null}
    </Card>
  );
}

export default function SourcesScreen() {
  const { colors } = useTheme();
  const { data, error, loading, refreshing, refresh, reload } = useLoad(() => sourcesApi.sources(), []);
  const [connector, setConnector] = useState("");
  const [token, setToken] = useState("");
  const [name, setName] = useState("");
  const [pageUrl, setPageUrl] = useState("");
  const [pageName, setPageName] = useState("");
  const [done, setDone] = useState("");
  const [info, setInfo] = useState("");
  const addForm = useAction();
  const pageForm = useAction();
  const row = useAction();

  if (loading) {
    return (
      <Screen title="Where we look for jobs">
        <Loading />
      </Screen>
    );
  }
  if (error || !data) {
    return (
      <Screen title="Where we look for jobs" onRefresh={refresh} refreshing={refreshing}>
        <ErrorBox message={error ?? "We could not load your job sources."} onRetry={reload} />
      </Screen>
    );
  }
  const chosen = connector || data.connectors[0]?.value || "";
  const trouble = troubleLine(data.trouble);
  const sharedTrouble = (data.shared_health ?? []).filter((s) => s.health.state === "error");

  const report = (r: { message: string; info: string } | undefined) => {
    if (!r) return false;
    setInfo(r.info);
    setDone(r.info ? "" : r.message);
    return !r.info;
  };
  const addCompany = async () => {
    setDone("");
    setInfo("");
    if (report(await addForm.run(() => sourcesApi.add({ connector: chosen, board_token: token, name })))) {
      setToken("");
      setName("");
      await reload();
    }
  };
  const addPage = async () => {
    setDone("");
    setInfo("");
    if (report(await pageForm.run(() => sourcesApi.addCareerPage({ url: pageUrl, name: pageName })))) {
      setPageUrl("");
      setPageName("");
      await reload();
    }
  };

  return (
    <Screen title="Where we look for jobs" onRefresh={refresh} refreshing={refreshing}>
      <Muted style={{ marginBottom: 12 }}>
        You do not need to set anything up. We already search {data.shared.length} job sources for you automatically, whenever you open your dashboard. Add a company below only if you want one we do not cover. Your own list is private to you.
      </Muted>
      {trouble ? <Card><Body>{trouble} A board that does not answer is skipped for now and tried again at your next search; nothing is lost.</Body></Card> : null}
      {done ? <Text style={{ color: colors.good, marginBottom: 8 }}>{done}</Text> : null}
      {info ? <Text style={{ marginBottom: 8 }}>{info}</Text> : null}

      <CoverageCard />

      <SectionTitle>Add a company</SectionTitle>
      <Card>
        <Select label="Which hiring system does the company use?" options={data.connectors} value={chosen} onChange={setConnector} />
        {data.help.connector ? <Muted style={{ marginTop: -8, marginBottom: 12 }}>{data.help.connector}</Muted> : null}
        <Field
          label="The company's name in that address, or paste the careers page address"
          value={token}
          onChangeText={setToken}
          hint={data.help.board_token}
          error={addForm.fields?.board_token}
          autoCapitalize="none"
          autoCorrect={false}
        />
        <Field label="Company name (optional)" value={name} onChangeText={setName} hint="Shown in your search log. Defaults to the name from the address." error={addForm.fields?.name} />
        {addForm.error && !addForm.fields ? <Text style={{ color: colors.danger, marginBottom: 10 }}>{addForm.error}</Text> : null}
        <Button label="Check and add" busy={addForm.busy} disabled={!token.trim()} onPress={addCompany} />
        <Muted style={{ marginTop: 6 }}>We read that company's public job list once to make sure it works. You can have up to {data.limit}.</Muted>
      </Card>

      <SectionTitle>Add a company's careers page</SectionTitle>
      <Card>
        <Muted style={{ marginBottom: 8 }}>
          Many companies list their openings on their own website. Paste the address of the page that lists them and we will read it the way a search engine does, obeying its robots.txt and never logging in.
        </Muted>
        <Field label="Address of the careers page" value={pageUrl} onChangeText={setPageUrl} placeholder="https://" autoCapitalize="none" keyboardType="url" error={pageForm.fields?.board_token} />
        <Field label="Company name (optional)" value={pageName} onChangeText={setPageName} error={pageForm.fields?.name} />
        {pageForm.error && !pageForm.fields ? <Text style={{ color: colors.danger, marginBottom: 10 }}>{pageForm.error}</Text> : null}
        <Button label="Check and add" busy={pageForm.busy} disabled={!pageUrl.trim()} onPress={addPage} />
        <Muted style={{ marginTop: 6 }}>If we cannot find a list of openings, paste single job links into Add a job instead.</Muted>
      </Card>

      <SectionTitle>Your companies</SectionTitle>
      {row.error ? <Text style={{ color: colors.danger, marginBottom: 8 }}>{row.error}</Text> : null}
      {data.mine.length === 0 ? <Muted>None yet. Add a company whose careers page you check often.</Muted> : null}
      {data.mine.map((s) => (
        <Card key={s.id}>
          <View style={{ flexDirection: "row", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <Text style={{ fontWeight: "700" }}>{s.name}</Text>
            {!s.enabled ? <Badge label="paused" color={colors.warn} /> : null}
          </View>
          <Muted>{s.connector === "careerpage" ? `Careers page on ${s.host || s.board_token}` : `${s.connector_label} · ${s.board_token}`}</Muted>
          {s.health ? <Text style={{ color: s.health.state === "error" ? colors.danger : colors.textMuted, marginTop: 2 }}>{sourceHealthText(s.health)}</Text> : null}
          <View style={{ flexDirection: "row", gap: 8, marginTop: 10 }}>
            <Button
              label={s.enabled ? "Pause" : "Resume"}
              variant="secondary"
              disabled={row.busy}
              onPress={async () => {
                if (await row.run(() => sourcesApi.toggle(s.id))) await reload();
              }}
            />
            <Button
              label="Remove"
              variant="danger"
              disabled={row.busy}
              onPress={async () => {
                if (!(await confirm("Remove this company from your searches?", s.name, "Remove"))) return;
                if (await row.run(() => sourcesApi.remove(s.id))) {
                  notify("Removed.");
                  await reload();
                }
              }}
            />
          </View>
        </Card>
      ))}

      {sharedTrouble.length > 0 ? (
        <>
          <SectionTitle>Not answering right now</SectionTitle>
          {sharedTrouble.map((s) => (
            <Body key={s.name}>
              {s.name}: {sourceHealthText(s.health)}
            </Body>
          ))}
          <Muted style={{ marginTop: 4 }}>These are searched for everyone, so only the site's owner can change them.</Muted>
        </>
      ) : null}
      {data.shared.length > 0 ? <Muted style={{ marginTop: 14 }}>Already searched for everyone ({data.shared.length}): {data.shared.join(", ")}</Muted> : null}
    </Screen>
  );
}
