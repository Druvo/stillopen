"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Badge, Button, Card, ErrorBox, Notice, Progress } from "@/components/ui";
import { SelectField } from "@/components/form";
import { errorText } from "@/lib/api";
import { Link } from "@/lib/router";
import { notify } from "@/lib/toast";
import { cvApi, type AtsCheck, type Coverage, type CoverageTerm, type Suggestion } from "./api";
import { countsText, groupChecks, KIND_LABELS, lineLabel, readinessText, readinessTone } from "./quality";

const STATUS_WORDS = { fail: "Needs fixing", warn: "Worth a look", pass: "Looks good" } as const;
const STATUS_TONE = { fail: "bad", warn: "warn", pass: "good" } as const;

function CheckRow({ check }: { check: AtsCheck }) {
  const where = lineLabel(check.lines);
  return (
    <details className="rounded-lg border border-border bg-surface px-3 py-2">
      <summary className="cursor-pointer text-sm">
        <Badge tone={STATUS_TONE[check.status]} className="mr-2">{STATUS_WORDS[check.status]}</Badge>
        <span className="font-medium">{check.title}</span>
      </summary>
      <div className="mt-2 space-y-1 text-sm">
        <p>
          <strong>Why it matters:</strong> {check.why}
        </p>
        {check.fix && (
          <p>
            <strong>How to fix it:</strong> {check.fix}
          </p>
        )}
        {where && <p className="text-muted">Found at {where} of the text below.</p>}
      </div>
    </details>
  );
}

function Terms({ items, empty }: { items: CoverageTerm[]; empty: string }) {
  if (items.length === 0) return <p className="text-sm text-muted">{empty}</p>;
  return (
    <ul className="flex flex-wrap gap-1.5">
      {items.map((t) => (
        <li key={t.term} className="rounded bg-surface-2 px-2 py-0.5 text-sm">
          {t.term}
          {t.required && <span className="ml-1 text-xs text-muted">(asked for)</span>}
        </li>
      ))}
    </ul>
  );
}

function CoverageBox({ coverage, jobLabel }: { coverage: Coverage; jobLabel: string }) {
  return (
    <section aria-label="Words from the job" className="mt-4 rounded-lg border border-border p-3">
      <h3 className="font-semibold">Words from {jobLabel}</h3>
      <p className="mb-2 text-sm">
        This CV has {coverage.found.length} of the {coverage.wanted} words the posting uses most ({coverage.percent}%). It is a rough guide, not a verdict.
      </p>
      <h4 className="mt-2 text-sm font-medium">Already in this CV</h4>
      <Terms items={coverage.found} empty="None of the main words yet." />
      <h4 className="mt-3 text-sm font-medium">Your own material has these, but this CV leaves them out</h4>
      <Terms items={coverage.in_material} empty="Nothing here: every word your material could back is already in this CV." />
      <h4 className="mt-3 text-sm font-medium">Not in your material at all: do not add these unless they are true</h4>
      <Terms items={coverage.not_in_material} empty="Nothing here." />
      <p className="mt-3 text-xs text-muted">{coverage.note}</p>
    </section>
  );
}

function SuggestionCard({ s, onApply, onDismiss, applied }: { s: Suggestion; onApply: () => void; onDismiss: () => void; applied: boolean }) {
  return (
    <li className="rounded-lg border border-border p-3 text-sm">
      <p className="mb-1">
        <Badge>{KIND_LABELS[s.kind] ?? s.kind}</Badge> <span className="text-muted">{s.reason}</span>
      </p>
      {s.original.trim() && (
        <p className="mb-1">
          <span className="font-medium">Now: </span>
          <span className="whitespace-pre-wrap break-words">{s.original}</span>
        </p>
      )}
      <p className="mb-2">
        <span className="font-medium">Suggested: </span>
        <span className="whitespace-pre-wrap break-words">{s.replacement}</span>
      </p>
      <div className="flex flex-wrap gap-2">
        {applied ? (
          <span className="text-good">Applied in the editor below. Save a new version to keep it.</span>
        ) : (
          <Button small onClick={onApply} aria-label={`Apply this change: ${s.replacement}`}>
            Apply this change
          </Button>
        )}
        <Button small variant="outline" onClick={onDismiss} aria-label={`Dismiss this suggestion: ${s.replacement}`}>
          Dismiss
        </Button>
      </div>
    </li>
  );
}

/**
 * The ATS check at the top of a CV: the readiness number, the checks in three groups, an optional comparison with one of the person's jobs and
 * an optional "Improve with AI". `onApply` puts a suggestion into the editor and says whether it fitted; nothing is saved by this card.
 */
export function AtsCard({ cvId, defaultJobId, onApply }: { cvId: number; defaultJobId: number | null; onApply: (s: Suggestion) => boolean }) {
  const [jobId, setJobId] = useState<number | null>(defaultJobId);
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);
  const [aiMessage, setAiMessage] = useState("");
  const [applied, setApplied] = useState<number[]>([]);
  const choices = useQuery({ queryKey: ["cv", "job-choices"], queryFn: cvApi.jobChoices, staleTime: 60_000 });
  const report = useQuery({ queryKey: ["cv", "ats", cvId, jobId], queryFn: () => cvApi.ats(cvId, jobId), retry: false });
  const improve = useMutation({
    mutationFn: () => cvApi.improve(cvId, jobId),
    onSuccess: (data) => {
      setSuggestions(data.suggestions);
      setApplied([]);
      setAiMessage(data.message);
    },
    onError: (e) => {
      setSuggestions(null);
      setAiMessage(errorText(e));
    },
  });
  useEffect(() => {
    setSuggestions(null);
    setAiMessage("");
  }, [cvId]);

  const ai = report.data?.ai ?? choices.data?.ai;
  const jobs = choices.data?.jobs ?? [];
  const picker = (
    <SelectField
      label="Check against a job"
      hint="Adds the words that job's posting uses, and which of them this CV has."
      value={jobId ?? ""}
      onChange={(e) => setJobId(e.target.value ? Number(e.target.value) : null)}
    >
      <option value="">No job: check the CV on its own</option>
      {jobs.map((j) => (
        <option key={j.id} value={j.id}>
          {j.company} - {j.role}
          {j.has_description ? "" : " (no description yet)"}
        </option>
      ))}
    </SelectField>
  );

  return (
    <Card className="mb-6" aria-labelledby="ats-heading">
      <h2 id="ats-heading" className="mb-1 text-lg font-semibold">
        ATS check
      </h2>
      <p className="mb-3 text-sm text-muted">
        Applicant tracking systems read a CV as plain text, in order. This free check shows what they commonly need. It does not use AI and nothing leaves your account.
      </p>
      {report.isPending && <p className="text-muted">Checking your CV…</p>}
      {report.isError && (
        <div className="mb-3">
          <ErrorBox message={errorText(report.error, "We could not check this CV.")} onRetry={() => report.refetch()} />
          {jobId !== null && (
            <Button className="mt-2" variant="outline" onClick={() => setJobId(null)}>
              Check without a job
            </Button>
          )}
        </div>
      )}
      {report.data && (
        <>
          <div role="status" aria-live="polite" className="mb-3">
            <p className="flex flex-wrap items-baseline gap-2">
              <span className="text-4xl font-bold" aria-hidden="true">
                {report.data.readiness}
              </span>
              <span className="text-sm text-muted" aria-hidden="true">
                out of 100
              </span>
              <Badge tone={readinessTone(report.data.readiness)}>{report.data.label}</Badge>
              <span className="sr-only">ATS readiness {readinessText(report.data.readiness, report.data.label)}.</span>
            </p>
            <div className="my-2">
              <Progress value={report.data.readiness} label="ATS readiness" />
            </div>
            <p className="text-sm">{countsText(report.data.counts)}.</p>
          </div>
          <p className="mb-3 text-xs text-muted">{report.data.caveat} Each check counts for the weight shown in its details; a check that could not be judged is left out.</p>
          {report.data.notes.map((n) => (
            <div key={n} className="mb-2">
              <Notice>{n}</Notice>
            </div>
          ))}
          {groupChecks(report.data.checks).map((g) => (
            <section key={g.status} aria-label={g.label} className="mb-3">
              <h3 className="mb-1 text-sm font-semibold">
                {g.label} ({g.items.length})
              </h3>
              <div className="space-y-1.5">
                {g.items.map((c) => (
                  <CheckRow key={c.id} check={c} />
                ))}
              </div>
            </section>
          ))}
          <details className="mb-3 text-sm">
            <summary className="cursor-pointer">How the files StillOpen makes are read</summary>
            <p className="mt-1">{report.data.export.summary}</p>
          </details>
        </>
      )}

      {picker}
      {report.data?.coverage && report.data.job && <CoverageBox coverage={report.data.coverage} jobLabel={`${report.data.job.company} - ${report.data.job.role}`} />}

      <section aria-label="Improve with AI" className="mt-4 border-t border-border pt-3">
        <h3 className="font-semibold">Improve with AI</h3>
        {ai && !ai.available ? (
          <p className="text-sm">
            {ai.missing_message}{" "}
            <Link to={ai.settings_link} className="text-brand underline">
              Open AI settings
            </Link>
            . The check above works without it.
          </p>
        ) : (
          <>
            <p className="mb-2 text-sm text-muted">
              Your own AI suggests up to six small changes. It only rewords what your CV already says and only uses skills your own material shows. Nothing changes until you apply it and save.
            </p>
            <Button
              disabled={improve.isPending || !ai}
              onClick={() => {
                setAiMessage("");
                improve.mutate();
              }}
            >
              {improve.isPending ? "Asking your AI…" : "Improve with AI"}
            </Button>
          </>
        )}
        <div aria-live="polite" className="mt-2">
          {aiMessage && <Notice tone={improve.isError ? "error" : "info"}>{aiMessage}</Notice>}
        </div>
        {suggestions && suggestions.length > 0 && (
          <ul className="mt-3 space-y-2">
            {suggestions.map((s) => (
              <SuggestionCard
                key={s.id}
                s={s}
                applied={applied.includes(s.id)}
                onApply={() => {
                  if (onApply(s)) {
                    setApplied((a) => [...a, s.id]);
                    notify("Change applied in the editor below. Save as a new version to keep it.");
                  } else {
                    notify("That line is no longer in the editor, so nothing was changed.", "error");
                  }
                }}
                onDismiss={() => setSuggestions((list) => (list ?? []).filter((x) => x.id !== s.id))}
              />
            ))}
          </ul>
        )}
      </section>
    </Card>
  );
}
