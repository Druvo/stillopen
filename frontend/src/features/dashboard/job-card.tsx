"use client";

import { GripVertical } from "lucide-react";
import { useState, type HTMLAttributes, type Ref } from "react";
import { coverApi, cvApi } from "@/features/cv/api";
import { prepApi } from "@/features/prep/api";
import { errorText } from "@/lib/api";
import { Link, navigate } from "@/lib/router";
import type { Job, StatusInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

const LIVE_TEXT: Record<Job["live_state"], string> = { unknown: "", active: "Still open", expired: "Closed", uncertain: "Open? Unclear" };

/** Makes a tailored CV or a cover letter through the API, then opens it. */
function MakeButton({ label, busyLabel, make }: { label: string; busyLabel: string; make: () => Promise<string> }) {
  const [state, setState] = useState<"idle" | "busy" | string>("idle");
  return (
    <>
      <button
        type="button"
        disabled={state === "busy"}
        onClick={async () => {
          setState("busy");
          try {
            navigate(await make());
          } catch (e) {
            setState(errorText(e));
          }
        }}
        className="rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-2 hover:text-fg"
      >
        {state === "busy" ? busyLabel : label}
      </button>
      {state !== "idle" && state !== "busy" && <span role="alert" className="basis-full px-2 text-xs text-bad">{state}</span>}
    </>
  );
}

/** Asks for a prep plan (or opens the one that exists) and goes to it. */
function PrepareButton({ jobId }: { jobId: number }) {
  const [state, setState] = useState<"idle" | "busy" | string>("idle");
  return (
    <>
      <button
        type="button"
        disabled={state === "busy"}
        onClick={async () => {
          setState("busy");
          try {
            const made = await prepApi.create(jobId);
            navigate(`/prep/${made.id}`);
          } catch (e) {
            setState(errorText(e));
          }
        }}
        className="rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-2 hover:text-fg"
      >
        {state === "busy" ? "Preparing…" : "Prepare"}
      </button>
      {state !== "idle" && state !== "busy" && <span role="alert" className="basis-full px-2 text-xs text-bad">{state}</span>}
    </>
  );
}

type Props = {
  job: Job;
  statuses: StatusInfo[];
  onMove: (job: Job, statusId: number) => void;
  onCheckFit: (job: Job) => void;
  checking: boolean;
  /** Drag wiring from dnd-kit; absent in the list view and the drag overlay. */
  dragHandle?: { attributes: HTMLAttributes<HTMLButtonElement>; listeners: HTMLAttributes<HTMLButtonElement> | undefined; setActivatorNodeRef: Ref<HTMLButtonElement> };
  overlay?: boolean;
};

export function JobCard({ job, statuses, onMove, onCheckFit, checking, dragHandle, overlay }: Props) {
  const status = statuses.find((s) => s.id === job.status_id);
  const live = LIVE_TEXT[job.live_state];
  return (
    <article
      id={`job-${job.id}`}
      aria-label={`${job.role} at ${job.company}`}
      className={cn("rounded-lg border border-border bg-surface p-3 text-sm shadow-sm", overlay && "rotate-1 shadow-lg")}
    >
      <div className="flex items-start gap-2">
        {dragHandle && (
          <button
            type="button"
            ref={dragHandle.setActivatorNodeRef}
            {...dragHandle.attributes}
            {...dragHandle.listeners}
            aria-label={`Drag ${job.role} at ${job.company} to another column. Or use the status menu on the card.`}
            className="-ml-1 mt-0.5 shrink-0 cursor-grab touch-none rounded p-1 text-muted hover:bg-surface-2 active:cursor-grabbing"
          >
            <GripVertical className="size-4" aria-hidden />
          </button>
        )}
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-semibold">{job.role}</h3>
          <p className="truncate text-muted">
            {job.company}
            {job.location ? ` · ${job.location}` : ""}
          </p>
        </div>
        {job.percent !== null && (
          <span
            className="shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold text-white"
            style={{ background: job.band?.color ?? "#64748b" }}
            title={job.band?.label}
          >
            {job.percent}%
          </span>
        )}
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
        {live && (
          <span className={cn("rounded bg-surface-2 px-1.5 py-0.5", job.live_state === "expired" ? "text-bad" : job.live_state === "active" ? "text-good" : "text-muted")}>{live}</span>
        )}
        {job.urgent && <span className="rounded bg-surface-2 px-1.5 py-0.5 text-warn">{job.days_left === 0 ? "Due today" : `${job.days_left} days left`}</span>}
        {job.overdue && <span className="rounded bg-surface-2 px-1.5 py-0.5 text-bad">Past the deadline</span>}
        {job.skill_matched && <span className="rounded bg-surface-2 px-1.5 py-0.5 text-muted">Skill match</span>}
        {job.repost && <span className="rounded bg-surface-2 px-1.5 py-0.5 text-warn">Posted again and again</span>}
        {job.fit_level && job.fit_level !== "ok" && job.fit_text && <span className="rounded bg-surface-2 px-1.5 py-0.5 text-warn">{job.fit_text}</span>}
      </div>

      {job.summary && <p className="mt-2 line-clamp-3 text-muted">{job.summary}</p>}

      {!overlay && (
        <>
          <div className="mt-3 flex items-center gap-2">
            <label className="sr-only" htmlFor={`status-${job.id}`}>
              Status of {job.role} at {job.company}
            </label>
            <select
              id={`status-${job.id}`}
              value={job.status_id}
              onChange={(event) => onMove(job, Number(event.target.value))}
              className="min-w-0 flex-1 rounded-md border border-border bg-surface px-2 py-1 text-xs"
              style={status ? { borderLeft: `4px solid ${status.color}` } : undefined}
            >
              {statuses.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => onCheckFit(job)}
              disabled={checking}
              className="shrink-0 rounded-md bg-brand px-2.5 py-1 text-xs font-medium text-brand-contrast disabled:opacity-60"
            >
              {checking ? "Checking…" : job.evaluated ? "Check again" : "Check my fit"}
            </button>
          </div>
          <div className="mt-2 -mx-1 flex flex-wrap items-center gap-x-1 border-t border-border pt-2">
            <Link to={`/jobs/${job.id}/apply`} className="rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-2 hover:text-fg">
              Apply
            </Link>
            <MakeButton label="Tailor CV" busyLabel="Tailoring…" make={() => cvApi.tailor(job.id).then((r) => `/cv/${r.id}`)} />
            <MakeButton label="Cover letter" busyLabel="Writing…" make={() => coverApi.write(job.id).then((r) => `/cover/${r.id}`)} />
            <PrepareButton jobId={job.id} />
            <Link to={`/jobs/${job.id}/edit`} className="rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-2 hover:text-fg">
              Edit
            </Link>
            {job.url && (
              <a href={job.url} target="_blank" rel="noopener noreferrer" className="rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-2 hover:text-fg">
                Posting
              </a>
            )}
          </div>
        </>
      )}
    </article>
  );
}
