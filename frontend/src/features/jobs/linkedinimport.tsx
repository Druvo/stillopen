"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Button, Card, Notice } from "@/components/ui";
import { errorText } from "@/lib/api";
import { navigate } from "@/lib/router";
import { notify } from "@/lib/toast";
import { jobsApi, type ImportReport } from "./api";
import { fileCountsLine, isLinkedinFile } from "./importlogic";
import { importHeadline } from "./jobmgmt";

const MAX_ZIP = 25 * 1024 * 1024;

/** "Import your LinkedIn jobs": the person's own LinkedIn data export (the zip, or its Saved Jobs / Job Applications files). Nothing is added until they confirm. */
export function LinkedinImportCard() {
  const client = useQueryClient();
  const inputId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function choose(next: File | null) {
    setFile(next);
    setReport(null);
    setError("");
    if (next && !isLinkedinFile(next.name)) setError("Choose the zip LinkedIn sent you, or its Saved Jobs or Job Applications file.");
    else if (next && next.size > MAX_ZIP) setError("That file is bigger than 25 MB. Ask LinkedIn for only the Jobs part of your data, or choose just the two CSV files from the zip.");
  }

  async function run(preview: boolean) {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const result = await jobsApi.importCsv(file, preview);
      if (preview) {
        setReport(result);
      } else {
        await Promise.all([client.invalidateQueries({ queryKey: ["dashboard"] }), client.invalidateQueries({ queryKey: ["stats"] })]);
        notify(importHeadline(result) + (result.stopped ? ` ${result.stopped}` : ""), result.stopped ? "info" : "success");
        navigate("/");
        return;
      }
    } catch (e) {
      setReport(null);
      setError(errorText(e, "We could not read that file."));
    }
    setBusy(false);
  }

  const bad = !!file && (!isLinkedinFile(file.name) || file.size > MAX_ZIP);
  return (
    <Card className="mb-4" role="region" aria-labelledby="linkedin-import-title">
      <h2 id="linkedin-import-title" className="font-semibold">
        Import your LinkedIn jobs
      </h2>
      <p className="mt-1 text-sm text-muted">
        LinkedIn lets you download a copy of your own data. It includes the jobs you saved and the applications you sent, and we can bring both in. We only read the company, job title, link and date. Your contact email, phone number, résumé name and any answers to
        application questions are never read or kept.
      </p>
      <ol className="mt-2 list-decimal pl-5 text-sm text-muted">
        <li>
          On LinkedIn, open <strong>Settings</strong>, then <strong>Data privacy</strong>, then <strong>Get a copy of your data</strong>.
        </li>
        <li>
          Choose <strong>Jobs</strong> (or everything) and press <strong>Request archive</strong>.
        </li>
        <li>LinkedIn emails you a download link. This can take a few minutes, or up to a day.</li>
        <li>
          Download the zip and choose it below. You can also choose just <em>Saved Jobs.csv</em> or <em>Job Applications.csv</em> from inside it.
        </li>
      </ol>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <div className="min-w-0">
          <label htmlFor={inputId} className="mb-1 block text-sm font-medium">
            Your LinkedIn download (.zip or .csv)
          </label>
          <input id={inputId} type="file" accept=".zip,.csv,application/zip,text/csv" onChange={(e) => choose(e.target.files?.[0] ?? null)} className="block max-w-full text-sm" />
        </div>
        <Button variant="outline" onClick={() => run(true)} disabled={!file || busy || bad}>
          {busy && !report ? "Reading…" : "Check the file"}
        </Button>
      </div>
      {error && (
        <div className="mt-3">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
      {report && (
        <div className="mt-4" aria-live="polite">
          <p className="font-medium">{importHeadline(report)}</p>
          <ul className="mt-1 list-disc pl-5 text-sm">
            {(report.files ?? []).map((f) => (
              <li key={f.name}>{fileCountsLine(f)}</li>
            ))}
          </ul>
          {!!report.ignored_files && <p className="mt-1 text-xs text-muted">{report.ignored_files} other files in the download were ignored and not opened.</p>}
          {report.privacy && <p className="mt-1 text-xs text-muted">{report.privacy}</p>}
          {report.stopped && (
            <div className="mt-2">
              <Notice tone="error">{report.stopped}</Notice>
            </div>
          )}
          {report.problems.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-sm">
              {report.problems.map((p) => (
                <li key={p.message}>{p.message}</li>
              ))}
            </ul>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            {report.will_add > 0 ? (
              <Button onClick={() => run(false)} disabled={busy}>
                {busy ? "Adding…" : `Add ${report.will_add} ${report.will_add === 1 ? "job" : "jobs"}`}
              </Button>
            ) : (
              <p className="text-sm text-muted">There is nothing new to add from this file.</p>
            )}
            <Button variant="ghost" onClick={() => choose(null)} disabled={busy}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
