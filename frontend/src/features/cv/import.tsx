"use client";

import { useId, useState } from "react";
import { Badge, Button, Card, Notice } from "@/components/ui";
import { CheckField } from "@/components/form";
import { errorText } from "@/lib/api";
import { cvApi } from "./api";
import { acceptAll, applyCards, canFill, initialDecisions, startStep, summaryText, type Decision, type Imported } from "./importlogic";
import type { BuilderAnswers } from "./quality";

const MAX_BYTES = 5 * 1024 * 1024;

/**
 * "I already have a CV": read a file, show one card per section, and fill the builder from the ones the person takes. Nothing is saved:
 * the answers go into the builder, and the CV is only made when they finish it there.
 */
export function ImportPanel({ aiAvailable, current, onFill }: { aiAvailable: boolean; current: BuilderAnswers; onFill: (answers: BuilderAnswers, step: number) => void }) {
  const inputId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [useAi, setUseAi] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Imported | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});

  async function read() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const out = await cvApi.importFile(file, useAi);
      setResult(out);
      setDecisions(initialDecisions(out.cards));
    } catch (e) {
      setResult(null);
      setError(errorText(e, "We could not read that file. Try a PDF, a Word document or a text file."));
    } finally {
      setBusy(false);
    }
  }

  const decide = (key: string, d: Decision) => setDecisions((prev) => ({ ...prev, [key]: d }));
  const label = (d: Decision) => (d === "pending" ? "To decide" : d === "accept" ? "Taken" : d === "edit" ? "Taken, to edit" : "Skipped");

  return (
    <Card>
      <h2 className="mb-1 text-lg font-semibold">Start from a CV you already have</h2>
      <p className="mb-3 text-sm text-muted">
        Choose a PDF, a Word document (.docx), a Markdown file or a text file, up to 5 MB. We sort it into sections for you to check. Nothing is saved until you finish the questions below, and the file itself is not kept.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor={inputId} className="mb-1 block text-sm font-medium">Your CV file</label>
          <input
            id={inputId}
            type="file"
            accept=".pdf,.docx,.md,.markdown,.txt"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setResult(null);
              setError("");
            }}
            className="block max-w-full text-sm"
          />
        </div>
        <Button variant="outline" onClick={read} disabled={!file || busy || (file?.size ?? 0) > MAX_BYTES}>
          {busy ? "Reading…" : "Read my CV"}
        </Button>
      </div>
      {file && file.size > MAX_BYTES && <p role="alert" className="mt-2 text-sm text-bad">That file is larger than 5 MB. A CV is usually well under 1 MB: try a smaller copy.</p>}
      {aiAvailable && (
        <div className="mt-2">
          <CheckField label="Let my AI sort it" hint="Your own AI sorts the text into sections. It can only use words that are in your file; anything else it suggests is thrown away." checked={useAi} onChange={(e) => setUseAi(e.target.checked)} />
        </div>
      )}
      <div aria-live="polite">
        {error && (
          <div className="mt-3">
            <Notice tone="error">{error}</Notice>
          </div>
        )}
        {result && (
          <div className="mt-4">
            <p className="mb-2 text-sm font-medium">
              {result.method === "ai" ? "Sorted by your AI." : "Sorted by plain rules, with no AI."} Check each section: accept it, edit it in the questions, or skip it.
            </p>
            {result.notes.map((n) => (
              <p key={n} className="mb-2 text-sm text-muted">{n}</p>
            ))}
            <ul className="space-y-3">
              {result.cards.map((c) => {
                const d = decisions[c.key] ?? "skip";
                return (
                  <li key={c.key} className="rounded-lg border border-border p-3" aria-label={c.label}>
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <h3 className="mr-auto font-semibold">{c.label}</h3>
                      {c.found ? <Badge tone={d === "skip" ? "muted" : d === "pending" ? "warn" : "good"}>{label(d)}</Badge> : <Badge>Not found</Badge>}
                    </div>
                    {c.found ? (
                      <>
                        <ul className="mb-2 list-disc pl-5 text-sm">
                          {c.preview.map((line, i) => (
                            <li key={i} className="break-words">{line}</li>
                          ))}
                        </ul>
                        {c.more > 0 && <p className="mb-2 text-xs text-muted">and {c.more} more</p>}
                        <div className="flex flex-wrap gap-2">
                          <Button small variant={d === "accept" ? "primary" : "outline"} aria-pressed={d === "accept"} onClick={() => decide(c.key, "accept")}>Accept</Button>
                          <Button small variant={d === "edit" ? "primary" : "outline"} aria-pressed={d === "edit"} onClick={() => decide(c.key, "edit")}>Edit</Button>
                          <Button small variant={d === "skip" ? "primary" : "outline"} aria-pressed={d === "skip"} onClick={() => decide(c.key, "skip")}>Skip</Button>
                        </div>
                      </>
                    ) : (
                      <p className="text-sm text-muted">We did not find this in your file. You can add it in the questions below.</p>
                    )}
                  </li>
                );
              })}
            </ul>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button variant="outline" onClick={() => setDecisions(acceptAll(result.cards))}>Accept all</Button>
              <Button onClick={() => onFill(applyCards(current, result.cards, decisions), startStep(result.cards, decisions))} disabled={!canFill(decisions)}>
                Fill the questions
              </Button>
              <span className="text-sm text-muted">{summaryText(decisions)}</span>
            </div>
            <p className="mt-2 text-xs text-muted">Edit fills that section and opens the questions at it, so you can change it there.</p>
          </div>
        )}
      </div>
    </Card>
  );
}
