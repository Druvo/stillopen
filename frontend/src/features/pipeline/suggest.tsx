"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Notice } from "@/components/ui";
import { api, errorText } from "@/lib/api";
import { notify } from "@/lib/toast";
import { moveText } from "@/features/jobs/jobmgmt";
import type { Saved } from "./api";

export type Suggestion = { jobId: number; status: NonNullable<Saved["suggest_status"]> };

/**
 * "Move this job to Interview?" after an interview or an offer was saved for a job that is still earlier in the process.
 * One tap does it; nothing is ever moved without that tap.
 */
export function SuggestMove({ suggestion, onDone }: { suggestion: Suggestion; onDone: () => void }) {
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function move() {
    setBusy(true);
    setError("");
    try {
      await api.setStatus(suggestion.jobId, suggestion.status.id);
      void client.invalidateQueries({ queryKey: ["dashboard"] });
      void client.invalidateQueries({ queryKey: ["job-history", suggestion.jobId] });
      notify(`Moved to ${suggestion.status.label}.`);
      onDone();
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }
  return (
    <Notice>
      <p className="font-medium">{moveText(suggestion.status.label)}</p>
      <p className="mt-0.5 text-muted">Its status still says it is earlier than that. Moving it keeps your dashboard and numbers in step.</p>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button small onClick={move} disabled={busy}>
          {busy ? "Moving…" : `Move this job to ${suggestion.status.label}`}
        </Button>
        <Button small variant="ghost" onClick={onDone} disabled={busy}>
          Not now
        </Button>
      </div>
      {error && (
        <p role="alert" className="mt-2 text-bad">
          {error}
        </p>
      )}
    </Notice>
  );
}
