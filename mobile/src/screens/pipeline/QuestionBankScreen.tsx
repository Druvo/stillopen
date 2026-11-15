import { useRouter, type Href } from "expo-router";
import React, { useEffect, useState } from "react";
import { View } from "react-native";

import { ApiError } from "../../api/client";
import { pipelineApi, type Bank, type BankItem } from "../../api/pipeline";
import { Badge, Button, Card, Chip, confirm, Empty, ErrorBox, Field, Loading, Muted, notify, Row, Screen, Text, useTheme } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";
import { FormSheet, MultiPick } from "./parts";

const parseTags = (text: string) => text.split(",").map((t) => t.trim()).filter(Boolean);

function BankForm({ data, item, onDone }: { data: Bank; item?: BankItem; onDone: () => void }) {
  const act = useAction();
  const [question, setQuestion] = useState(item?.question ?? "");
  const [answer, setAnswer] = useState(item?.answer ?? "");
  const [tags, setTags] = useState(item?.tags.join(", ") ?? "");
  const [interviews, setInterviews] = useState<number[]>(item?.interviews.map((i) => i.id) ?? []);
  const [jobs, setJobs] = useState<number[]>(item?.jobs.map((j) => j.id) ?? []);
  const f = act.fields ?? {};
  return (
    <View>
      <Field label="Question" value={question} onChangeText={setQuestion} multiline maxLength={400} error={f.question} />
      <Field label="Your answer" value={answer} onChangeText={setAnswer} multiline maxLength={4000} hint="In your own words. Only you see this." />
      <Field label="Skill tags" value={tags} onChangeText={setTags} autoCapitalize="none" hint="Up to five, separated by commas. For example: python, leadership." error={f.tags} />
      <MultiPick label="Jobs where it was asked" options={data.jobs} value={jobs} onChange={setJobs} />
      <MultiPick label="Stages where it was asked" options={data.interviews} value={interviews} onChange={setInterviews} />
      {act.error && !act.fields ? <ErrorBox message={act.error} /> : null}
      <Button
        label={item ? "Save changes" : "Save question"}
        busy={act.busy}
        onPress={async () => {
          const body = { question, answer, tags: parseTags(tags), interview_ids: interviews, job_ids: jobs };
          if (await act.run(() => (item ? pipelineApi.editBank(item.id, body) : pipelineApi.addBank(body)))) {
            notify("Question saved.");
            onDone();
          }
        }}
      />
    </View>
  );
}

function BankCard({ item, onEdit, onChanged }: { item: BankItem; onEdit: () => void; onChanged: () => void }) {
  const { colors } = useTheme();
  const router = useRouter();
  const act = useAction();
  const remove = async () => {
    if (!(await confirm("Delete this question?", undefined, "Delete"))) return;
    const done = await act.run(async () => {
      try {
        await pipelineApi.deleteBank(item.id);
      } catch (e) {
        // A question linked to an interview or a job needs a second, explicit yes.
        if (e instanceof ApiError && e.status === 409) {
          if (!(await confirm("This question is linked to an interview or a job.", "Delete it anyway?", "Delete anyway"))) return false;
          await pipelineApi.deleteBank(item.id, true);
        } else throw e;
      }
      return true;
    });
    if (done) {
      notify("Deleted.");
      onChanged();
    }
  };
  return (
    <Card>
      <Text style={{ fontWeight: "700" }}>{item.question}</Text>
      {item.answer ? <Text style={{ marginTop: 6 }}>{item.answer}</Text> : null}
      {item.tags.length > 0 ? (
        <Row style={{ flexWrap: "wrap", marginTop: 8, gap: 6 }}>
          {item.tags.map((t) => (
            <Badge key={t} label={t} color={colors.textMuted} />
          ))}
        </Row>
      ) : null}
      {item.jobs.length > 0 ? (
        <View style={{ marginTop: 8 }}>
          <Muted>Asked for:</Muted>
          {item.jobs.map((j) => (
            <Text key={j.id} style={{ color: colors.accent, minHeight: 32 }} onPress={() => router.push(`/job/${j.id}` as Href)} accessibilityRole="link">
              {j.label}
            </Text>
          ))}
        </View>
      ) : null}
      {item.interviews.length > 0 ? (
        <View style={{ marginTop: 4 }}>
          <Muted>Asked at:</Muted>
          {item.interviews.map((i) => (
            <Text key={i.id} style={{ color: colors.accent, minHeight: 32 }} onPress={() => router.push(`/jobs/${i.job_id}/process` as Href)} accessibilityRole="link">
              {i.label}
            </Text>
          ))}
        </View>
      ) : null}
      <Row style={{ marginTop: 10 }}>
        <Button label="Edit" variant="secondary" onPress={onEdit} />
        <Button label="Delete" variant="danger" busy={act.busy} onPress={remove} />
      </Row>
      {act.error ? <Text style={{ color: colors.danger, marginTop: 8 }}>{act.error}</Text> : null}
    </Card>
  );
}

export default function QuestionBankScreen() {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [tag, setTag] = useState("");
  const [editing, setEditing] = useState<BankItem | "new" | null>(null);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 350);
    return () => clearTimeout(t);
  }, [search]);
  const load = useLoad(() => pipelineApi.bank(debounced, tag), [debounced, tag]);
  const data = load.data;
  return (
    <Screen title="Question bank" onRefresh={load.refresh} refreshing={load.refreshing}>
      <Muted style={{ marginBottom: 12 }}>Interview questions you want to be ready for, with your own answers. Save one from any prep list, or add your own.</Muted>
      <Button label="Add a question" onPress={() => setEditing("new")} />
      <View style={{ height: 12 }} />
      <Field label="Search" value={search} onChangeText={setSearch} maxLength={100} autoCapitalize="none" returnKeyType="search" />
      {data && data.tags.length > 0 ? (
        <Row style={{ flexWrap: "wrap", gap: 8, marginBottom: 14 }}>
          <Chip label="All tags" selected={tag === ""} onPress={() => setTag("")} />
          {data.tags.map((t) => (
            <Chip key={t} label={t} selected={tag === t} onPress={() => setTag(tag === t ? "" : t)} />
          ))}
        </Row>
      ) : null}
      {load.loading && !data ? <Loading /> : load.error && !data ? <ErrorBox message={load.error} onRetry={load.reload} /> : null}
      {data ? (
        data.questions.length === 0 ? (
          <Empty
            title={search || tag ? "No saved question matches" : "Nothing saved yet"}
            hint={search || tag ? "Clear the search or pick another tag." : "Add a question you were asked, or press Save to my question bank on a prep question."}
            action={search || tag ? undefined : { label: "Add a question", onPress: () => setEditing("new") }}
          />
        ) : (
          data.questions.map((q) => <BankCard key={q.id} item={q} onEdit={() => setEditing(q)} onChanged={load.reload} />)
        )
      ) : null}
      <FormSheet visible={editing !== null && !!data} title={editing && editing !== "new" ? "Edit question" : "Add a question"} onClose={() => setEditing(null)}>
        {editing && data ? (
          <BankForm
            key={editing === "new" ? "new" : editing.id}
            data={data}
            item={editing === "new" ? undefined : editing}
            onDone={() => {
              setEditing(null);
              load.reload();
            }}
          />
        ) : null}
      </FormSheet>
    </Screen>
  );
}
