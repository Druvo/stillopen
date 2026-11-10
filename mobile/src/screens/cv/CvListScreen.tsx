import { useRouter, type Href } from "expo-router";
import React, { useState } from "react";
import { View } from "react-native";

import { cvApi, type CvSummary } from "../../api/cv";
import { useTheme } from "../../context/ThemeContext";
import { Badge, Button, Card, confirm, Empty, ErrorBox, Loading, Muted, notify, Screen, SectionTitle, Text } from "../../ui";
import { errorText, useLoad } from "../../ui/useApi";
import { readinessTone } from "./logic/quality";
import { when } from "./parts";

function VersionCard({ v, children, onOpen }: { v: CvSummary; children?: React.ReactNode; onOpen: () => void }) {
  const { colors } = useTheme();
  const tone = typeof v.ats_readiness === "number" ? readinessTone(v.ats_readiness) : null;
  const atsColor = tone === "good" ? colors.good : tone === "warn" ? colors.warn : colors.danger;
  return (
    <Card onPress={onOpen}>
      <Text style={{ fontWeight: "700", fontSize: 16 }}>{v.label || `Version ${v.id}`}</Text>
      <Muted style={{ marginTop: 2 }}>
        v{v.id} - {when(v.created_at)} - {v.source_label}
        {v.provider ? ` (${v.provider})` : ""}
      </Muted>
      {v.job ? <Muted>For {v.job.company} - {v.job.role}</Muted> : null}
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
        {v.current ? <Badge label="Current" /> : null}
        {v.kind === "tailored" ? (
          v.flagged && !v.approved ? (
            <Badge label={`${v.flagged_count} to review`} color={colors.warn} />
          ) : v.flagged ? (
            <Badge label="Approved" color={colors.good} />
          ) : (
            <Badge label="Checked" color={colors.good} />
          )
        ) : null}
        {tone ? <Badge label={`ATS check ${v.ats_readiness}/100`} color={atsColor} /> : null}
      </View>
      {children}
    </Card>
  );
}

export default function CvListScreen() {
  const router = useRouter();
  const { data, error, loading, refreshing, refresh, reload } = useLoad(() => cvApi.list());
  const [busyId, setBusyId] = useState<number | null>(null);
  const [message, setMessage] = useState("");

  const open = (id: number) => router.push({ pathname: "/cv/[id]", params: { id: String(id) } });

  async function restore(v: CvSummary) {
    if (!(await confirm("Make this your current CV?", "Your history is kept.", "Restore"))) return;
    setBusyId(v.id);
    setMessage("");
    try {
      const made = await cvApi.restore(v.id);
      notify("Restored", "It is now your current CV. The history is kept.");
      await reload();
      open(made.id);
    } catch (e) {
      setMessage(errorText(e));
    } finally {
      setBusyId(null);
    }
  }

  async function remove(v: CvSummary) {
    if (!(await confirm("Delete this tailored CV?", `"${v.label || `Version ${v.id}`}" will be removed. Your master CV is not affected.`))) return;
    setBusyId(v.id);
    setMessage("");
    try {
      await cvApi.remove(v.id);
      await reload();
    } catch (e) {
      setMessage(errorText(e));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Screen title="Your CV" onRefresh={refresh} refreshing={refreshing}>
      <Muted style={{ marginBottom: 12 }}>
        Every change to your CV is kept. Each tailored CV is saved with the job it was made for, so you always know exactly what you sent.
      </Muted>
      <View style={{ flexDirection: "row", gap: 10, marginBottom: 8 }}>
        <Button label="Build, import or tailor" icon="add-circle-outline" onPress={() => router.push("/cv/new" as Href)} style={{ flex: 1 }} />
        <Button label="Documents" variant="secondary" icon="folder-open-outline" onPress={() => router.push("/documents" as Href)} />
      </View>
      {message ? <ErrorBox message={message} /> : null}
      {loading ? <Loading /> : null}
      {error && !data ? <ErrorBox message={error} onRetry={reload} /> : null}
      {data ? (
        <>
          <SectionTitle>Tailored for jobs</SectionTitle>
          {data.tailored.length === 0 ? (
            <Empty title="No tailored CVs yet" hint="Pick a job and a CV matched to it is saved here." action={{ label: "Tailor a CV for a job", onPress: () => router.push("/cv/new" as Href) }} />
          ) : (
            data.tailored.map((v) => (
              <VersionCard key={v.id} v={v} onOpen={() => open(v.id)}>
                <View style={{ flexDirection: "row", marginTop: 10 }}>
                  <Button label="Delete" variant="danger" busy={busyId === v.id} onPress={() => remove(v)} />
                </View>
              </VersionCard>
            ))
          )}

          <SectionTitle>Your CV over time</SectionTitle>
          {data.masters.length === 0 ? (
            <Empty title="No CV yet" hint="Build one in about five minutes, or import the file you already have." action={{ label: "Build or import a CV", onPress: () => router.push("/cv/new" as Href) }} />
          ) : (
            data.masters.map((v, i) => (
              <VersionCard key={v.id} v={{ ...v, current: i === 0 }} onOpen={() => open(v.id)}>
                {i > 0 ? (
                  <View style={{ flexDirection: "row", gap: 10, marginTop: 10 }}>
                    <Button
                      label="Compare with current"
                      variant="secondary"
                      style={{ flex: 1 }}
                      onPress={() => router.push({ pathname: "/cv/[id]/diff", params: { id: String(data.masters[0].id), against: String(v.id) } })}
                    />
                    <Button label="Restore" busy={busyId === v.id} onPress={() => restore(v)} />
                  </View>
                ) : null}
              </VersionCard>
            ))
          )}
        </>
      ) : null}
    </Screen>
  );
}
