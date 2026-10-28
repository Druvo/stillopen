"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Button, Notice } from "@/components/ui";
import { errorText } from "@/lib/api";
import { notify } from "@/lib/toast";
import { accountApi, type DataImportReport } from "./api";
import { importLines } from "./data-import-logic";

const MAX_BYTES = 8 * 1024 * 1024;

/** "Add an export back": choose the file from "Export my data", see what would be added, then confirm. Nothing already in the account is changed. */
export function DataImportCard() {
  const client = useQueryClient();
  const inputId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<DataImportReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function choose(next: File | null) {
    setFile(next);
    setReport(null);
    setError(next && next.size > MAX_BYTES ? "That file is bigger than 8 MB, so it is not one of our exports." : "");
  }

  async function run(preview: boolean) {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const done = await accountApi.importData(file, preview);
      if (preview) {
        setReport(done);
      } else {
        await client.invalidateQueries();
        notify("Your export was added back. Nothing that was already here was changed.");
        choose(null);
      }
    } catch (e) {
      setReport(null);
      setError(errorText(e, "We could not read that file. Nothing was changed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mt-5 border-t border-border pt-4" aria-labelledby="data-import-title">
      <h3 id="data-import-title" className="font-semibold">
        Add an export back
      </h3>
      <p className="mt-1 text-sm text-muted">
        Choose a file you downloaded from this account with the button above. We show what would be added first. Your profile answers, CV versions, cover letters and job notes are added only where you do not already have them, and nothing you have now is changed.
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <div className="min-w-0">
          <label htmlFor={inputId} className="mb-1 block text-sm font-medium">
            Your export file (.json)
          </label>
          <input id={inputId} type="file" accept=".json,application/json" onChange={(e) => choose(e.target.files?.[0] ?? null)} className="block max-w-full text-sm" />
        </div>
        <Button variant="outline" onClick={() => run(true)} disabled={!file || busy || (file?.size ?? 0) > MAX_BYTES}>
          {busy && !report ? "Reading…" : "Check the file"}
        </Button>
      </div>
      {error && (
        <div className="mt-3">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
      {report && (
        <div className="mt-3" aria-live="polite">
          <ul className="list-disc pl-5 text-sm">
            {importLines(report).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap gap-2">
            {report.nothing ? (
              <p className="text-sm text-muted">There is nothing new to add from this file.</p>
            ) : (
              <Button onClick={() => run(false)} disabled={busy}>
                {busy ? "Adding…" : "Add these"}
              </Button>
            )}
            <Button variant="ghost" onClick={() => choose(null)} disabled={busy}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
