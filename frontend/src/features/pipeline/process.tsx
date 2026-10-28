"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, buttonClass, Card, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { errorText } from "@/lib/api";
import { Link } from "@/lib/router";
import { cn } from "@/lib/utils";
import { depthApi, companyPath, type Stage } from "./depth-api";
import { pipelineApi } from "./api";
import { whenLabel } from "./logic";
import { SuggestMove, type Suggestion } from "./suggest";

const OUTCOMES = [
  { value: "pending", label: "Scheduled" },
  { value: "done", label: "Completed, waiting to hear" },
  { value: "passed", label: "Passed" },
  { value: "rejected", label: "Failed" },
  { value: "noshow", label: "No-show" },
  { value: "cancelled", label: "Cancelled" },
];

const DOT: Record<string, string> = {
  pending: "border-border bg-surface",
  done: "border-brand bg-brand/30",
  passed: "border-good bg-good",
  rejected: "border-bad bg-bad",
  noshow: "border-warn bg-warn",
  cancelled: "border-border bg-surface-2",
};

function StageItem({ stage, jobId, onSuggest }: { stage: Stage; jobId: number; onSuggest: (s: Suggestion) => void }) {
  const client = useQueryClient();
  const change = useMutation({
    mutationFn: (outcome: string) => pipelineApi.interviewOutcome(stage.id, outcome),
    onSuccess: (data) => {
      if (data.suggest_status) onSuggest({ jobId, status: data.suggest_status });
      return client.invalidateQueries({ queryKey: ["process", jobId] });
    },
  });
  return (
    <li className="relative pb-6 pl-8 last:pb-0" data-testid="stage">
      <span aria-hidden className={cn("absolute left-0 top-1.5 size-4 rounded-full border-2", DOT[stage.outcome] ?? DOT.pending)} />
      <span aria-hidden className="absolute left-[7px] top-6 h-[calc(100%-1rem)] w-0.5 bg-border" />
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold">{stage.name}</h3>
          <p className="text-sm text-muted">{whenLabel(stage.scheduled_local)}</p>
        </div>
        <Badge tone={stage.outcome === "passed" ? "good" : stage.outcome === "rejected" ? "bad" : "muted"}>{stage.outcome_label}</Badge>
      </div>
      {stage.interviewers.length > 0 && (
        <p className="mt-1 text-sm">
          With{" "}
          {stage.interviewers.map((c, i) => (
            <span key={c.id}>
              {i > 0 && ", "}
              <Link to="/contacts" className="underline">
                {c.name}
              </Link>
            </span>
          ))}
        </p>
      )}
      {stage.where && <p className="text-sm text-muted">{stage.where}</p>}
      <label className="mt-2 block text-sm">
        <span className="mr-1 text-muted">Outcome of {stage.name}</span>
        <select
          className="rounded-md border border-border bg-surface px-2 py-1 text-sm"
          value={stage.outcome}
          disabled={change.isPending}
          onChange={(e) => change.mutate(e.target.value)}
        >
          {OUTCOMES.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      {change.isError && (
        <p role="alert" className="mt-1 text-sm text-bad">
          {errorText(change.error)}
        </p>
      )}
    </li>
  );
}

/** One job's hiring process: every stage in date order, who you met, and how each went. */
export function JobProcess({ id }: { id: number }) {
  const query = useQuery({ queryKey: ["process", id], queryFn: () => depthApi.process(id) });
  const [suggest, setSuggest] = useState<Suggestion | null>(null);
  if (query.isPending) return <Loading what="this hiring process" />;
  if (query.isError) return <ErrorBox message={errorText(query.error, "We could not load this job's process.")} onRetry={() => query.refetch()} />;
  const data = query.data;
  return (
    <>
      <PageHeader
        title={`Hiring process: ${data.job.role}`}
        subtitle={
          <>
            <Link to={companyPath(data.job.company)} className="underline">
              {data.job.company}
            </Link>{" "}
            · currently {data.job.status}
          </>
        }
        actions={
          <Link to={`/interviews?job=${id}`} className={buttonClass("primary")}>
            Add a stage
          </Link>
        }
      />
      <p className="mb-4 text-lg font-medium" data-testid="process-summary">
        {data.summary}
      </p>
      {suggest && (
        <div className="mb-4">
          <SuggestMove suggestion={suggest} onDone={() => setSuggest(null)} />
        </div>
      )}
      {data.stages.length === 0 ? (
        <Card className="text-sm text-muted">Nothing here yet. When a company invites you to talk, add the first stage and it will show up on this timeline.</Card>
      ) : (
        <Card>
          <ol aria-label="Stages of the hiring process">
            {data.stages.map((s) => (
              <StageItem key={s.id} stage={s} jobId={id} onSuggest={setSuggest} />
            ))}
          </ol>
        </Card>
      )}
      {data.offers.length > 0 && (
        <p className="mt-4 text-sm">
          You have {data.offers.length} offer{data.offers.length === 1 ? "" : "s"} for this job.{" "}
          <Link to="/offers" className="underline">
            See offers
          </Link>
          .
        </p>
      )}
    </>
  );
}
