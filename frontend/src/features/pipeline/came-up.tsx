"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui";
import { errorText } from "@/lib/api";
import { notify } from "@/lib/toast";
import { depthApi, type Tally } from "./depth-api";

/** "This came up" tick for one prep question, and the running tally ("3 of 8 came up"). Pass `jobId`+`qkey` or `questionId`. */
export function CameUpTick({ jobId, qkey, questionId, planId }: { jobId?: number; qkey?: string; questionId?: number; planId?: number }) {
  const client = useQueryClient();
  const key = ["came-up", jobId ?? `plan${planId}`] as const;
  const query = useQuery({ queryKey: key, queryFn: () => (jobId !== undefined ? depthApi.jobTally(jobId) : depthApi.planTally(planId as number)) });
  const set = useMutation({
    mutationFn: (value: boolean) => (jobId !== undefined ? depthApi.setJobCameUp(jobId, qkey as string, value) : depthApi.setPlanCameUp(questionId as number, value)),
    onSuccess: (data: Tally) => client.setQueryData(key, data),
  });
  const ticked = query.data?.ticked.includes(jobId !== undefined ? (qkey as string) : (questionId as number)) ?? false;
  return (
    <label className="mt-2 flex items-center gap-2 text-sm">
      <input type="checkbox" checked={ticked} disabled={set.isPending || query.isPending} onChange={(e) => set.mutate(e.target.checked)} />
      <span>This came up</span>
      {set.isError && <span role="alert" className="text-bad">{errorText(set.error)}</span>}
    </label>
  );
}

/** The tally line for a job's interview prep or a plan's quiz ("3 of 8 came up"); nothing while there are no questions. */
export function CameUpTally({ jobId, planId }: { jobId?: number; planId?: number }) {
  const query = useQuery({ queryKey: ["came-up", jobId ?? `plan${planId}`], queryFn: () => (jobId !== undefined ? depthApi.jobTally(jobId) : depthApi.planTally(planId as number)) });
  if (!query.data?.text) return null;
  return (
    <p className="mb-2 text-sm text-muted" aria-live="polite" data-testid="came-up-tally">
      {query.data.text}
    </p>
  );
}

/** Copies one prep question into the person's own bank, linked to the job it came from. */
export function SaveToBank({ question, jobId }: { question: string; jobId?: number }) {
  const [state, setState] = useState<"idle" | "saved">("idle");
  const save = useMutation({
    mutationFn: () => depthApi.addBank({ question: question.slice(0, 400), answer: "", tags: [], job_ids: jobId ? [jobId] : [], interview_ids: [] }),
    onSuccess: () => {
      setState("saved");
      notify("Saved to your question bank.");
    },
  });
  if (state === "saved") return <span className="text-sm text-muted">In your question bank</span>;
  return (
    <>
      <Button variant="outline" small disabled={save.isPending} onClick={() => save.mutate()}>
        Save to my question bank
      </Button>
      {save.isError && <span role="alert" className="ml-2 text-sm text-bad">{errorText(save.error)}</span>}
    </>
  );
}
