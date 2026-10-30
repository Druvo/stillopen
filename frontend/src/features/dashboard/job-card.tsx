"use client";

import { CalendarClock, GripVertical } from "lucide-react";
import { lazy, Suspense, useMemo, useState, type HTMLAttributes, type ReactNode, type Ref } from "react";
import { ActionMenu, type MenuItem } from "@/components/menu";
import { CreditLink } from "@/components/credit";
import { buttonClass } from "@/components/ui";
import { cvApi } from "@/features/cv/api";
import { SummaryView } from "@/features/assist/summary";
import { prepApi } from "@/features/prep/api";
import { errorText } from "@/lib/api";
import { Link, navigate } from "@/lib/router";
import { notify } from "@/lib/toast";
import type { Job, StatusInfo } from "@/lib/types";
import { applyHref, cn } from "@/lib/utils";
import { companyPath } from "@/features/pipeline/depth-api";
import { dashboardApi } from "./api";
import { statusLabel } from "./jobmgmt";
import { appliedParts, cvBadgeText, deadlineText, FIT_BADGE_TEXT, livingBadge, paperlessDocumentUrl, repostTitle, SKILL_MATCH_TITLE, shortDate, truncate } from "./logic";

// The per-requirement card is fetched only when someone opens it.
const MatchCard = lazy(() => import("@/features/jobs/match-card"));

function MatchDetails({ jobId }: { jobId: number }) {
  const [opened, setOpened] = useState(false);
  return (
    <details className="mt-2" onToggle={(e) => e.currentTarget.open && setOpened(true)}>
      <summary className="cursor-pointer">How you match</summary>
      <div className="mt-2">
        {opened && (
          <Suspense fallback={<p className="text-theme-sm text-muted">Reading the posting…</p>}>
            <MatchCard jobId={jobId} heading={false} />
          </Suspense>
        )}
      </div>
    </details>
  );
}

/** What every card needs from the page around it. */
export type CardExtras = {
  /** "Quick keyword check" / the AI's name, for the Check my fit tooltip. */
  judgeLabel: string;
  prepEnabled: boolean;
  /** The Paperless address when this person may use Paperless (site admins only), else "". */
  paperlessUrl: string;
  /** Reload the dashboard after something on a card changed. */
  refresh: () => Promise<unknown> | void;
  /** Move one job to "Not for me" (with an Undo). Absent where the card is shown without the list's actions. */
  notForMe?: (job: Job) => void;
  /** Archive one job: it leaves the list and the counts and can be restored from the Archived section. */
  archive?: (job: Job) => void;
  /** Ask to remove one job for good (the page shows the confirmation). */
  remove?: (job: Job) => void;
};

const PILL = "inline-flex items-center gap-1 rounded-md bg-surface-2 px-1.5 py-0.5 text-theme-xs";
const TOUCH = "min-h-11 sm:min-h-9";

function Pill({ children, tone = "muted", title }: { children: ReactNode; tone?: "muted" | "good" | "bad" | "warn" | "brand"; title?: string }) {
  const tones = { muted: "text-muted", good: "text-good", bad: "text-bad", warn: "text-warn", brand: "text-brand" };
  return (
    <span className={cn(PILL, tones[tone])} title={title || undefined}>
      {children}
    </span>
  );
}

/** How well the job matches: a ring filled to the percent, with the number (and, in the list, the band's name) so colour is never the only clue. */
export function MatchRing({ job, showBand }: { job: Pick<Job, "percent" | "band" | "ai_method">; showBand: boolean }) {
  if (job.percent === null) {
    return (
      <div className="w-16 shrink-0 rounded-lg border border-dashed border-border px-1 py-1.5 text-center text-theme-xs leading-tight text-muted">Not checked yet</div>
    );
  }
  const color = job.band?.color ?? "var(--brand)";
  const r = 18;
  const c = 2 * Math.PI * r;
  const how = job.ai_method === "keywords" ? "Quick keyword check" : job.ai_method ? "Read by AI" : "";
  return (
    <div className="flex w-14 shrink-0 flex-col items-center" title={how || undefined}>
      <div className="relative size-12" role="img" aria-label={`${job.percent}% match${job.band ? `, ${job.band.label}` : ""}`}>
        <svg viewBox="0 0 44 44" className="size-12 -rotate-90" aria-hidden>
          <circle cx="22" cy="22" r={r} fill="none" strokeWidth="4" className="stroke-gray-200 dark:stroke-gray-700" />
          <circle cx="22" cy="22" r={r} fill="none" strokeWidth="4" strokeLinecap="round" stroke={color} strokeDasharray={c} strokeDashoffset={c * (1 - Math.min(100, job.percent) / 100)} />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-theme-xs font-semibold text-gray-800 dark:text-white/90" aria-hidden>
          {job.percent}%
        </span>
      </div>
      {showBand && job.band && <span className="mt-0.5 text-center text-theme-xs leading-tight text-muted">{job.band.label}</span>}
    </div>
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
  /** "row" is the list's full-width row; "compact" is the same card narrowed for a board column. */
  variant?: "row" | "compact";
  /** Present while the person is choosing several jobs (list view only): the box in front of the row. */
  select?: { checked: boolean; onToggle: () => void };
  /** Drag wiring from dnd-kit; absent in the list view and the drag overlay. */
  dragHandle?: { attributes: HTMLAttributes<HTMLButtonElement>; listeners: HTMLAttributes<HTMLButtonElement> | undefined; setActivatorNodeRef: Ref<HTMLButtonElement> };
  overlay?: boolean;
};

export function JobCard({ job, statuses, extras, onMove, onCheckFit, checking, variant = "row", dragHandle, overlay, select }: Props) {
  const compact = variant === "compact";
  const status = statuses.find((s) => s.id === job.status_id);
  const live = livingBadge(job.live_state);
  const deadline = deadlineText(job);
  const applied = appliedParts(job);
  const canJudge = job.has_description || !!job.url;
  const needsFit = canJudge && !job.ai_evaluated;
  const hasDetails = job.strengths.length > 0 || job.gaps.length > 0 || job.tech_skills.length > 0 || !!job.notes || job.documents.length > 0 || applied.length > 0 || !!job.next_action || !!job.ai_method;
  const [working, setWorking] = useState<string | null>(null);
  const [problem, setProblem] = useState("");
  const name = `${job.role} at ${job.company}`;

  /** A slow thing (make a tailored CV, make a prep plan), then open the result; say why if it could not be done. */
  const run = async (busyText: string, go: () => Promise<string>) => {
    setWorking(busyText);
    setProblem("");
    try {
      navigate(await go());
    } catch (e) {
      setProblem(errorText(e));
    } finally {
      setWorking(null);
    }
  };

  const unsent = job.documents.filter((d) => !d.paperless_id);
  const items = useMemo(() => {
    const list: MenuItem[] = [];
    if (canJudge && job.ai_evaluated) list.push({ key: "again", label: "Check again", onSelect: () => onCheckFit(job) });
    if (needsFit) list.push({ key: "apply", label: job.applied_date && job.applied_cv ? "Your application" : "Get ready to apply", to: `/jobs/${job.id}/apply` });
    if (canJudge) {
      list.push({ key: "tailor", label: "Tailor my CV", onSelect: () => void run("Tailoring your CV…", () => cvApi.tailor(job.id).then((r) => `/cv/${r.id}`)) });
    }
    if (extras.prepEnabled && job.gaps.length > 0 && job.has_description) {
      list.push({ key: "prep", label: "Prepare for this job", onSelect: () => void run("Preparing your plan…", async () => `/prep/${(await prepApi.create(job.id)).id}`) });
    }
    list.push({ key: "process", label: "Hiring process", to: `/jobs/${job.id}/process` });
    list.push({ key: "edit", label: "Edit details", to: `/jobs/${job.id}/edit` });
    if (job.url) list.push({ key: "view", label: "View the posting", href: job.url });
    if (extras.notForMe) list.push({ key: "notforme", label: "Not for me", onSelect: () => extras.notForMe?.(job) });
    if (extras.archive) list.push({ key: "archive", label: "Archive", onSelect: () => extras.archive?.(job) });
    if (extras.remove) list.push({ key: "remove", label: "Remove for good…", onSelect: () => extras.remove?.(job) });
    if (extras.paperlessUrl && unsent.length > 0) {
      list.push({
        key: "paperless",
        label: "Send to Paperless",
        onSelect: () =>
          void (async () => {
            try {
              for (const d of unsent) {
                const r = await dashboardApi.sendToPaperless(d.id);
                if (!r.ok) throw new Error(r.error || "Paperless upload failed");
              }
              await extras.refresh();
            } catch (e) {
              notify(e instanceof Error && e.message ? e.message : "Paperless upload failed", "error");
            }
          })(),
      });
    }
    return list;
    // `run` only sets state; the card's data is what the list depends on.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job, canJudge, needsFit, extras, unsent.length, onCheckFit]);

  return (
    <article
      id={`job-${job.id}`}
      aria-label={name}
      className={cn("so-job scroll-mt-20 rounded-md border bg-surface p-3 text-theme-sm shadow-theme-xs sm:p-4", job.urgent ? "border-warn" : "border-border", overlay && "rotate-1 shadow-lg")}
    >
      <div className={cn("flex gap-3", compact ? "flex-col" : "flex-col md:flex-row md:items-start md:justify-between")}>
        <div className="flex min-w-0 flex-1 items-start gap-3">
          {select && (
            <label className="-ml-1 flex size-11 shrink-0 cursor-pointer items-center justify-center sm:size-8">
              <input type="checkbox" checked={select.checked} onChange={select.onToggle} aria-label={`Select ${name}`} className="size-4" />
            </label>
          )}
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
          <MatchRing job={job} showBand={!compact} />
          <div className="min-w-0 flex-1">
            <h3 className="break-words font-semibold text-gray-800 dark:text-white/90">{job.role}</h3>
            <p className="break-words text-muted">
              <Link to={companyPath(job.company)} className="hover:underline">
                {job.company}
              </Link>
              {job.location && <span> · {job.location}</span>}
            </p>
            <p className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-theme-xs text-muted">
              {job.source && <span>{job.source}</span>}
              {job.advertised_pay && <span>{job.advertised_pay}</span>}
              {job.credit && <CreditLink credit={job.credit} className="underline" />}
              {job.applied_date && <span>Applied {shortDate(job.applied_date)}</span>}
            </p>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              {live && (
                <Pill tone={live.tone} title={job.live_detail}>
                  {live.text}
                </Pill>
              )}
              {deadline && (
                <Pill tone={job.overdue ? "bad" : job.urgent ? "warn" : "muted"}>
                  <CalendarClock className="size-3" aria-hidden />
                  {deadline}
                </Pill>
              )}
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
              {job.decision && <Pill title={job.decision}>{truncate(job.decision, 28)}</Pill>}
              {job.risk && <Pill>Risk: {job.risk}</Pill>}
            </div>
            {!compact && job.summary && <p className="mt-1.5 line-clamp-2">{job.summary}</p>}
            {!compact && applyHref(job.apply_address) && (
              <p className="mt-1">
                <a href={applyHref(job.apply_address)} target="_blank" rel="noopener noreferrer" className="text-brand underline" title="The address this posting publishes for applying. We never send anything for you.">
                  Apply address: {job.apply_address}
                </a>
              </p>
            )}
          </div>
        </div>

        {!overlay && (
          <div className={cn("flex flex-wrap items-center gap-2", !compact && "md:shrink-0 md:justify-end")}>
            <label className="sr-only" htmlFor={`status-${job.id}`}>
              Status of {name}
            </label>
            <select
              id={`status-${job.id}`}
              value={job.status_id}
              onChange={(event) => onMove(job, Number(event.target.value))}
              className={cn("min-w-0 max-w-full rounded-lg border border-border bg-surface px-2 py-1 text-theme-sm", TOUCH)}
              style={status ? { borderLeft: `4px solid ${status.color}` } : undefined}
            >
              {statuses.map((s) => (
                <option key={s.id} value={s.id}>
                  {statusLabel(s)}
                </option>
              ))}
            </select>
            {needsFit ? (
              <button type="button" onClick={() => onCheckFit(job)} disabled={checking} aria-label={checking ? undefined : `Check my fit for ${name}`} title={`How we judge: ${extras.judgeLabel}`} className={cn(buttonClass("primary"), TOUCH)}>
                {checking ? "Reading the posting…" : "Check my fit"}
              </button>
            ) : (
              <Link to={`/jobs/${job.id}/apply`} className={cn(buttonClass("primary"), TOUCH)}>
                {job.applied_date && job.applied_cv ? "Your application" : "Get ready to apply"}
              </Link>
            )}
            <ActionMenu label={`More actions for ${name}`} items={items} busy={working !== null} />
          </div>
        )}
      </div>

      {!overlay && (
        <>
          {working && (
            <p role="status" className="mt-2 text-theme-xs text-muted">
              {working}
            </p>
          )}
          {problem && (
            <p role="alert" className="mt-2 text-theme-xs text-bad">
              {problem}
            </p>
          )}
          {job.has_description && <MatchDetails jobId={job.id} />}
          {hasDetails && (
            <details className="mt-2">
              <summary className="cursor-pointer">Details</summary>
              <div className="mt-2">
                {job.next_action && <p className="mb-2 text-muted">Suggested next: {job.next_action}</p>}
                {job.prep && (
                  <p className="mb-2">
                    <Link to={`/prep/${job.prep.id}`} className="text-brand underline">
                      Prep plan {job.prep.percent}% done
                    </Link>
                  </p>
                )}
                {job.ai_summary && (
                  <div className="mb-2">
                    <strong>What this role really needs</strong>
                    <SummaryView summary={job.ai_summary} />
                  </div>
                )}
                {compact && job.summary && <p className="mb-2">{job.summary}</p>}
                {job.ai_method && <p className="mb-2 text-theme-xs text-muted">{job.ai_method === "keywords" ? "Fit worked out by a quick keyword check." : "Fit read by AI."}</p>}
                {applied.length > 0 && (
                  <p className="mb-2 text-theme-xs text-muted">
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
