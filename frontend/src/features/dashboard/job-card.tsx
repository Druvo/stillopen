"use client";

import { GripVertical } from "lucide-react";
import type { HTMLAttributes, Ref } from "react";
import { csrfToken } from "@/lib/api";
import type { Job, StatusInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

const LIVE_TEXT: Record<Job["live_state"], string> = { unknown: "", active: "Still open", expired: "Closed", uncertain: "Open? Unclear" };

/** A button that POSTs to a classic page (those actions are POST-only there), then lands on that page. */
function PostButton({ action, children }: { action: string; children: React.ReactNode }) {
  return (
    <form
      method="post"
      action={action}
      onSubmit={(event) => {
        const field = event.currentTarget.elements.namedItem("csrfmiddlewaretoken") as HTMLInputElement | null;
        if (field) field.value = csrfToken();
      }}
    >
      <input type="hidden" name="csrfmiddlewaretoken" defaultValue="" />
      <button type="submit" className="rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-2 hover:text-fg">
        {children}
      </button>
    </form>
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
            <a href={job.apply_url} className="rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-2 hover:text-fg">
              Apply
            </a>
            <PostButton action={job.tailor_url}>Tailor CV</PostButton>
            <PostButton action={job.cover_url}>Cover letter</PostButton>
            <PostButton action={job.prep_url}>Prepare</PostButton>
            <a href={job.edit_url} className="rounded-md px-2 py-1 text-xs text-muted hover:bg-surface-2 hover:text-fg">
              Edit
            </a>
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
