"use client";

import { dayTimeText } from "@/lib/dates";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { TextAreaField, TextField } from "@/components/form";
import { Button, Card } from "@/components/ui";
import { errorText } from "@/lib/api";
import { notify } from "@/lib/toast";
import { googleApi, type MailItem } from "./api";

const when = (iso: string) => dayTimeText(iso);

/**
 * Replies next to the job: the saved conversation as a small timeline (React escapes every snippet), a manual "Check for replies", a draft
 * reply the person edits, and three free interview times to paste. Opening the screen checks once, with the server's short cache. Nothing here sends.
 */
export function JobMail({ jobId, connected, thread }: { jobId: number; connected: boolean; thread: boolean }) {
  const client = useQueryClient();
  const key = ["google", "messages", jobId];
  const query = useQuery({ queryKey: key, queryFn: () => googleApi.messages(jobId), enabled: connected, staleTime: 0 });
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [reply, setReply] = useState("");
  const [flags, setFlags] = useState<string[]>([]);

  useEffect(() => {
    if (!connected || !thread) return;
    googleApi
      .check(jobId, "", false)
      .then(() => client.invalidateQueries({ queryKey: ["google", "messages", jobId] }))
      .catch(() => undefined);
  }, [connected, thread, jobId, client]);

  if (!connected) return null;
  const data = query.data;
  const linked = data?.linked ?? thread;

  async function run(name: string, task: () => Promise<void>) {
    setBusy(name);
    setError("");
    try {
      await task();
    } catch (e) {
      setError(errorText(e, e instanceof Error ? e.message : undefined));
    } finally {
      setBusy("");
    }
  }

  const check = () =>
    run("check", async () => {
      const r = await googleApi.check(jobId, address.trim(), true);
      client.setQueryData(key, { connected: true, linked: r.linked ?? true, messages: r.messages, checked_at: new Date().toISOString() });
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
    <Card className="mb-3">
      <h2 className="mb-1 text-lg font-semibold">Replies from your Gmail</h2>
      {!linked && (
        <div className="mb-2 text-sm text-muted">
          <p>This job is not linked to an email conversation yet. Send the application from here, or type the address the employer writes from to find it.</p>
          <TextField label="Employer's email address" type="email" value={address} onChange={(e) => setAddress(e.target.value)} className="max-w-sm" />
        </div>
      )}
      {data && data.messages.length === 0 ? (
        <p className="mb-2 text-sm text-muted">{linked ? "No messages saved yet. Press Check for replies." : "Nothing to show yet."}</p>
      ) : (
        <ol className="mb-2 border-l border-border pl-3">
          {data?.messages.map((m) => (
            <li key={m.id} className="mb-2 text-sm">
              <span className="font-medium">{m.from_me ? "You" : m.sender}</span> <span className="text-muted">{when(m.sent_at)}</span>
              <p className="whitespace-pre-wrap text-muted">{m.snippet}</p>
              {!m.from_me && (
                <Button variant="outline" small disabled={busy !== ""} onClick={() => draft(m)}>
                  Draft a reply
                </Button>
              )}
            </li>
          ))}
        </ol>
      )}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" disabled={busy !== "" || (!linked && !address.trim())} onClick={check}>
          {busy === "check" ? "Checking…" : "Check for replies"}
        </Button>
        <Button variant="outline" disabled={busy !== ""} onClick={times}>
          {busy === "times" ? "Looking at your calendar…" : "Suggest interview times"}
        </Button>
      </div>
      {reply && (
        <div className="mt-3">
          <TextAreaField
            label="Your reply (a draft: copy it, change it, then send it from Gmail)"
            rows={9}
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            hint={flags.length ? `Check these, we could not find them in your own material: ${flags.join(", ")}.` : "Written from your own material only. It has not been sent."}
          />
          <Button variant="outline" small onClick={() => navigator.clipboard?.writeText(reply).then(() => notify("Copied."))}>
            Copy
          </Button>
        </div>
      )}
      {(error || query.isError) && (
        <p role="alert" className="mt-2 text-sm text-bad">
          {error || errorText(query.error)}
        </p>
      )}
    </Card>
  );
}
