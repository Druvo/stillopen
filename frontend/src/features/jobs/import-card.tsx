"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";
import { Button, buttonClass, Card, Notice } from "@/components/ui";
import { errorText } from "@/lib/api";
import { navigate } from "@/lib/router";
import { notify } from "@/lib/toast";
import { jobsApi, type ImportReport } from "./api";
import { CSV_EXPORT_URL, importHeadline } from "./jobmgmt";

const MAX_BYTES = 1024 * 1024;

/**
 * "Import from a spreadsheet": choose a CSV file, see exactly what would be added (and what is skipped or cannot be read), then confirm.
 * Nothing is added by the first step, and no link in the file is ever opened.
 */
export function ImportCard() {
  const client = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function choose(next: File | null) {
    setFile(next);
    setReport(null);
    setError("");
    if (next && next.size > MAX_BYTES) setError("That file is bigger than 1 MB. Split it into smaller files, or remove columns you do not need.");
  }

  async function check() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      setReport(await jobsApi.importCsv(file, true));
    } catch (e) {
      setReport(null);
      setError(errorText(e, "We could not read that file."));
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const done = await jobsApi.importCsv(file, false);
      await Promise.all([client.invalidateQueries({ queryKey: ["dashboard"] }), client.invalidateQueries({ queryKey: ["stats"] })]);
      notify(importHeadline(done) + (done.stopped ? ` ${done.stopped}` : ""), done.stopped ? "info" : "success");
      navigate("/");
    } catch (e) {
      setError(errorText(e, "The import did not work. Nothing was added."));
      setBusy(false);
    }
  }

  return (
    <Card className="mb-4" role="region" aria-labelledby="import-title">
      <h2 id="import-title" className="font-semibold">
        Import from a spreadsheet
      </h2>
      <p className="mt-1 text-sm text-muted">
        Keeping your jobs in Excel or Google Sheets? Save the sheet as <strong>CSV</strong> and choose it here. It needs a header row with at least <strong>Company</strong> and <strong>Role</strong>. We also use Link, Status, Date applied,
        Follow up, Deadline, Location, Country and Notes when they are there. We never open the links in your file.
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <div className="min-w-0">
          <label htmlFor={inputId} className="mb-1 block text-sm font-medium">
            Your CSV file
          </label>
          <input ref={input} id={inputId} type="file" accept=".csv,text/csv" onChange={(e) => choose(e.target.files?.[0] ?? null)} className="block max-w-full text-sm" />
        </div>
        <Button variant="outline" onClick={check} disabled={!file || busy || (file?.size ?? 0) > MAX_BYTES}>
          {busy && !report ? "Reading…" : "Check the file"}
        </Button>
        <a href={CSV_EXPORT_URL} download className={buttonClass("ghost")}>
          Export my jobs (CSV)
        </a>
      </div>
      {error && (
        <div className="mt-3">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
      {report && <Preview report={report} busy={busy} onConfirm={confirm} onCancel={() => choose(null)} />}
    </Card>
  );
}

function Preview({ report, busy, onConfirm, onCancel }: { report: ImportReport; busy: boolean; onConfirm: () => void; onCancel: () => void }) {
  return (
    <div className="mt-4" aria-live="polite">
      <p className="font-medium">{importHeadline(report)}</p>
      {report.stopped && (
        <div className="mt-2">
          <Notice tone="error">{report.stopped}</Notice>
        </div>
      )}
      {report.rows.length > 0 && (
        <div className="mt-2 max-h-72 overflow-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Jobs that will be added</caption>
            <thead className="sticky top-0 bg-surface-2">
              <tr>
                <th scope="col" className="px-2 py-1.5">Row</th>
                <th scope="col" className="px-2 py-1.5">Company</th>
                <th scope="col" className="px-2 py-1.5">Role</th>
                <th scope="col" className="px-2 py-1.5">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {report.rows.map((r) => (
                <tr key={r.row}>
                  <td className="px-2 py-1.5 text-muted">{r.row}</td>
                  <td className="px-2 py-1.5">{r.company}</td>
                  <td className="px-2 py-1.5">{r.role}</td>
                  <td className="px-2 py-1.5">{r.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {report.will_add > report.rows.length && <p className="mt-1 text-xs text-muted">Showing the first {report.rows.length} of {report.will_add}.</p>}
      {report.skipped.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm">Skipped: {report.skipped_count} (already in your tracker)</summary>
          <ul className="mt-1 list-disc pl-5 text-sm text-muted">
            {report.skipped.map((s) => (
              <li key={s.row}>
                Row {s.row}: {s.role} at {s.company}. {s.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
      {report.problems.length > 0 && (
        <div className="mt-3" role="group" aria-label="Rows that could not be read">
          <p className="text-sm font-medium text-bad">These rows will not be added:</p>
          <ul className="mt-1 list-disc pl-5 text-sm">
            {report.problems.map((p) => (
              <li key={`${p.row}-${p.message}`}>{p.message}</li>
            ))}
          </ul>
        </div>
      )}
      {report.warnings.length > 0 && (
        <ul className="mt-3 list-disc pl-5 text-sm text-muted">
          {report.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {report.will_add > 0 ? (
          <Button onClick={onConfirm} disabled={busy}>
            {busy ? "Adding…" : `Add ${report.will_add} ${report.will_add === 1 ? "job" : "jobs"}`}
          </Button>
        ) : (
          <p className="text-sm text-muted">There is nothing new to add from this file. Fix the rows above, or choose another file.</p>
        )}
        <Button variant="ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
