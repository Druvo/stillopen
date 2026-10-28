"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { TextAreaField, TextField } from "@/components/form";
import { Button, Card, Notice } from "@/components/ui";
import { appliedMessage } from "@/features/jobs/logic";
import { errorText } from "@/lib/api";
import { Link, navigate } from "@/lib/router";
import { notify } from "@/lib/toast";
import { googleApi, type Preview } from "./api";

type Props = {
  jobId: number;
  connected: boolean;
  available: boolean;
  suggestedTo: string;
  draft: { subject: string; body: string };
  cv: number | null;
  cover: number | null;
};

const size = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

/**
 * "Send from my Gmail". Nothing is sent before the last step: write (or edit) the message, see it exactly as it will go (the server describes it
 * and gives back a fingerprint), then press Send. Changing anything after the preview throws the preview away.
 */
export function SendFromGmail({ jobId, connected, available, suggestedTo, draft, cv, cover }: Props) {
  const client = useQueryClient();
  const [to, setTo] = useState(suggestedTo);
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const edit = (set: (v: string) => void) => (e: { target: { value: string } }) => {
    set(e.target.value);
    setPreview(null);
  };
  const message = { to, subject, body, cv, cover };

  if (!available) return null;
  if (!connected) {
    return (
      <Card className="mb-3">
        <h3 className="font-semibold">Send from my Gmail</h3>
        <p className="text-sm text-muted">
          Connect your Google account to send this from your own Gmail and see the replies here.{" "}
          <Link to="/profile/connections" className="text-brand underline">
            Connect Google
          </Link>
        </p>
      </Card>
    );
  }

  async function look() {
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
  }

  async function send() {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      const done = await googleApi.send(jobId, message, preview.digest);
      await Promise.all([client.invalidateQueries({ queryKey: ["dashboard"] }), client.invalidateQueries({ queryKey: ["apply", jobId] })]);
      notify(`Sent to ${done.to}. ${appliedMessage(done.follow_up_date)}`);
      navigate("/");
    } catch (e) {
      setError(errorText(e));
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-3" onKeyDown={(e) => { if (e.key === "Enter" && e.target instanceof HTMLInputElement) e.preventDefault(); }}>
      <h3 className="font-semibold">Send from my Gmail</h3>
      <p className="mb-2 text-sm text-muted">Nothing is sent until you have looked at the whole message and pressed Send. The CV you chose above is attached as a Word file.</p>
      <TextField
        label="Send to"
        type="email"
        value={to}
        onChange={edit(setTo)}
        hint={suggestedTo && to === suggestedTo ? "This is the address the posting itself gives. Check it is the right one." : "Type the address you are applying to."}
        autoComplete="off"
      />
      <TextField label="Subject" value={subject} onChange={edit(setSubject)} maxLength={200} />
      <TextAreaField label="Message" rows={10} value={body} onChange={edit(setBody)} hint="Replace [Your name] and check every statement is true." />
      {!preview && (
        <Button variant="outline" disabled={busy || !to.trim()} onClick={look}>
          {busy ? "Checking…" : "Preview the email"}
        </Button>
      )}
      {preview && (
        <section className="mt-3 rounded-md border border-border p-3" aria-label="The email exactly as it will be sent">
          <p className="text-sm">
            <strong>From:</strong> {preview.from || "your Gmail"}
          </p>
          <p className="text-sm">
            <strong>To:</strong> {preview.to}
          </p>
          <p className="text-sm">
            <strong>Subject:</strong> {preview.subject}
          </p>
          <p className="mt-1 whitespace-pre-wrap text-sm">{preview.body}</p>
          <p className="mt-2 text-sm">
            <strong>Attached:</strong> {preview.attachments.length ? preview.attachments.map((a) => `${a.name} (${size(a.bytes)})`).join(", ") : "nothing"}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button disabled={busy} onClick={send}>
              {busy ? "Sending…" : `Send to ${preview.to}`}
            </Button>
            <Button variant="ghost" disabled={busy} onClick={() => setPreview(null)}>
              Keep editing
            </Button>
          </div>
        </section>
      )}
      {error && (
        <p role="alert" className="mt-2 text-sm text-bad">
          {error}
        </p>
      )}
      {cv === null && <Notice>No CV is chosen above, so nothing will be attached.</Notice>}
    </Card>
  );
}
