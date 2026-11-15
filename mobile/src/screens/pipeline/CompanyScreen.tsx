import * as Linking from "expo-linking";
import { useLocalSearchParams, useRouter, type Href } from "expo-router";
import React, { useEffect, useState } from "react";
import { TouchableOpacity, View } from "react-native";

import { pipelineApi, type CompanyPage } from "../../api/pipeline";
import { Badge, Button, Card, ErrorBox, Field, Ionicons, Loading, Muted, notify, Row, Screen, SectionTitle, Text, useTheme } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";

function openLink(url: string) {
  // Only an https address is ever opened; anything else stays as text.
  if (/^https:\/\//i.test(url)) Linking.openURL(url).catch(() => {});
}

function LinkLine({ label, href }: { label: string; href: string }) {
  const { colors } = useTheme();
  if (!href) return null;
  return (
    <TouchableOpacity onPress={() => openLink(href)} accessibilityRole="link" accessibilityLabel={`${label}: ${href}`} style={{ minHeight: 44, justifyContent: "center" }}>
      <Text style={{ color: colors.accent, fontWeight: "600" }}>{label}</Text>
      <Text style={{ color: colors.textMuted, fontSize: 12 }} numberOfLines={1}>
        {href}
      </Text>
    </TouchableOpacity>
  );
}

function Details({ page, onSaved }: { page: CompanyPage; onSaved: (p: CompanyPage) => void }) {
  const act = useAction();
  const [v, setV] = useState({ notes: page.notes, website: page.website, careers: page.careers, linkedin: page.linkedin });
  useEffect(() => setV({ notes: page.notes, website: page.website, careers: page.careers, linkedin: page.linkedin }), [page.notes, page.website, page.careers, page.linkedin]);
  const f = act.fields ?? {};
  return (
    <View>
      <Field label="Your notes" value={v.notes} onChangeText={(x) => setV({ ...v, notes: x })} multiline maxLength={4000} hint="What you learned, who said what, why you like it." />
      <Field label="Website" value={v.website} onChangeText={(x) => setV({ ...v, website: x })} keyboardType="url" autoCapitalize="none" error={f.website} hint="Starts with https://. StillOpen only keeps the address; the server never opens it." />
      <Field label="Careers page" value={v.careers} onChangeText={(x) => setV({ ...v, careers: x })} keyboardType="url" autoCapitalize="none" error={f.careers} />
      <Field label="LinkedIn page" value={v.linkedin} onChangeText={(x) => setV({ ...v, linkedin: x })} keyboardType="url" autoCapitalize="none" error={f.linkedin} />
      {act.error && !act.fields ? <ErrorBox message={act.error} /> : null}
      <Button
        label="Save details"
        busy={act.busy}
        onPress={async () => {
          const saved = await act.run(() => pipelineApi.editCompany(page.name, v));
          if (saved) {
            onSaved(saved);
            notify("Saved.");
          }
        }}
      />
    </View>
  );
}

export default function CompanyScreen() {
  const { name } = useLocalSearchParams<{ name: string }>();
  const router = useRouter();
  const { colors } = useTheme();
  const company = decodeURIComponent(String(name ?? ""));
  const load = useLoad(() => pipelineApi.company(company), [company]);
  const act = useAction();
  const page = load.data;
  return (
    <Screen title={page?.name ?? company} onRefresh={load.refresh} refreshing={load.refreshing}>
      {load.loading ? <Loading /> : load.error && !page ? <ErrorBox message={load.error} onRetry={load.reload} /> : null}
      {page ? (
        <>
          <Button
            label={page.watched ? "Watching" : "Watch this company"}
            variant={page.watched ? "primary" : "secondary"}
            icon={page.watched ? "star" : "star-outline"}
            busy={act.busy}
            onPress={async () => {
              const saved = await act.run(() => pipelineApi.editCompany(page.name, { watched: !page.watched }));
              if (saved) load.setData(saved);
            }}
          />
          {act.error ? <Text style={{ color: colors.danger, marginTop: 8 }}>{act.error}</Text> : null}
          {page.website || page.careers || page.linkedin ? (
            <Card style={{ marginTop: 12 }}>
              <LinkLine label="Website" href={page.website} />
              <LinkLine label="Careers" href={page.careers} />
              <LinkLine label="LinkedIn" href={page.linkedin} />
            </Card>
          ) : null}

          <SectionTitle>Jobs</SectionTitle>
          <Card>
            {page.jobs.length === 0 ? (
              <Muted>No jobs tracked here. Add one from the dashboard.</Muted>
            ) : (
              page.jobs.map((j) => (
                <View key={j.id} style={{ marginBottom: 10 }}>
                  <Row style={{ justifyContent: "space-between" }}>
                    <Text style={{ flex: 1 }}>{j.role}</Text>
                    <Badge label={j.status} />
                  </Row>
                  <Row style={{ gap: 16 }}>
                    <TouchableOpacity onPress={() => router.push(`/job/${j.id}` as Href)} style={{ minHeight: 44, justifyContent: "center" }}>
                      <Text style={{ color: colors.accent, fontWeight: "600" }}>Open</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => router.push(`/jobs/${j.id}/process` as Href)} style={{ minHeight: 44, justifyContent: "center" }}>
                      <Text style={{ color: colors.accent, fontWeight: "600" }}>Hiring process</Text>
                    </TouchableOpacity>
                  </Row>
                </View>
              ))
            )}
          </Card>

          <SectionTitle>People you know here</SectionTitle>
          <Card>
            {page.contacts.length === 0 ? (
              <Muted>No contacts yet. Add one on the Contacts page and set their company.</Muted>
            ) : (
              page.contacts.map((c) => (
                <Text key={c.id} style={{ marginBottom: 6 }}>
                  {c.name}
                  {c.title ? ` · ${c.title}` : ""}
                </Text>
              ))
            )}
          </Card>

          <SectionTitle>Interviews</SectionTitle>
          <Card>
            {page.interviews.length === 0 ? (
              <Muted>No interviews with them yet.</Muted>
            ) : (
              page.interviews.map((i) => (
                <View key={i.id} style={{ marginBottom: 8 }}>
                  <Text>
                    {i.name} for {i.role}, {i.when}
                  </Text>
                  <Muted>
                    {i.outcome_label}
                    {i.interviewers.length > 0 ? ` · with ${i.interviewers.join(", ")}` : ""}
                  </Muted>
                </View>
              ))
            )}
          </Card>

          <SectionTitle>Offers</SectionTitle>
          <Card>
            {page.offers.length === 0 ? (
              <Muted>No offers from them.</Muted>
            ) : (
              page.offers.map((o) => (
                <Text key={o.id} style={{ marginBottom: 6 }}>
                  {o.role}: {o.base} {o.currency} · {o.status_label}
                </Text>
              ))
            )}
          </Card>

          <SectionTitle>Notes and links</SectionTitle>
          <Card>
            <Details page={page} onSaved={load.setData} />
          </Card>
          <Row style={{ justifyContent: "center", marginTop: 4 }}>
            <Ionicons name="lock-closed-outline" size={14} color={colors.textMuted} />
            <Muted>Only you see these notes.</Muted>
          </Row>
        </>
      ) : null}
    </Screen>
  );
}
