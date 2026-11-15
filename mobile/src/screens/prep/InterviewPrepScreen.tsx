import { useLocalSearchParams } from "expo-router";
import React, { useState } from "react";
import { View } from "react-native";

import type { Tally } from "../../api/prep";
import { assistApi, findingsText, prepText, questionText, starMissing, statements, wordCount, type Feedback, type InterviewPrep, type PostingSummary, type PrepQuestion } from "../../api/assist";
import { Badge, Body, Button, Card, ErrorBox, Field, Loading, Muted, notify, Screen, SectionTitle, Text, useTheme } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";
import { AiNotice, CameUpTick, CopyButton, NoKeyLine, Problem } from "./parts";

function Listing({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <View style={{ marginTop: 8 }}>
      <Text style={{ fontWeight: "700", fontSize: 14 }}>{title}</Text>
      {items.map((t, i) => (
        <Text key={i} style={{ fontSize: 14, marginTop: 2 }}>
          {"•"} {t}
        </Text>
      ))}
    </View>
  );
}

function FeedbackView({ feedback }: { feedback: Feedback }) {
  const { colors } = useTheme();
  const missing = starMissing(feedback.star);
  return (
    <View style={{ marginTop: 12, padding: 12, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceAlt }}>
      {feedback.summary ? <Body>{feedback.summary}</Body> : null}
      <Listing title="What works" items={feedback.works} />
      <Listing title="What is vague" items={feedback.vague} />
      <Listing title="What to add" items={feedback.add} />
      <Body style={{ marginTop: 8 }}>
        <Text style={{ fontWeight: "700" }}>Structure: </Text>
        {missing.length === 0 ? "your answer covers the situation, your task, what you did and the result." : `not clear yet: ${missing.join(", ")}.`}
      </Body>
      <Body style={{ marginTop: 4 }}>
        <Text style={{ fontWeight: "700" }}>Length: </Text>
        {feedback.length.words} words. {feedback.length.note}
      </Body>
      <AiNotice>{feedback.notice}</AiNotice>
    </View>
  );
}

function Practise({ jobId, question }: { jobId: number; question: string }) {
  const [open, setOpen] = useState(false);
  const [answer, setAnswer] = useState("");
  const act = useAction();
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  if (!open) return <Button label="Practise this answer" variant="ghost" onPress={() => setOpen(true)} />;
  return (
    <View style={{ marginTop: 8 }}>
      <Field
        label="Your answer, written the way you would say it"
        hint="Nothing you type here is saved. You get feedback, not a grade."
        value={answer}
        onChangeText={setAnswer}
        multiline
        maxLength={3000}
      />
      <Button
        label={act.busy ? "Reading your answer…" : "Get feedback"}
        variant="secondary"
        busy={act.busy}
        disabled={wordCount(answer) < 5}
        onPress={async () => {
          const r = await act.run(() => assistApi.feedback(jobId, question, answer));
          if (r) setFeedback(r.feedback);
        }}
      />
      <Problem message={act.error} />
      {feedback ? <FeedbackView feedback={feedback} /> : null}
    </View>
  );
}

function QuestionCard({ jobId, q, ticked, onTally, canPractise }: { jobId: number; q: PrepQuestion; ticked: boolean; onTally: (t: { ticked: (number | string)[]; text: string }) => void; canPractise: boolean }) {
  const { colors } = useTheme();
  const [saved, setSaved] = useState(false);
  const save = useAction();
  return (
    <Card>
      <Text style={{ fontWeight: "700", fontSize: 16 }}>{q.question}</Text>
      <Muted style={{ marginTop: 6 }}>What they are really testing: {q.testing}</Muted>
      {q.outline.length > 0 ? (
        <View style={{ marginTop: 8 }}>
          <Muted>Outline to rewrite in your own words (from your own material)</Muted>
          {q.outline.map((p, i) => (
            <Text key={i} style={{ fontSize: 14, marginTop: 3 }}>
              {"•"} {p}
            </Text>
          ))}
        </View>
      ) : (
        <Muted style={{ marginTop: 8 }}>Nothing in your material fits this one yet. Think of your own example, and be honest if it is something you are still learning.</Muted>
      )}
      {q.flags.length > 0 ? <Text style={{ color: colors.warn, fontSize: 12, marginTop: 6 }}>The job mentions {q.flags.join(", ")}, which your material does not. Only say it if it is true.</Text> : null}
      <CameUpTick
        ticked={ticked}
        onSet={async (value) => {
          const t = await assistApi.setJobCameUp(jobId, q.id, value);
          onTally(t);
        }}
      />
      <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap" }}>
        <CopyButton text={questionText(q)} label="Copy" />
        {saved ? (
          <Muted style={{ alignSelf: "center" }}>In your question bank</Muted>
        ) : (
          <Button
            label="Save to my question bank"
            variant="secondary"
            busy={save.busy}
            onPress={async () => {
              if (await save.run(() => assistApi.saveToBank(q.question, jobId))) {
                setSaved(true);
                notify("Saved to your question bank.");
              }
            }}
          />
        )}
      </View>
      <Problem message={save.error} />
      {canPractise ? <Practise jobId={jobId} question={q.question} /> : null}
    </Card>
  );
}

function Questions({ jobId }: { jobId: number }) {
  const act = useAction();
  const { data, error, loading, setData } = useLoad(() => assistApi.getPrep(jobId), [jobId]);
  const tally = useLoad(() => assistApi.jobTally(jobId), [jobId]);
  const prep: InterviewPrep | null = data?.prep ?? null;
  const ai = data?.ai ?? false;
  return (
    <>
      <SectionTitle>Prepare for interviews</SectionTitle>
      <Muted style={{ marginBottom: 10 }}>Eight questions this job is likely to bring up, from the posting and your own material. Nothing here is sent or saved as your words.</Muted>
      {loading ? <Loading /> : null}
      {error && !data ? <ErrorBox message={error} /> : null}
      {data && !ai ? (
        <Card>
          <NoKeyLine />
        </Card>
      ) : null}
      {data && ai ? (
        <Button
          label={act.busy ? "Writing your questions…" : prep ? "Write them again" : "Write my interview questions"}
          variant={prep ? "secondary" : "primary"}
          busy={act.busy}
          onPress={async () => {
            const r = await act.run(() => assistApi.makePrep(jobId));
            if (r) setData(r);
          }}
        />
      ) : null}
      <Problem message={act.error} />
      {prep ? (
        <View style={{ marginTop: 12 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 8 }}>
            <CopyButton text={prepText(prep)} label="Copy all questions" />
            <Badge label={`Made ${prep.generated_at.slice(0, 10)}`} />
          </View>
          {tally.data?.text ? <Muted style={{ marginBottom: 8 }}>{tally.data.text}</Muted> : null}
          {prep.groups
            .filter((g) => g.questions.length > 0)
            .map((g) => (
              <View key={g.key}>
                <SectionTitle>{g.title}</SectionTitle>
                {g.questions.map((q) => (
                  <QuestionCard key={q.id} jobId={jobId} q={q} canPractise={ai} ticked={tally.data?.ticked.includes(q.id) ?? false} onTally={(t) => tally.setData(t as Tally)} />
                ))}
              </View>
            ))}
          {prep.dropped_points > 0 ? (
            <Muted>
              We left out {prep.dropped_points} outline point{prep.dropped_points === 1 ? "" : "s"} that mentioned things your own material does not show.
            </Muted>
          ) : null}
          <AiNotice>{prep.notice}</AiNotice>
        </View>
      ) : null}
    </>
  );
}

function SummaryView({ summary }: { summary: PostingSummary }) {
  const rows = statements(summary);
  return (
    <View style={{ marginTop: 10 }}>
      <Listing title="Must have" items={summary.must_have} />
      <Listing title="Nice to have" items={summary.nice_to_have} />
      {summary.must_have.length === 0 && summary.nice_to_have.length === 0 ? <Muted style={{ marginTop: 8 }}>We could not tell which skills are required. Read the posting itself.</Muted> : null}
      {rows.length > 0 ? (
        <View style={{ marginTop: 8 }}>
          {rows.map((r) => (
            <Body key={r.label}>
              <Text style={{ fontWeight: "700" }}>{r.label}:</Text> {r.text}
            </Body>
          ))}
        </View>
      ) : (
        <Muted style={{ marginTop: 8 }}>The posting says nothing about level, pay, visas, relocation or a deadline.</Muted>
      )}
      <Text style={{ fontWeight: "700", fontSize: 14, marginTop: 8 }}>Red flags</Text>
      {summary.red_flags.length === 0 ? (
        <Muted>None found. That is not a promise: still check the company is real.</Muted>
      ) : (
        summary.red_flags.map((f, i) => (
          <Body key={i} style={{ marginTop: 2 }}>
            {"•"} {f.flag} <Muted>The posting says: {"“"}{f.quote}{"”"}</Muted>
          </Body>
        ))
      )}
      <Muted style={{ marginTop: 8 }}>{summary.method === "ai" ? "Read by AI, which can be wrong. Check it against the posting." : "A quick read by simple rules, not by AI. Check it against the posting."}</Muted>
    </View>
  );
}

function Summary({ jobId }: { jobId: number }) {
  const act = useAction();
  const { data, error, loading, setData } = useLoad(() => assistApi.getSummary(jobId), [jobId]);
  const summary = data?.summary ?? null;
  return (
    <Card>
      <Text style={{ fontWeight: "700", fontSize: 16 }}>What this role really needs</Text>
      <Muted style={{ marginVertical: 6 }}>A short list of what the posting asks for, and anything in it that looks worrying.</Muted>
      {loading ? <Loading /> : null}
      {error && !data ? <ErrorBox message={error} /> : null}
      {data ? (
        <Button
          label={act.busy ? "Reading the posting…" : summary ? "Read it again" : "Read this posting"}
          variant={summary ? "secondary" : "primary"}
          busy={act.busy}
          onPress={async () => {
            const r = await act.run(() => assistApi.summarise(jobId));
            if (r) setData({ summary: r.summary, ai: r.ai });
          }}
        />
      ) : null}
      {data && !data.ai ? <Muted style={{ marginTop: 8 }}>This is the free version. For a deeper read, add your free Google AI Studio key in AI settings.</Muted> : null}
      <Problem message={act.error} />
      {summary ? <SummaryView summary={summary} /> : null}
      {summary?.method === "ai" && summary.notice ? <AiNotice>{summary.notice}</AiNotice> : null}
    </Card>
  );
}

/** A draft answer to a question on an application form. Only ever copied, never sent. */
function ApplicationAnswer({ jobId }: { jobId: number }) {
  const status = useLoad(() => assistApi.status(), []);
  const { colors } = useTheme();
  const [question, setQuestion] = useState("");
  const [text, setText] = useState("");
  const [meta, setMeta] = useState<{ words: number; flagged: string; notice: string } | null>(null);
  const act = useAction();
  return (
    <>
      <SectionTitle>Answer an application question</SectionTitle>
      <Card>
        {status.data && !status.data.ai ? (
          <NoKeyLine />
        ) : (
          <>
            <Field
              label="The question from the application form"
              hint="For example: Why do you want this role? Or: Describe a time you led a project."
              value={question}
              onChangeText={setQuestion}
              maxLength={500}
            />
            <Button
              label={act.busy ? "Writing a draft…" : "Draft an answer"}
              busy={act.busy}
              disabled={question.trim().length < 5}
              onPress={async () => {
                const r = await act.run(() => assistApi.answer(jobId, question));
                if (r) {
                  setText(r.answer);
                  setMeta({ words: r.words, flagged: r.flagged_count > 0 ? findingsText(r.flagged) : "", notice: r.notice });
                }
              }}
            />
            <Problem message={act.error} />
            {meta ? (
              <View style={{ marginTop: 14 }}>
                <Field label="Your draft (edit it freely)" value={text} onChangeText={setText} multiline numberOfLines={9} />
                <Muted>{meta.words} words. Copy it into the application form yourself; nothing is sent for you.</Muted>
                {meta.flagged ? (
                  <Text style={{ color: colors.warn, fontSize: 13, marginVertical: 8 }}>We could not match these to your own material: {meta.flagged}. Remove or change them unless they are true.</Text>
                ) : null}
                <View style={{ marginTop: 8 }}>
                  <CopyButton text={text} label="Copy the answer" />
                </View>
                <AiNotice>{meta.notice}</AiNotice>
              </View>
            ) : null}
          </>
        )}
      </Card>
    </>
  );
}

export default function InterviewPrepScreen() {
  const { id: raw } = useLocalSearchParams<{ id: string }>();
  const jobId = Number(raw);
  const [tick, setTick] = useState(0);
  return (
    <Screen title="Interview prep" onRefresh={() => setTick(tick + 1)}>
      <Summary key={`s${tick}`} jobId={jobId} />
      <Questions key={`q${tick}`} jobId={jobId} />
      <ApplicationAnswer key={`a${tick}`} jobId={jobId} />
    </Screen>
  );
}
