"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Button, Card, Loading, Notice } from "@/components/ui";
import { errorText } from "@/lib/api";
import { Link, navigate } from "@/lib/router";
import { announce } from "@/lib/toast";
import { coverApi, cvApi, type RefineMessage } from "./api";
import { findingText, type Finding } from "./logic";

const IDEAS = ["Make it shorter", "Less formal", "Lead with my strongest work", "Use plainer words"];

/**
 * "Ask for changes": type what you want different, the AI sends back a revised copy, which is fact-checked like a tailored one. On a CV it
 * becomes a new version (this screen then opens it); on a cover letter the text changes here and Undo takes it back. Loaded only when opened.
 * `flagged` are the lines of the current text that the fact check could not find in your own material, shown here before you approve.
 */
export default function RefinePanel({ kind, id, flagged }: { kind: "cv" | "cover"; id: number; flagged: Finding[] }) {
  const client = useQueryClient();
  const api = kind === "cv" ? cvApi : coverApi;
  const key = ["refine", kind, id] as const;
  const query = useQuery({ queryKey: key, queryFn: () => api.refineState(id) });
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const log = useRef<HTMLUListElement>(null);
  const messages: RefineMessage[] = query.data?.messages ?? [];
  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight });
  }, [messages.length]);

  if (query.isPending) return <Loading what="the chat" />;
  if (query.isError) return <Notice tone="error">{errorText(query.error)}</Notice>;
  const state = query.data;
  if (!state.ai.available) {
    return (
      <Notice>
        {state.ai.missing_message} <Link to="/profile/ai" className="link-target text-brand underline">Set up AI first</Link>
      </Notice>
    );
  }
  const canUndo = kind === "cv" ? Boolean(state.undo_to) : Boolean(state.can_undo);
  const fresh = () => {
    client.invalidateQueries({ queryKey: [kind === "cv" ? "cv" : "cover"] });
  };

  async function send(message: string) {
    if (!message.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      if (kind === "cv") {
        const r = await cvApi.refine(id, message);
        client.setQueryData(["refine", "cv", r.id], { ai: state.ai, messages: r.messages, undo_to: r.undo_to });
        announce(`${r.summary} ${r.flagged_count ? `${r.flagged_count} lines need your check before you approve.` : "Nothing to check."} Opening the new version.`);
        setText("");
        fresh();
        navigate(`/cv/${r.id}`);
      } else {
        const r = await coverApi.refine(id, message);
        client.setQueryData(key, { ai: state.ai, messages: r.messages, can_undo: r.can_undo });
        client.setQueryData(["cover", id], r.letter);
        announce(`${r.summary} ${r.letter.flagged_count ? `${r.letter.flagged_count} lines need your check before you approve.` : "Nothing to check."}`);
        setText("");
      }
    } catch (e) {
      setError(errorText(e));
      announce(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function undo() {
    setBusy(true);
    setError("");
    try {
      if (kind === "cv") {
        const r = await cvApi.refineUndo(id);
        announce("Went back to the version before the change.");
        navigate(`/cv/${r.id}`);
      } else {
        const r = await coverApi.refineUndo(id);
        client.setQueryData(key, { ai: state.ai, messages: r.messages, can_undo: r.can_undo });
        client.setQueryData(["cover", id], r.letter);
        announce(r.summary);
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {messages.length === 0 ? (
        <p className="text-sm text-muted">
          Tell the AI what you would like different and it sends back a new copy. It can only use what is already in your own CV and documents,
          and anything it adds that is not there is flagged for you to check. {kind === "cv" ? "Your current version is kept." : "You can undo the change."}
        </p>
      ) : (
        <ul ref={log} aria-label="Earlier requests" tabIndex={0} className="max-h-64 space-y-2 overflow-y-auto rounded-lg border border-border p-2 text-sm">
          {messages.map((m) => (
            <li key={m.id} className={m.role === "user" ? "text-right" : ""}>
              <span className="sr-only">{m.role === "user" ? "You: " : "AI: "}</span>
              <span className={m.role === "user" ? "inline-block rounded-lg bg-brand/10 px-2 py-1" : "inline-block px-2 py-1"}>{m.text}</span>
              {m.role === "assistant" && m.flagged_count > 0 && <span className="ml-1 text-theme-xs text-muted">({m.flagged_count} to check)</span>}
              {m.role === "assistant" && m.result_id && kind === "cv" && m.result_id !== id && (
                <Link to={`/cv/${m.result_id}`} className="link-target ml-2 text-theme-xs text-brand underline">Open that version</Link>
              )}
            </li>
          ))}
        </ul>
      )}
      {flagged.length > 0 && (
        <Card className="border-warn text-sm">
          <p className="font-semibold">Check these before you use it. They are not in your own CV or documents.</p>
          <ul className="ml-5 list-disc">
            {flagged.map((f, i) => (
              <li key={i}>
                {findingText(f)} <span className="text-muted">(line {f.line})</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {error && <Notice tone="error">{error}</Notice>}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send(text);
        }}
        className="space-y-2"
      >
        <label htmlFor={`refine-${kind}`} className="block text-sm font-medium">What would you like changed?</label>
        <textarea
          id={`refine-${kind}`}
          value={text}
          maxLength={600}
          rows={2}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              void send(text);
            }
          }}
          aria-describedby={`refine-hint-${kind}`}
          className="w-full rounded-lg border border-border bg-transparent p-2 text-sm"
          placeholder="For example: make it shorter"
        />
        <p id={`refine-hint-${kind}`} className="text-theme-xs text-muted">Press Ctrl+Enter to send. Up to 600 characters.</p>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" disabled={busy || !text.trim()}>{busy ? "Working on it…" : "Send"}</Button>
          {canUndo && <Button type="button" variant="outline" disabled={busy} onClick={() => void undo()}>Undo the last change</Button>}
          {IDEAS.map((idea) => (
            <button key={idea} type="button" disabled={busy} className="link-target rounded-full border border-border px-2 py-1 text-theme-xs" onClick={() => void send(idea)}>
              {idea}
            </button>
          ))}
        </div>
      </form>
    </div>
  );
}
