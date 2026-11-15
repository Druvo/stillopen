import * as Clipboard from "expo-clipboard";
import { useLocalSearchParams, useRouter } from "expo-router";
import React, { useEffect, useState } from "react";
import { View } from "react-native";

import { googleApi, type ApplyInfo, type MailItem, type MailList, type Preview } from "../../api/google";
import { Button, Card, confirm, ErrorBox, Field, Loading, Muted, notify, Screen, SectionTitle, Select, Text, useTheme } from "../../ui";
import { errorText, useLoad } from "../../ui/useApi";
import { dayTimeText } from "./format";

const size = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

export default function JobMailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const jobId = Number(id);
  const { data, error, loading, refreshing, refresh, reload } = useLoad(() => googleApi.applyInfo(jobId), [jobId]);
  return (
    <Screen title="Email and replies" onRefresh={refresh} refreshing={refreshing}>
      {loading ? (
        <Loading />
      ) : error && !data ? (
        <ErrorBox message={error} onRetry={reload} />
      ) : data ? (
        <>
          <Muted style={{ marginBottom: 10 }}>
            {data.job.role} at {data.job.company}
          </Muted>
          <SendFromGmail jobId={jobId} info={data} />
          <Replies jobId={jobId} connected={data.google.connected} thread={data.google.thread} />
        </>
      ) : null}
    </Screen>
  );
}

/**
 * "Send from my Gmail". Nothing is sent before the last step: write (or edit) the message, see it exactly as it will go (the server describes it and gives
 * back a fingerprint), then press Send and confirm. Changing anything after the preview throws the preview away.
 */
function SendFromGmail({ jobId, info }: { jobId: number; info: ApplyInfo }) {
  const router = useRouter();
  const [to, setTo] = useState(info.google.suggested_to);
  const [subject, setSubject] = useState(info.draft.subject);
  const [body, setBody] = useState(info.draft.body);
  const [cv, setCv] = useState<number | null>(info.selected);
  const [cover, setCover] = useState<number | null>(info.cover_letters.find((l) => !l.needs_review)?.id ?? null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const edit = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setPreview(null);
  };
  const message = { to, subject, body, cv, cover };

  if (!info.google.available) return null;
  if (!info.google.connected) {
    return (
      <Card>
        <Text style={{ fontWeight: "700" }}>Send from my Gmail</Text>
        <Muted style={{ marginVertical: 6 }}>Connect your Google account to send this from your own Gmail and see the replies here.</Muted>
        <Button variant="secondary" label="Connect Google" onPress={() => router.push("/profile/connections")} />
      </Card>
    );
  }

  const look = async () => {
    setBusy(true);
    setError("");
    try {
      setPreview(await googleApi.preview(jobId, message));
    } catch (e) {
      setPreview(null);
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const send = async () => {
    if (!preview) return;
    // The one place a message goes out: only from this button, for exactly the previewed message, after a second confirmation.
    if (!(await confirm(`Send this email to ${preview.to}?`, "It goes from your own Gmail, exactly as shown.", "Send"))) return;
    setBusy(true);
    setError("");
    try {
      const done = await googleApi.send(jobId, message, preview.digest);
      notify(`Sent to ${done.to}.`, done.follow_up_date ? `We have noted it, and will remind you to follow up on ${done.follow_up_date}.` : "We have noted it.");
      router.replace("/");
    } catch (e) {
      setError(errorText(e));
      setPreview(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <Text style={{ fontWeight: "700" }}>Send from my Gmail</Text>
      <Muted style={{ marginVertical: 6 }}>Nothing is sent until you have looked at the whole message and pressed Send. The CV you choose is attached as a Word file.</Muted>
      <Field
        label="Send to"
        value={to}
        onChangeText={edit(setTo)}
        keyboardType="email-address"
        autoCapitalize="none"
        autoCorrect={false}
        hint={info.google.suggested_to && to === info.google.suggested_to ? "This is the address the posting itself gives. Check it is the right one." : "Type the address you are applying to."}
      />
      <Field label="Subject" value={subject} onChangeText={edit(setSubject)} maxLength={200} />
      <Field label="Message" value={body} onChangeText={edit(setBody)} multiline style={{ minHeight: 200 }} hint="Replace [Your name] and check every statement is true." />
      <Select
        label="CV to attach"
        value={cv}
        placeholder="No CV (nothing attached)"
        options={info.versions.map((v) => ({ value: v.id, label: `${v.label}${v.flagged ? " (needs review)" : ""} · ${v.created}` }))}
        onChange={edit(setCv)}
      />
      {cv !== null ? <Button variant="ghost" label="Attach no CV" onPress={() => { setCv(null); setPreview(null); }} /> : <Muted style={{ marginBottom: 10 }}>No CV is chosen, so nothing will be attached.</Muted>}
      {info.cover_letters.length > 0 ? (
        <Select
          label="Cover letter"
          value={cover}
          placeholder="No cover letter"
          options={info.cover_letters.map((l) => ({ value: l.id, label: `Letter of ${l.created}${l.needs_review ? " (needs review)" : ""}` }))}
          onChange={edit(setCover)}
        />
      ) : null}
      {!preview ? <Button label="Preview the email" busy={busy} disabled={!to.trim()} onPress={look} /> : null}
      {preview ? <PreviewBox preview={preview} busy={busy} onSend={send} onEdit={() => setPreview(null)} /> : null}
      {error ? (
        <View style={{ marginTop: 10 }}>
          <ErrorBox message={error} />
        </View>
      ) : null}
    </Card>
  );
}

function PreviewBox({ preview, busy, onSend, onEdit }: { preview: Preview; busy: boolean; onSend: () => void; onEdit: () => void }) {
  const { colors } = useTheme();
  return (
    <View accessibilityLabel="The email exactly as it will be sent" style={{ borderWidth: 1, borderColor: colors.accent, borderRadius: 12, padding: 12, marginTop: 4 }}>
      <Text style={{ fontWeight: "700", marginBottom: 6 }}>The email exactly as it will be sent</Text>
      <Text>
        <Text style={{ fontWeight: "700" }}>From: </Text>
        {preview.from || "your Gmail"}
      </Text>
      <Text>
        <Text style={{ fontWeight: "700" }}>To: </Text>
        {preview.to}
      </Text>
      <Text>
        <Text style={{ fontWeight: "700" }}>Subject: </Text>
        {preview.subject}
      </Text>
      <Text style={{ marginTop: 8 }}>{preview.body}</Text>
      <Text style={{ marginTop: 8 }}>
        <Text style={{ fontWeight: "700" }}>Attached: </Text>
        {preview.attachments.length ? preview.attachments.map((a) => `${a.name} (${size(a.bytes)})`).join(", ") : "nothing"}
      </Text>
      <View style={{ gap: 8, marginTop: 12 }}>
        <Button label={`Send to ${preview.to}`} icon="send" busy={busy} onPress={onSend} />
        <Button variant="ghost" label="Keep editing" disabled={busy} onPress={onEdit} />
      </View>
    </View>
  );
}

/** Replies next to the job: the saved conversation, a manual "Check for replies", a draft reply to edit and three free interview times. Nothing here sends. */
function Replies({ jobId, connected, thread }: { jobId: number; connected: boolean; thread: boolean }) {
  const [data, setData] = useState<MailList | null>(null);
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [reply, setReply] = useState("");
  const [flags, setFlags] = useState<string[]>([]);

  useEffect(() => {
    if (!connected) return;
    let live = true;
    (async () => {
      try {
        setData(await googleApi.messages(jobId));
        if (thread) {
          await googleApi.check(jobId, "", false).catch(() => undefined); // one quiet check on open, with the server's short cache
          if (live) setData(await googleApi.messages(jobId));
        }
      } catch (e) {
        if (live) setError(errorText(e));
      }
    })();
    return () => {
      live = false;
    };
  }, [connected, thread, jobId]);

  if (!connected) return null;
  const linked = data?.linked ?? thread;

  const run = async (name: string, task: () => Promise<void>) => {
    setBusy(name);
    setError("");
    try {
      await task();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  };

  const check = () =>
    run("check", async () => {
      const r = await googleApi.check(jobId, address.trim(), true);
      setData({ connected: true, linked: r.linked ?? true, messages: r.messages, checked_at: new Date().toISOString() });
      notify(r.new ? `${r.new} new message${r.new === 1 ? "" : "s"}.` : "No new replies.");
    });
  const draft = (m: MailItem) =>
    run("draft", async () => {
      const r = await googleApi.draft(jobId, m.id, false);
      setReply(r.draft);
      setFlags(r.flags.map((f) => f.text));
    });
  const times = () =>
    run("times", async () => {
      const r = await googleApi.times(jobId);
      if (!r.count) throw new Error("No free time found in the next ten days.");
      setReply((old) => (old ? `${old}\n\n${r.text}` : r.text));
    });

  return (
    <>
      <SectionTitle>Replies from your Gmail</SectionTitle>
      <Card>
        {!linked ? (
          <View style={{ marginBottom: 8 }}>
            <Muted style={{ marginBottom: 8 }}>This job is not linked to an email conversation yet. Send the application from here, or type the address the employer writes from to find it.</Muted>
            <Field label="Employer's email address" value={address} onChangeText={setAddress} keyboardType="email-address" autoCapitalize="none" autoCorrect={false} />
          </View>
        ) : null}
        {data && data.messages.length === 0 ? (
          <Muted style={{ marginBottom: 8 }}>{linked ? "No messages saved yet. Press Check for replies." : "Nothing to show yet."}</Muted>
        ) : (
          data?.messages.map((m) => (
            <View key={m.id} style={{ marginBottom: 12 }}>
              <Text>
                <Text style={{ fontWeight: "700" }}>{m.from_me ? "You" : m.sender}</Text> <Text style={{ opacity: 0.7 }}>{dayTimeText(m.sent_at)}</Text>
              </Text>
              {/* A snippet is the employer's text: shown as plain text, never as markup. */}
              <Muted>{m.snippet}</Muted>
              {!m.from_me ? <Button variant="secondary" label="Draft a reply" disabled={busy !== ""} busy={busy === "draft"} onPress={() => draft(m)} style={{ marginTop: 6 }} /> : null}
            </View>
          ))
        )}
        <View style={{ gap: 8 }}>
          <Button variant="secondary" label="Check for replies" busy={busy === "check"} disabled={busy !== "" || (!linked && !address.trim())} onPress={check} />
          <Button variant="secondary" label="Suggest interview times" busy={busy === "times"} disabled={busy !== ""} onPress={times} />
        </View>
        {reply ? (
          <View style={{ marginTop: 14 }}>
            <Field
              label="Your reply (a draft: copy it, change it, then send it from Gmail)"
              value={reply}
              onChangeText={setReply}
              multiline
              style={{ minHeight: 180 }}
              hint={flags.length ? `Check these, we could not find them in your own material: ${flags.join(", ")}.` : "Written from your own material only. It has not been sent."}
            />
            <Button
              variant="secondary"
              label="Copy"
              icon="copy-outline"
              onPress={async () => {
                await Clipboard.setStringAsync(reply);
                notify("Copied.");
              }}
            />
          </View>
        ) : null}
        {error ? (
          <View style={{ marginTop: 10 }}>
            <ErrorBox message={error} />
          </View>
        ) : null}
      </Card>
    </>
  );
}
