"use client";

import { GripVertical } from "lucide-react";
import { useState, type HTMLAttributes, type ReactNode, type Ref } from "react";
import { buttonClass } from "@/components/ui";
import { cvApi } from "@/features/cv/api";
import { prepApi } from "@/features/prep/api";
import { errorText } from "@/lib/api";
import { Link, navigate } from "@/lib/router";
import { notify } from "@/lib/toast";
import type { Job, StatusInfo } from "@/lib/types";
import { cn } from "@/lib/utils";
import { dashboardApi } from "./api";
import { appliedParts, cvBadgeText, deadlineText, FIT_BADGE_TEXT, livingBadge, paperlessDocumentUrl, repostTitle, SKILL_MATCH_TITLE, shortDate, truncate } from "./logic";

/** What every card needs from the page around it. */
export type CardExtras = {
  /** "Quick keyword check" / the AI's name, for the Check my fit tooltip. */
  judgeLabel: string;
  prepEnabled: boolean;
  /** The Paperless address when this person may use Paperless (site admins only), else "". */
  paperlessUrl: string;
  /** Reload the dashboard after something on a card changed. */
  refresh: () => Promise<unknown> | void;
};

const LINK = "rounded-md px-2 py-1 text-theme-xs text-muted hover:bg-surface-2 hover:text-fg";
const PILL = "inline-flex items-center rounded-md bg-surface-2 px-1.5 py-0.5 text-theme-xs";

function Pill({ children, tone = "muted", title }: { children: ReactNode; tone?: "muted" | "good" | "bad" | "warn" | "brand"; title?: string }) {
  const tones = { muted: "text-muted", good: "text-good", bad: "text-bad", warn: "text-warn", brand: "text-brand" };
  return (
    <span className={cn(PILL, tones[tone])} title={title || undefined}>
      {children}
    </span>
  );
}

/** One button that does a slow thing (make a tailored CV, make a prep plan), then opens the result; says why if it could not. */
function DoButton({ label, busyLabel, title, primary, run }: { label: string; busyLabel: string; title: string; primary?: boolean; run: () => Promise<string> }) {
  const [state, setState] = useState<"idle" | "busy" | string>("idle");
  return (
    <>
      <button
        type="button"
        disabled={state === "busy"}
        title={title}
        onClick={async () => {
          setState("busy");
          try {
            navigate(await run());
          } catch (e) {
            setState(errorText(e));
          }
        }}
        className={buttonClass(primary ? "primary" : "outline", true)}
      >
        {state === "busy" ? busyLabel : label}
      </button>
      {state !== "idle" && state !== "busy" && (
        <span role="alert" className="basis-full text-theme-xs text-bad">
          {state}
        </span>
      )}
    </>
  );
}

function SendToPaperless({ documentId, refresh }: { documentId: number; refresh: CardExtras["refresh"] }) {
  const [busy, setBusy] = useState(false);
  return (
    <button
      type="button"
      disabled={busy}
      className={buttonClass("outline", true)}
      onClick={async () => {
        setBusy(true);
        try {
          const r = await dashboardApi.sendToPaperless(documentId);
          if (r.ok) await refresh();
          else notify(r.error || "Paperless upload failed", "error");
        } catch (e) {
          notify(errorText(e, "Paperless upload failed"), "error");
        } finally {
          setBusy(false);
        }
      }}
    >
      {busy ? "Sending..." : "Send to Paperless"}
    </button>
  );
}

function Documents({ job, extras }: { job: Job; extras: CardExtras }) {
  return (
    <>
      <strong className="mt-2 block text-theme-sm">Documents</strong>
      <ul className="mt-1 space-y-1 text-theme-sm">
        {job.documents.map((d) => (
          <li key={d.id} className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>
              {d.kind}:{" "}
              <a href={`/document/${d.id}/`} target="_blank" rel="noopener noreferrer" className="text-brand underline">
                {d.title}
              </a>
            </span>
            {extras.paperlessUrl &&
              (d.paperless_id ? (
                <a href={paperlessDocumentUrl(extras.paperlessUrl, d.paperless_id)} target="_blank" rel="noopener noreferrer" className="text-brand underline">
                  in Paperless
                </a>
              ) : (
                <SendToPaperless documentId={d.id} refresh={extras.refresh} />
              ))}
            {d.paperless_error && (
              <span className="text-muted" title={d.paperless_error}>
                (!)
              </span>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}

type Props = {
  job: Job;
  statuses: StatusInfo[];
  extras: CardExtras;
  onMove: (job: Job, statusId: number) => void;
  onCheckFit: (job: Job) => void;
  checking: boolean;
  /** Drag wiring from dnd-kit; absent in the list view and the drag overlay. */
  dragHandle?: { attributes: HTMLAttributes<HTMLButtonElement>; listeners: HTMLAttributes<HTMLButtonElement> | undefined; setActivatorNodeRef: Ref<HTMLButtonElement> };
  overlay?: boolean;
};

export function JobCard({ job, statuses, extras, onMove, onCheckFit, checking, dragHandle, overlay }: Props) {
  const status = statuses.find((s) => s.id === job.status_id);
  const live = livingBadge(job.live_state);
  const deadline = deadlineText(job);
  const applied = appliedParts(job);
  const canJudge = job.has_description || !!job.url;
  const hasDetails = job.strengths.length > 0 || job.gaps.length > 0 || job.tech_skills.length > 0 || !!job.notes || job.documents.length > 0;
  const color = job.band?.color;
  return (
    <article
      id={`job-${job.id}`}
      aria-label={`${job.role} at ${job.company}`}
      className={cn(
        "scroll-mt-20 rounded-md border bg-surface p-3 text-theme-sm shadow-theme-xs sm:p-4",
        job.urgent ? "border-warn" : "border-border",
        overlay && "rotate-1 shadow-lg",
      )}
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
          <h3 className="font-semibold text-gray-800 dark:text-white/90">
            {job.company} <span className="font-normal text-muted">— {job.role}</span>
          </h3>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-theme-xs text-muted">
            {job.source && <span>{job.source}</span>}
            {job.advertised_pay && <span>{job.advertised_pay}</span>}
            {job.location && <span>{job.location}</span>}
            {job.applied_date && <span>Applied {shortDate(job.applied_date, true)}</span>}
            {deadline && <span className={job.overdue ? "text-bad" : job.urgent ? "text-warn" : undefined}>{deadline}</span>}
          </div>
        </div>
        <div className="shrink-0 text-right">
          {job.percent === null ? (
            <div className="text-theme-xs text-muted">Not checked yet</div>
          ) : (
            <>
              <div className="text-xl font-semibold leading-none" style={color ? { color } : undefined}>
                {job.percent}%
              </div>
              <div className="text-theme-xs text-muted">{job.band ? job.band.label : "fit"}</div>
            </>
          )}
        </div>
      </div>

      {job.percent !== null && (
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-2" aria-hidden>
          <div className="h-full rounded-full bg-brand" style={{ width: `${job.percent}%`, ...(color ? { background: color } : {}) }} />
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <span className={cn(PILL, "gap-1.5")}>
          <span className="size-2 rounded-full" style={{ background: status?.color ?? "currentColor" }} aria-hidden />
          {status?.name ?? ""}
        </span>
        {live && (
          <Pill tone={live.tone} title={job.live_detail}>
            {live.text}
          </Pill>
        )}
        {job.decision && <Pill title={job.decision}>{truncate(job.decision, 28)}</Pill>}
        {job.risk && <Pill>Risk: {job.risk}</Pill>}
        {job.repost && (
          <Pill tone="warn" title={repostTitle(job.repost)}>
            Possible repost
          </Pill>
        )}
        {job.skill_matched && (
          <Pill tone="brand" title={SKILL_MATCH_TITLE}>
            Skill match
          </Pill>
        )}
        {job.fit_badge && (
          <Link to={`/jobs/${job.id}/edit`} title={job.fit_text} className={cn(PILL, job.fit_badge === "fits" ? "text-good" : job.fit_badge === "check" ? "text-warn" : "text-muted")}>
            {FIT_BADGE_TEXT[job.fit_badge]}
          </Link>
        )}
        {job.cv && (
          <Link to={`/cv/${job.cv.id}`} className={cn(PILL, job.cv.flagged && !job.cv.approved ? "text-warn" : "text-good")}>
            {cvBadgeText(job.cv)}
          </Link>
        )}
      </div>

      {!overlay && (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <label className="sr-only" htmlFor={`status-${job.id}`}>
              Status of {job.role} at {job.company}
            </label>
            <select
              id={`status-${job.id}`}
              value={job.status_id}
              onChange={(event) => onMove(job, Number(event.target.value))}
              className="min-w-0 max-w-full rounded-lg border border-border bg-surface px-2 py-1 text-theme-xs"
              style={status ? { borderLeft: `4px solid ${status.color}` } : undefined}
            >
              {statuses.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            {canJudge && (
              <button type="button" onClick={() => onCheckFit(job)} disabled={checking} title={`How we judge: ${extras.judgeLabel}`} className={buttonClass(job.ai_evaluated ? "outline" : "primary", true)}>
                {checking ? "Reading the posting…" : job.ai_evaluated ? "Check again" : "Check my fit"}
              </button>
            )}
            {canJudge && (
              <DoButton
                label="Tailor my CV"
                busyLabel="Tailoring…"
                title="Make a CV tailored to this job from your own CV. Nothing is invented."
                primary={job.ai_evaluated && !job.cv}
                run={() => cvApi.tailor(job.id).then((r) => `/cv/${r.id}`)}
              />
            )}
            {extras.prepEnabled && job.gaps.length > 0 && job.has_description && (
              <DoButton
                label="Prepare for this job"
                busyLabel="Preparing…"
                title="A short study plan that closes the gaps this job showed. It is written by your own AI account."
                run={async () => `/prep/${(await prepApi.create(job.id)).id}`}
              />
            )}
            <Link to={`/jobs/${job.id}/apply`} className={buttonClass("outline", true)}>
              {job.applied_date && job.applied_cv ? "Your application" : "Get ready to apply"}
            </Link>
            {job.ai_method && <span className="text-theme-xs text-muted">{job.ai_method === "keywords" ? "quick keyword check" : "read by AI"}</span>}
          </div>
          <div className="-mx-1 mt-2 flex flex-wrap items-center border-t border-border pt-2">
            {job.url && (
              <a href={job.url} target="_blank" rel="noopener noreferrer" className={LINK}>
                View the posting
              </a>
            )}
            <Link to={`/jobs/${job.id}/edit`} className={LINK}>
              Edit details
            </Link>
          </div>

          {job.summary && <p className="mt-2">{job.summary}</p>}
          {job.next_action && <p className="mt-1 text-muted">Suggested next: {job.next_action}</p>}

          {applied.length > 0 && (
            <p className="mt-2 text-theme-xs text-muted">
              {applied.map((part, i) => (
                <span key={i}>
                  {i > 0 && " · "}
                  {part.text}
                  {part.cv && (
                    <>
                      {" "}
                      <Link to={`/cv/${part.cv.id}`} className="text-brand underline">
                        {part.cv.label}
                      </Link>
                    </>
                  )}
                </span>
              ))}
            </p>
          )}

          {hasDetails && (
            <details className="mt-2">
              <summary className="cursor-pointer">Details</summary>
              <div className="mt-2">
                {job.strengths.length > 0 && (
                  <>
                    <strong>Strengths</strong>
                    <ul className="mb-2 list-disc pl-5">
                      {job.strengths.map((t, i) => (
                        <li key={i}>{t}</li>
                      ))}
                    </ul>
                  </>
                )}
                {job.gaps.length > 0 && (
                  <>
                    <strong>Worth knowing</strong>
                    <ul className="mb-2 list-disc pl-5">
                      {job.gaps.map((t, i) => (
                        <li key={i}>{t}</li>
                      ))}
                    </ul>
                  </>
                )}
                {job.tech_skills.length > 0 && (
                  <>
                    <strong>Recognized technologies</strong>
                    <p className="mb-2 text-theme-xs text-muted">Named tools this posting mentions (O*NET&apos;s own database), and whether your CV already covers them.</p>
                    <div className="mb-2 flex flex-wrap gap-1.5">
                      {job.tech_skills.map((t) => (
                        <span
                          key={t.name}
                          title={t.hot ? "In demand, per O*NET" : undefined}
                          className={cn(PILL, t.have ? "text-good" : "text-muted")}
                        >
                          {t.name}
                          {t.hot && " ★"}
                        </span>
                      ))}
                    </div>
                  </>
                )}
                {job.notes && <p className="whitespace-pre-line text-muted">{job.notes}</p>}
                {job.documents.length > 0 && <Documents job={job} extras={extras} />}
              </div>
            </details>
          )}
        </>
      )}
    </article>
  );
}
