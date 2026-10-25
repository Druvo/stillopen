"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { SelectField, TextAreaField, TextField } from "@/components/form";
import { Button, Card } from "@/components/ui";
import { extrasApi } from "@/features/assist/extras-api";
import { findingsText, messageText } from "@/features/assist/logic";
import { AiNotice, CopyButton, NoKeyLine, ProblemLine } from "@/features/assist/ui";
import { errorText } from "@/lib/api";
import { canCompare, compareHint } from "./compare-logic";
import type { Offer } from "./api";

/**
 * "Compare these offers in words": the differences per currency (never converted), what to ask each employer about, and, with the person's
 * own AI key, a short counter-offer note that states only numbers they entered. Nothing is saved or sent.
 */
export function CompareInWords({ offers, selected, onClear }: { offers: Offer[]; selected: number[]; onClear: () => void }) {
  const chosen = offers.filter((o) => selected.includes(o.id));
  const [focus, setFocus] = useState<number | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const run = useMutation({
    mutationFn: () => extrasApi.compareOffers(selected, focus && selected.includes(focus) ? focus : null),
    onSuccess: (data) => {
      setSubject(data.counter_note?.subject ?? "");
      setBody(data.counter_note?.body ?? "");
    },
  });
  const note = run.data;
  const ready = canCompare(selected);
  return (
    <Card className="mb-4" aria-labelledby="compare-heading">
      <h2 id="compare-heading" className="mb-1 font-semibold">
        Compare these offers in words
      </h2>
      <p className="mb-3 text-sm text-muted" data-testid="compare-hint">
        {compareHint(selected.length)} Offers in different currencies are compared within each currency and never converted.
      </p>
      {chosen.length >= 2 && (
        <SelectField label="If you want a counter-offer note, it is about" value={String(focus ?? chosen[0].id)} onChange={(e) => setFocus(Number(e.target.value))} className="max-w-sm">
          {chosen.map((o) => (
            <option key={o.id} value={o.id}>
              {o.job.company} - {o.job.role}
            </option>
          ))}
        </SelectField>
      )}
      <div className="flex flex-wrap gap-2">
        <Button disabled={!ready || run.isPending} onClick={() => run.mutate()}>
          {run.isPending ? "Reading your offers…" : "Compare these offers in words"}
        </Button>
        {selected.length > 0 && (
          <Button variant="ghost" onClick={onClear}>
            Clear ticks
          </Button>
        )}
      </div>
      <ProblemLine message={run.isError ? errorText(run.error) : ""} />
      {note && (
        <div className="mt-4 space-y-4" data-testid="compare-result">
          <section aria-labelledby="differences-heading">
            <h3 id="differences-heading" className="mb-1 font-medium">
              The differences
            </h3>
            {note.differences.map((d) => (
              <div key={d.currency} className="mb-2">
                <p className="text-sm font-medium">In {d.currency}</p>
                <ul className="list-disc space-y-1 pl-5 text-sm">
                  {d.lines.map((l) => (
                    <li key={l}>{l}</li>
                  ))}
                </ul>
              </div>
            ))}
          </section>
          <section aria-labelledby="ask-heading">
            <h3 id="ask-heading" className="mb-1 font-medium">
              What to ask about
            </h3>
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {note.ask_about.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </section>
          <section aria-labelledby="counter-heading">
            <h3 id="counter-heading" className="mb-1 font-medium">
              A counter-offer note
            </h3>
            {!note.ai && <NoKeyLine />}
            {note.counter_note && (
              <div>
                <TextField label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
                <TextAreaField label="Message" rows={9} value={body} onChange={(e) => setBody(e.target.value)} />
                {note.counter_note.flagged_count > 0 && (
                  <p role="status" className="mb-2 rounded-md border border-warn p-2 text-sm">
                    The AI added things you did not give it: {findingsText(note.counter_note.flagged)}. Remove them unless they are true.
                  </p>
                )}
                <CopyButton text={messageText({ subject, body })} label="Copy the note" small={false} />
                <p className="mt-2 text-xs text-muted">It names no figure you did not enter. Add your own numbers only if you want to ask for something specific. It is never sent for you.</p>
                <AiNotice>{note.notice}</AiNotice>
              </div>
            )}
          </section>
        </div>
      )}
    </Card>
  );
}
