"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { TextAreaField } from "@/components/form";
import { Button, Card, Notice } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { notify } from "@/lib/toast";
import { jobsApi, type ReplyReading } from "./api";
import { confidenceText, statusWord, suggestionButton } from "./jobmgmt";

const MAX_CHARS = 20000;

/**
 * "Got a reply? Paste it here." The email is read with fixed phrase lists on the server (no AI, nothing stored), and the answer is only a
 * suggestion with the exact sentences it is based on. The status changes, and "Reply pasted: ..." goes into the timeline, only when the person
 * presses the button.
 */
export function ReplyPaste({ jobId, currentStatusId }: { jobId: number; currentStatusId?: number }) {
  const client = useQueryClient();
  const [text, setText] = useState("");
  const [reading, setReading] = useState<ReplyReading | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function read() {
    setBusy(true);
    setError("");
    setReading(null);
    try {
      setReading(await jobsApi.replyParse(jobId, text));
    } catch (e) {
      setError(errorText(e, "We could not read that."));
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    const suggestion = reading?.suggestion;
    if (!suggestion) return;
    setBusy(true);
    setError("");
    try {
      await api.setStatus(jobId, suggestion.status.id, suggestion.quotes[0] ?? "");
      await Promise.all([
        client.invalidateQueries({ queryKey: ["dashboard"] }),
        client.invalidateQueries({ queryKey: ["apply", jobId] }),
        client.invalidateQueries({ queryKey: ["job-history", jobId] }),
      ]);
      notify(`Status set to ${statusWord(suggestion.status)}. The sentence it was based on is in the job's history.`);
      setReading(null);
      setText("");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const suggestion = reading?.suggestion ?? null;
  return (
    <Card className="mt-6" role="region" aria-labelledby="reply-title">
      <h2 id="reply-title" className="text-lg font-semibold">
        Got a reply? Paste it here
      </h2>
      <p className="mb-3 mt-1 text-sm text-muted">
        Paste the email from the employer and we will suggest where this job now stands. We only read it: nothing is saved, nothing changes until you say so, and it is never sent anywhere.
      </p>
      <TextAreaField
        label="The email you got"
        rows={6}
        maxLength={MAX_CHARS}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setReading(null);
        }}
        hint="English emails only."
      />
      <Button variant="outline" onClick={read} disabled={busy || !text.trim()}>
        {busy && !reading ? "Reading…" : "Read it"}
      </Button>
      {error && (
        <div className="mt-3">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
      {reading && (
        <div className="mt-3" aria-live="polite">
          {suggestion ? (
            <Notice>
              <p className="font-medium">
                {confidenceText(suggestion.confidence, suggestion.mixed)}{" "}
                <span className="text-brand">{statusWord(suggestion.status)}</span>
              </p>
              {suggestion.quotes.length > 0 && (
                <>
                  <p className="mt-2 text-muted">It says:</p>
                  {suggestion.quotes.map((q) => (
                    <blockquote key={q} className="mt-1 border-l-2 border-border pl-3 italic">
                      {q}
                    </blockquote>
                  ))}
                </>
              )}
              {suggestion.already || suggestion.status.id === currentStatusId ? (
                <p className="mt-2 text-muted">This job is already set to {statusWord(suggestion.status)}, so there is nothing to change.</p>
              ) : (
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button onClick={confirm} disabled={busy}>
                    {busy ? "Saving…" : suggestionButton(suggestion.status)}
                  </Button>
                  <Button variant="ghost" onClick={() => setReading(null)} disabled={busy}>
                    No, leave it
                  </Button>
                </div>
              )}
            </Notice>
          ) : (
            <Notice>{reading.message}</Notice>
          )}
          {reading.truncated && <p className="mt-2 text-xs text-muted">The message was very long, so only the start was read.</p>}
        </div>
      )}
    </Card>
  );
}
