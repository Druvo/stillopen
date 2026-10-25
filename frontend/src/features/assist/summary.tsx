"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, Button, Card } from "@/components/ui";
import { errorText } from "@/lib/api";
import { Link } from "@/lib/router";
import { assistApi, type PostingSummary } from "./api";
import { AI_SETTINGS_PATH, statements } from "./logic";
import { AiNotice, ProblemLine } from "./ui";

/** A saved reading of a posting: what it needs, what it says about pay and place, and red flags with the exact words quoted. */
export function SummaryView({ summary }: { summary: PostingSummary }) {
  const rows = statements(summary);
  return (
    <div className="text-sm" data-testid="posting-summary">
      {summary.must_have.length > 0 && (
        <>
          <strong>Must have</strong>
          <ul className="mb-2 list-disc pl-5">
            {summary.must_have.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </>
      )}
      {summary.nice_to_have.length > 0 && (
        <>
          <strong>Nice to have</strong>
          <ul className="mb-2 list-disc pl-5">
            {summary.nice_to_have.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </>
      )}
      {summary.must_have.length === 0 && summary.nice_to_have.length === 0 && <p className="mb-2 text-muted">We could not tell which skills are required. Read the posting itself.</p>}
      {rows.length > 0 ? (
        <ul className="mb-2 space-y-0.5">
          {rows.map((r) => (
            <li key={r.label}>
              <strong>{r.label}:</strong> {r.text}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mb-2 text-muted">The posting says nothing about level, pay, visas, relocation or a deadline.</p>
      )}
      <strong>Red flags</strong>
      {summary.red_flags.length === 0 ? (
        <p className="text-muted">None found. That is not a promise: still check the company is real.</p>
      ) : (
        <ul className="list-disc pl-5">
          {summary.red_flags.map((f, i) => (
            <li key={i}>
              {f.flag} <span className="text-muted">The posting says: &ldquo;{f.quote}&rdquo;</span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-muted">{summary.method === "ai" ? "Read by AI, which can be wrong. Check it against the posting." : "A quick read by simple rules, not by AI. Check it against the posting."}</p>
    </div>
  );
}

/** The edit screen's section: read the posting (free, or deeper with the person's own AI) and show the saved reading. */
export function PostingSummaryPanel({ jobId, hasDescription }: { jobId: number; hasDescription: boolean }) {
  const client = useQueryClient();
  const key = ["assist", "summary", jobId] as const;
  const query = useQuery({ queryKey: key, queryFn: () => assistApi.getSummary(jobId) });
  const read = useMutation({
    mutationFn: () => assistApi.summarise(jobId),
    onSuccess: (data) => {
      client.setQueryData(key, { summary: data.summary, ai: data.ai });
      void client.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
  const summary = read.data?.summary ?? query.data?.summary ?? null;
  return (
    <Card className="mb-4">
      <h2 className="mb-1 font-semibold">What this role really needs</h2>
      <p className="mb-3 text-sm text-muted">A short list of what the posting asks for, and anything in it that looks worrying.</p>
      {!hasDescription && !summary && <p className="mb-2 text-sm text-muted">Paste the job description below and save it, then read it here.</p>}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Button variant={summary ? "outline" : "primary"} small={!!summary} disabled={read.isPending || (!hasDescription && !summary)} onClick={() => read.mutate()}>
          {read.isPending ? "Reading the posting…" : summary ? "Read it again" : "Read this posting"}
        </Button>
        {summary && <Badge>{summary.method === "ai" ? "Read by AI" : "Read by rules"}</Badge>}
      </div>
      {query.isSuccess && !query.data.ai && (
        <p className="mb-2 text-xs text-muted">
          This is the free version. For a deeper read, add your free Google AI Studio key in{" "}
          <Link to={AI_SETTINGS_PATH} className="text-brand underline">
            AI settings
          </Link>
          .
        </p>
      )}
      <ProblemLine message={read.isError ? errorText(read.error) : ""} />
      {summary && <SummaryView summary={summary} />}
      {summary?.method === "ai" && <AiNotice>{summary.notice}</AiNotice>}
    </Card>
  );
}
