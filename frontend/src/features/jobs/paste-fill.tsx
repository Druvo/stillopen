"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Notice } from "@/components/ui";
import { extrasApi, type ParsedFields } from "@/features/assist/extras-api";
import { errorText } from "@/lib/api";
import { filledMessage } from "./paste";

/**
 * "Fill the form from pasted text", under the job description box on Add job. It reads the pasted posting with plain rules (and, when the
 * person has an AI key, asks it only about what the rules could not find). Nothing is saved: the person checks every field and presses Save.
 * `onFields` lays the fields over the form and returns the plain-words list of what it filled.
 */
export function PasteFill({ text, onFields }: { text: string; onFields: (fields: ParsedFields) => string[] }) {
  const [message, setMessage] = useState("");
  const read = useMutation({
    mutationFn: () => extrasApi.parseText(text),
    onMutate: () => setMessage(""),
    onSuccess: (data) => setMessage(filledMessage(onFields(data.fields), data.notice)),
  });
  const short = text.trim().length < 20;
  return (
    <div className="mb-3" data-testid="paste-fill">
      <Button variant="outline" disabled={read.isPending || short} onClick={() => read.mutate()}>
        {read.isPending ? "Reading…" : "Fill the form from pasted text"}
      </Button>
      {short && <p className="mt-1 text-xs text-muted">Paste the job text in the box above first, then press this.</p>}
      {read.isError && (
        <p role="alert" className="mt-2 text-sm text-bad">
          {errorText(read.error)}
        </p>
      )}
      {message && (
        <div className="mt-2">
          <Notice>{message}</Notice>
        </div>
      )}
    </div>
  );
}
