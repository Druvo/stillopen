import { useLocalSearchParams, useRouter } from "expo-router";
import React, { useState } from "react";
import { View } from "react-native";

import { cvApi, type TailorMode } from "../../api/cv";
import { Button, Card, Choice, Empty, ErrorBox, Loading, Muted, notify, Screen, Select, Text } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";
import { CvBuilder } from "./builder";
import { ImportPanel } from "./importPanel";
import { tailoredSaid } from "./logic/messages";
import { emptyAnswers, type BuilderAnswers } from "./logic/quality";

type Tab = "build" | "import" | "tailor";

const MODES: { value: TailorMode; label: string }[] = [
  { value: "auto", label: "Automatic" },
  { value: "ai", label: "My AI" },
  { value: "keywords", label: "Keywords only" },
];

function TailorPanel({ initialJob }: { initialJob: number | null }) {
  const router = useRouter();
  const { data, error, loading, reload } = useLoad(() => cvApi.jobChoices());
  const [jobId, setJobId] = useState<number | null>(initialJob);
  const [mode, setMode] = useState<TailorMode>("auto");
  const act = useAction();

  if (loading) return <Loading />;
  if (!data) return <ErrorBox message={error ?? "We could not load your jobs."} onRetry={reload} />;
  if (data.jobs.length === 0) return <Empty title="No jobs yet" hint="Add a job first, then come back to make a CV matched to it." action={{ label: "Add a job", onPress: () => router.push("/jobs/add") }} />;

  async function tailor() {
    if (!jobId) return;
    const made = await act.run(() => cvApi.tailor(jobId, mode));
    if (made) {
      const said = tailoredSaid(made);
      notify(said.tone === "error" ? "Check this CV" : "Tailored CV ready", said.text);
      router.replace({ pathname: "/cv/[id]", params: { id: String(made.id) } });
    }
  }

  return (
    <View>
      <Muted style={{ marginBottom: 10 }}>
        We rewrite your current CV for one job, using only what is already in your CV and documents. Anything that is not there is flagged for you to check, and the tailored CV stays locked for download until you approve it.
      </Muted>
      <Select label="Which job?" value={jobId} onChange={setJobId} options={data.jobs.map((j) => ({ value: j.id, label: `${j.company} - ${j.role}${j.has_description ? "" : " (no description yet)"}` }))} />
      <Choice
        label="How"
        value={mode}
        onChange={setMode}
        options={MODES.filter((m) => m.value === "keywords" || data.ai.available || m.value === "auto")}
      />
      {!data.ai.available ? <Muted style={{ marginBottom: 10 }}>{data.ai.missing_message} Without it, the keyword method is used.</Muted> : null}
      {act.error ? <ErrorBox message={act.error} /> : null}
      <Button label="Tailor my CV" icon="sparkles-outline" onPress={tailor} busy={act.busy} disabled={!jobId} />
    </View>
  );
}

export default function NewCvScreen() {
  const params = useLocalSearchParams<{ tab?: string; job?: string }>();
  const initial: Tab = params.tab === "import" || params.tab === "tailor" ? params.tab : params.job ? "tailor" : "build";
  const [tab, setTab] = useState<Tab>(initial);
  const [answers, setAnswers] = useState<BuilderAnswers>(emptyAnswers);
  const [step, setStep] = useState(0);
  const { data: choices } = useLoad(() => cvApi.jobChoices());
  const existing = useLoad(() => cvApi.list());

  const hasCv = (existing.data?.masters.length ?? 0) > 0;
  return (
    <Screen title="New CV">
      <Choice
        value={tab}
        onChange={setTab}
        options={[
          { value: "build", label: "Build step by step" },
          { value: "import", label: "Import a file" },
          { value: "tailor", label: "Tailor for a job" },
        ]}
      />
      {tab !== "tailor" && hasCv ? <Card><Muted>You already have a CV. Building a new one adds a new version and makes it your current CV. Your earlier versions are kept.</Muted></Card> : null}
      {tab === "build" ? <CvBuilder answers={answers} setAnswers={setAnswers} step={step} setStep={setStep} ai={choices?.ai ?? null} /> : null}
      {tab === "import" ? (
        <ImportPanel
          aiAvailable={Boolean(choices?.ai.available)}
          current={answers}
          onFill={(filled, at) => {
            setAnswers(filled);
            setStep(at);
            setTab("build");
            notify("Filled from your file", "Check each step, then build your CV. Nothing is saved yet.");
          }}
        />
      ) : null}
      {tab === "tailor" ? <TailorPanel initialJob={params.job && /^\d+$/.test(params.job) ? Number(params.job) : null} /> : null}
    </Screen>
  );
}
