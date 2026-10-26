"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Loader2 } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { Button, buttonClass, Card, Notice, Progress } from "@/components/ui";
import { errorText } from "@/lib/api";
import { Link } from "@/lib/router";
import { notify } from "@/lib/toast";
import type { Dashboard, Followup, Me, NextStep, ScanStatus, SearchSummary, ComingUpItem } from "@/lib/types";
import { useIsWide } from "@/lib/use-media";
import { cn } from "@/lib/utils";
import { jobsApi } from "@/features/jobs/api";
import { duplicateMessage } from "@/features/jobs/jobmgmt";
import type { Stats } from "@/features/stats/api";
import { cardTiles } from "@/features/stats/logic";
import { dashboardApi } from "./api";
import { comingUpAllLinks, comingUpText, comingUpTo } from "./coming-up";
import { entryText, nextStepTarget, scanPercent, scanTitle, searchRows, shortDate } from "./logic";

export function Spinner() {
  return <Loader2 className="size-4 animate-spin" aria-hidden />;
}

/** The warnings only a site admin sees (the same ones the classic dashboard showed). */
export function StaffBanners({ me }: { me?: Me }) {
  if (!me?.is_staff) return null;
  return (
    <>
      {me.email_unverified_signups && (
        <Notice>
          Sign-up is open, but this server has no email set up, so new people are let in without confirming their address. Set <code>EMAIL_HOST</code> (see docs/HOSTING.md) to turn confirmation back on.
        </Notice>
      )}
      {me.no_search_keys && (
        <Notice>
          Add a free Jooble or Adzuna key to find jobs in more countries. Without one, whole countries have no job search behind them. Add it under{" "}
          <a href="/admin/tracker/siteconfig/" className="text-brand underline">
            Site configuration &gt; Job search keys
          </a>
          .
        </Notice>
      )}
      {me.legal_has_blanks && (
        <Notice>
          Sign-up is open, but your privacy policy or terms still have <code>[bracketed parts]</code> to fill in. Complete them under{" "}
          <a href="/admin/tracker/siteconfig/" className="text-brand underline">
            Site configuration &gt; Legal
          </a>{" "}
          before real people sign up. Run <code>python manage.py update_legal_text</code> first if you are still on the old placeholder text.
        </Notice>
      )}
      {me.jooble_sources_dormant && !me.no_search_keys && ( // the "no key at all" banner above already says it; two nudges for one cause would be noise
        <Notice>
          A Jooble job source is enabled (e.g. Bangladesh, Malaysia, the Gulf) but has no key, so it silently
          finds nothing on every search. Get a free key at{" "}
          <a href="https://jooble.org/api/about" target="_blank" rel="noopener noreferrer" className="text-brand underline">
            jooble.org/api/about
          </a>{" "}
          and paste it under{" "}
          <a href="/admin/tracker/siteconfig/" className="text-brand underline">
            Site configuration &gt; Job search keys
          </a>
          .
        </Notice>
      )}
      {me.usajobs_sources_dormant && (
        <Notice>
          A USAJobs source is enabled but has no key (or no registered email), so it silently finds nothing on
          every search. Get a free key at{" "}
          <a href="https://developer.usajobs.gov/apirequest" target="_blank" rel="noopener noreferrer" className="text-brand underline">
            developer.usajobs.gov/apirequest
          </a>{" "}
          and paste both it and the email you requested it with under{" "}
          <a href="/admin/tracker/siteconfig/" className="text-brand underline">
            Site configuration &gt; Job search keys
          </a>
          .
        </Notice>
      )}
    </>
  );
}

// ---- the side column ---------------------------------------------------------------------------------------------------------

/**
 * A card of the side column. From the xl breakpoint it is a plain card. Below it the cards stack under the tiles and each one folds
 * into a disclosure (a button with aria-expanded), closed unless `defaultOpen`, so a phone is not a long wall of cards.
 */
export function AsideCard({ title, defaultOpen = false, accent = false, hint, children }: { title: string; defaultOpen?: boolean; accent?: boolean; hint?: ReactNode; children: ReactNode }) {
  const wide = useIsWide();
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  const shown = wide || open;
  return (
    <section aria-labelledby={`${id}-h`} className={cn("so-card rounded-2xl border bg-surface", accent ? "border-brand-300 dark:border-brand-500/40" : "border-border")}>
      <h2 id={`${id}-h`} className="text-theme-sm font-semibold text-gray-800 dark:text-white/90">
        {wide ? (
          <span className="flex items-center justify-between gap-2 px-4 pt-4">
            {title}
            {hint}
          </span>
        ) : (
          <button type="button" aria-expanded={open} aria-controls={`${id}-body`} onClick={() => setOpen((v) => !v)} className="flex min-h-11 w-full items-center justify-between gap-2 px-4 py-2 text-left font-semibold">
            <span>
              {title} {hint}
            </span>
            <ChevronDown className={cn("size-4 shrink-0 transition-transform", open && "rotate-180")} aria-hidden />
          </button>
        )}
      </h2>
      <div id={`${id}-body`} hidden={!shown} className="px-4 pb-4 pt-2">
        {children}
      </div>
    </section>
  );
}

/**
 * The first thing a person with no AI set up is asked: add a Google AI Studio key. The free keyword check works without it, so "Not now"
 * is a real answer (saved on the account, so it is not asked again on another device).
 */
export function AiKeyPrompt({ onDismiss }: { onDismiss: () => void }) {
  return (
    <section aria-labelledby="ai-prompt-h" className="rounded-2xl border border-brand-300 bg-brand-50 p-4 sm:p-5 dark:border-brand-500/40 dark:bg-brand-500/10">
      <h2 id="ai-prompt-h" className="text-lg font-semibold text-gray-800 dark:text-white/90">
        First, add a free Google AI Studio key
      </h2>
      <p className="mt-1 text-theme-sm">
        With your own key, StillOpen can read each job and your CV carefully: a better match score, what you are strong at, and what to learn. Without it you still get the free keyword check, so you can come back to this later.
      </p>
      <ol className="mt-3 list-decimal space-y-1 pl-5 text-theme-sm">
        <li>
          <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer" className="font-medium text-brand underline">
            Create a key in Google AI Studio
          </a>{" "}
          (a Google account is enough; it opens in a new tab).
        </li>
        <li>Press &ldquo;Add my key&rdquo;, paste it and Save. It is stored encrypted and never shown again.</li>
      </ol>
      <p className="mt-2 text-theme-xs text-muted">
        Only when you press Check my fit are the job text and the relevant parts of your CV sent to Google. On Google&apos;s free tier Google may use what you send to improve its products; pick a paid key or another provider if that matters to you.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Link to="/profile/ai?preset=gemini" className={buttonClass("primary")}>
          Add my key
        </Link>
        <Button variant="outline" onClick={onDismiss}>
          Not now
        </Button>
      </div>
    </section>
  );
}

/** "Your next step": the one thing worth doing now. A link into the app uses the router, a `#job-ID` link scrolls to that card. */
export function NextStepBody({ step, onCard }: { step: NextStep; onCard: (id: string) => void }) {
  const target = step.url ? nextStepTarget(step.url) : null;
  const cls = buttonClass("primary");
  return (
    <div>
      <p className="font-semibold text-gray-800 dark:text-white/90">{step.headline}</p>
      <p className="mt-0.5 text-theme-sm text-muted">{step.body}</p>
      {target && step.label && (
        <div className="mt-3">
          {target.kind === "app" && (
            <Link to={target.to} className={cn(cls, "min-h-11 sm:min-h-9")}>
              {step.label}
            </Link>
          )}
          {target.kind === "card" && (
            <a
              href={`#${target.id}`}
              className={cn(cls, "min-h-11 sm:min-h-9")}
              onClick={(e) => {
                e.preventDefault();
                onCard(target.id);
              }}
            >
              {step.label}
            </a>
          )}
          {target.kind === "other" && (
            <a href={target.href} className={cn(cls, "min-h-11 sm:min-h-9")}>
              {step.label}
            </a>
          )}
        </div>
      )}
    </div>
  );
}

/** The per-source log of the last search. It is fetched only once it is opened (it can be long). */
function ScanLogList({ scan }: { scan: ScanStatus }) {
  const log = useQuery({
    queryKey: ["scan-log", scan.started_at, scan.finished_at, scan.running],
    queryFn: dashboardApi.scanLog,
    staleTime: 0,
    refetchInterval: scan.running ? 3000 : false,
  });
  if (log.isPending) return <p className="text-theme-xs text-muted">Loading the log…</p>;
  if (log.isError)
    return (
      <p role="alert" className="text-theme-xs text-bad">
        We could not load the log.{" "}
        <button type="button" onClick={() => log.refetch()} className="underline">
          Try again
        </button>
      </p>
    );
  const entries = log.data.entries ?? [];
  if (entries.length === 0) return <p className="text-theme-xs text-muted">No sources checked yet.</p>;
  return (
    <div className="space-y-1.5">
      {entries.map((e, i) => (
        <div key={`${e.source}-${i}`} className="flex flex-col gap-0.5 text-theme-xs">
          <span>
            {e.source} <span className="text-muted">({e.connector})</span>
          </span>
          <span className={e.error ? "text-bad" : "text-muted"}>{entryText(e)}</span>
        </div>
      ))}
    </div>
  );
}

/** The last search: progress while it runs, a one-line result after, and the log of every source on request. */
export function LastSearchBody({ scan, starting, canScan }: { scan: ScanStatus | null; starting: boolean; canScan: boolean }) {
  const [logOpen, setLogOpen] = useState(false);
  if (!scan && !starting) {
    return <p className="text-theme-sm text-muted">{canScan ? "You have not searched yet. Press Search for jobs and we look through your job sources for roles that fit you." : "No search has run yet."}</p>;
  }
  const running = starting || !!scan?.running;
  const view: ScanStatus = scan ?? { running: true, done: 0, total: 0, error: "", found: 0, added: 0, note: "", started_at: null, finished_at: null, phase: "reading", entries_count: 0 };
  const percent = starting && !scan?.running ? 3 : scanPercent(view);
  return (
    <div>
      <div className="flex items-start gap-2" aria-live="polite">
        {running && <Spinner />}
        <strong className="text-theme-sm font-medium">{starting && !scan?.running ? "Starting the search…" : scanTitle(view)}</strong>
      </div>
      {running && (
        <>
          <div className="mt-2">
            <Progress value={percent} label="Search progress" />
          </div>
          <p className="mt-1 text-theme-xs text-muted">Usually about a minute. You can keep using StillOpen: the first jobs show up here by themselves as soon as they are ready.</p>
        </>
      )}
      {view.note && <p className="mt-1 text-theme-sm text-muted">{view.note}</p>}
      {view.error && <p className="mt-1 text-theme-sm text-bad">{view.error}</p>}
      <details className="mt-2" onToggle={(e) => setLogOpen((e.currentTarget as HTMLDetailsElement).open)}>
        <summary className="cursor-pointer text-theme-sm">Scan log -- where it searched and what it found</summary>
        <div className="mt-2">{logOpen && <ScanLogList scan={view} />}</div>
      </details>
    </div>
  );
}

/** What drives the matches, with where to change each thing. Read-only: the changing happens in Profile. */
export function YourSearchBody({ summary, emptyPlaces }: { summary: SearchSummary; emptyPlaces?: string | null }) {
  return (
    <div>
      <ul className="space-y-2">
        {searchRows(summary).map((row) => (
          <li key={row.key} className="flex items-start justify-between gap-3 text-theme-sm">
            <dl className="min-w-0">
              <div>
                <dt className="text-theme-xs text-muted">{row.label}</dt>
                <dd className={cn("break-words", row.empty && "text-muted")}>{row.value}</dd>
              </div>
            </dl>
            <Link to={row.to} aria-label={`Your search: ${row.empty ? "add" : "change"} ${row.action}`} className="link-target shrink-0 rounded px-1 text-theme-xs text-brand underline">
              {row.empty ? "Add" : "Change"}
            </Link>
          </li>
        ))}
      </ul>
      {emptyPlaces && (
        <p className="mt-3 text-theme-xs text-muted">
          {emptyPlaces}{" "}
          <Link to="/sources" className="link-target text-brand underline">
            See why and what to do
          </Link>
        </p>
      )}
    </div>
  );
}

/** A compact "This week": found, checked, applied and waiting, with a way into the full numbers. */
export function ThisWeekBody({ stats }: { stats: Pick<Stats, "week" | "waiting"> & { summary_text?: string } }) {
  return (
    <div>
      {stats.summary_text && <p className="mb-2 text-theme-sm">{stats.summary_text}</p>}
      <dl className="grid grid-cols-2 gap-2">
        {cardTiles(stats).map((t) => (
          <div key={t.label} className="flex flex-col-reverse rounded-xl bg-surface-2 px-3 py-2">
            <dt className="text-theme-xs text-muted">{t.label}</dt>
            <dd className="text-lg font-semibold tabular-nums leading-tight">{t.value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-1 text-theme-xs text-muted">The last 7 days.</p>
      <Link to="/insights" className="link-target mt-2 text-theme-sm text-brand underline">
        See all your numbers
      </Link>
    </div>
  );
}

export function ComingUpBody({ items }: { items: ComingUpItem[] }) {
  const more = comingUpAllLinks(items);
  return (
    <div>
      <ul className="space-y-1.5 text-theme-sm">
        {items.map((i) => (
          <li key={`${i.kind}-${i.job_id}-${i.when}`}>
            <Link to={comingUpTo(i)} className="link-target text-fg underline decoration-border underline-offset-2 hover:text-brand">
              {comingUpText(i)}
            </Link>
          </li>
        ))}
      </ul>
      <p className="mt-2 flex flex-wrap gap-x-4 text-theme-sm">
        {more.map((l) => (
          <Link key={l.to} to={l.to} className="link-target text-brand underline">
            {l.label}
          </Link>
        ))}
      </p>
    </div>
  );
}

export function FollowupsBody({ items, onChanged }: { items: Followup[]; onChanged: () => Promise<unknown> | void }) {
  const [busy, setBusy] = useState<number | null>(null);
  const act = async (f: Followup, what: "done" | "snooze") => {
    setBusy(f.id);
    try {
      if (what === "done") await dashboardApi.followupDone(f.id);
      else await dashboardApi.followupSnooze(f.id, 3);
      notify(what === "done" ? `Marked the follow-up for ${f.company} as done.` : `We will remind you about ${f.company} again in 3 days.`);
      await onChanged();
    } catch (e) {
      notify(errorText(e, "That did not work. Please try again."), "error");
    } finally {
      setBusy(null);
    }
  };
  return (
    <ul className="space-y-3">
      {items.map((f) => (
        <li key={f.id} className="text-theme-sm">
          <p className="min-w-0">
            {f.company} — {f.role}{" "}
            <span className="text-muted">
              (due {shortDate(f.follow_up_date)}
              {f.applied_date ? `, applied ${shortDate(f.applied_date)}` : ""})
            </span>{" "}
            <Link to={`/jobs/${f.id}/apply`} aria-label={`Open the ${f.role} follow-up at ${f.company}`} className="text-brand underline">
              Open
            </Link>
          </p>
          <span className="mt-1.5 flex gap-2">
            <Button variant="outline" small disabled={busy === f.id} onClick={() => act(f, "done")} aria-label={`Done with the ${f.role} follow-up at ${f.company}`} className="min-h-11 sm:min-h-0">
              Done
            </Button>
            <Button variant="outline" small disabled={busy === f.id} onClick={() => act(f, "snooze")} aria-label={`Remind me about ${f.company} in 3 days`} className="min-h-11 sm:min-h-0">
              In 3 days
            </Button>
          </span>
        </li>
      ))}
    </ul>
  );
}

// ---- the tiles ---------------------------------------------------------------------------------------------------------------

function Tile({ value, label }: { value: ReactNode; label: string }) {
  return (
    <div className="so-card flex flex-col-reverse rounded-2xl border border-border bg-surface px-3 py-2.5">
      <dt className="text-theme-xs text-muted">{label}</dt>
      <dd className="text-xl font-semibold leading-tight text-gray-800 dark:text-white/90">{value}</dd>
    </div>
  );
}

export function StatTiles({ data }: { data: Pick<Dashboard, "stats" | "urgent_days"> }) {
  const { stats } = data;
  if (!stats.total) return null;
  return (
    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
      <Tile value={stats.total} label="Jobs you are tracking" />
      <Tile value={stats.submitted} label="Applications sent" />
      <Tile value={stats.average_match === null ? "–" : `${stats.average_match}%`} label={stats.average_match === null ? "Average fit (check a job first)" : "Average fit"} />
      <Tile value={stats.urgent} label={`Closing within ${data.urgent_days} days`} />
    </dl>
  );
}
