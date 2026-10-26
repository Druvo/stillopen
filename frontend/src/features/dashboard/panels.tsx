"use client";

import { Loader2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button, buttonClass, Card, Notice, Progress } from "@/components/ui";
import { errorText } from "@/lib/api";
import { Link, navigate } from "@/lib/router";
import { notify } from "@/lib/toast";
import type { Dashboard, Followup, Me, NextStep, ScanStatus, UpcomingInterview } from "@/lib/types";
import { jobsApi } from "@/features/jobs/api";
import { dashboardApi } from "./api";
import { entryText, interviewWhen, nextStepTarget, scanPercent, scanTitle, shortDate } from "./logic";
import { stashPrefill } from "./prefill";

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
      {me.legal_has_blanks && (
        <Notice>
          Sign-up is open, but your privacy policy or terms still have <code>[bracketed parts]</code> to fill in. Complete them under{" "}
          <a href="/admin/tracker/siteconfig/" className="text-brand underline">
            Site configuration &gt; Legal
          </a>{" "}
          before real people sign up. Run <code>python manage.py update_legal_text</code> first if you are still on the old placeholder text.
        </Notice>
      )}
      {me.jooble_sources_dormant && (
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
    </>
  );
}

/** "Your next step": the one thing worth doing now. A link into the app uses the router, a `#job-ID` link scrolls to that card. */
export function NextStepCard({ step, onCard }: { step: NextStep; onCard: (id: string) => void }) {
  const target = step.url ? nextStepTarget(step.url) : null;
  const cls = buttonClass("primary");
  return (
    <Card className="border-brand-300 dark:border-brand-500/40">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-bold tracking-wider text-brand">YOUR NEXT STEP</p>
          <h2 className="text-lg font-semibold text-gray-800 dark:text-white/90">{step.headline}</h2>
          <p className="text-theme-sm text-muted">{step.body}</p>
        </div>
        {target && step.label && target.kind === "app" && (
          <Link to={target.to} className={cls}>
            {step.label}
          </Link>
        )}
        {target && step.label && target.kind === "card" && (
          <a
            href={`#${target.id}`}
            className={cls}
            onClick={(e) => {
              e.preventDefault();
              onCard(target.id);
            }}
          >
            {step.label}
          </a>
        )}
        {target && step.label && target.kind === "other" && (
          <a href={target.href} className={cls}>
            {step.label}
          </a>
        )}
      </div>
    </Card>
  );
}

/** "Found a job you like? Paste its link": reads the posting, then opens Add job with what was found, to be checked before saving. */
export function QuickAdd() {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const go = async () => {
    const link = url.trim();
    if (!link) {
      notify("Paste a job link first", "error");
      return;
    }
    setBusy(true);
    try {
      const found = await jobsApi.quickAdd(link);
      stashPrefill(found);
      navigate("/jobs/add");
    } catch (e) {
      notify(errorText(e, "Could not fetch that page"), "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!busy) void go();
        }}
      >
        <label htmlFor="quickadd-url" className="mb-1 block text-theme-sm font-medium">
          Found a job you like? Paste its link
        </label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            id="quickadd-url"
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://..."
            className="min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 py-2 text-theme-sm"
          />
          <Button type="submit" disabled={busy}>
            {busy ? "Looking…" : "Look it up"}
          </Button>
        </div>
        <p className="mt-1 text-theme-xs text-muted">We read the title and description from the page and let you check them first. Nothing is saved until you say so.</p>
      </form>
    </Card>
  );
}

/** The search card: progress while it runs, the last result after, and the per-source log. */
export function ScanCard({ scan, starting }: { scan: ScanStatus | null; starting: boolean }) {
  if (!scan && !starting) return null;
  const running = starting || !!scan?.running;
  const view: ScanStatus = scan ?? { running: true, done: 0, total: 0, error: "", found: 0, added: 0, note: "", started_at: null, finished_at: null, phase: "reading", entries: [] };
  const percent = starting && !scan?.running ? 3 : scanPercent(view);
  return (
    <Card>
      <div className="flex items-center gap-2" aria-live="polite">
        {running && <Spinner />}
        <strong className="text-theme-sm">{starting && !scan?.running ? "Starting the search…" : scanTitle(view)}</strong>
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
      <details className="mt-2">
        <summary className="cursor-pointer text-theme-sm">Scan log -- where it searched and what it found</summary>
        <div className="mt-2 space-y-1">
          {view.entries.length === 0 && <p className="text-theme-xs text-muted">No sources checked yet.</p>}
          {view.entries.map((e, i) => (
            <div key={`${e.source}-${i}`} className="flex flex-col justify-between gap-0.5 text-theme-xs sm:flex-row sm:gap-3">
              <span>
                {e.source} <span className="text-muted">({e.connector})</span>
              </span>
              <span className={e.error ? "text-bad" : "text-muted"}>{entryText(e)}</span>
            </div>
          ))}
        </div>
      </details>
    </Card>
  );
}

export function ComingUp({ items }: { items: UpcomingInterview[] }) {
  if (items.length === 0) return null;
  return (
    <Card>
      <div className="flex flex-wrap items-baseline gap-x-3">
        <strong className="text-theme-sm">Coming up</strong>
        <Link to="/interviews" className="text-theme-sm text-brand underline">
          All interviews
        </Link>
      </div>
      <ul className="mt-2 space-y-1 text-theme-sm">
        {items.map((i) => (
          <li key={i.id}>
            {interviewWhen(i.when)} · {i.kind} — {i.company}, {i.role}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function FollowupsDue({ items, onChanged }: { items: Followup[]; onChanged: () => Promise<unknown> | void }) {
  const [busy, setBusy] = useState<number | null>(null);
  if (items.length === 0) return null;
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
    <Card>
      <strong className="text-theme-sm">Follow-ups due</strong>
      <ul className="mt-2 space-y-2">
        {items.map((f) => (
          <li key={f.id} className="flex flex-wrap items-center justify-between gap-2 text-theme-sm">
            <span className="min-w-0">
              {f.company} — {f.role}{" "}
              <span className="text-muted">
                (due {shortDate(f.follow_up_date)}
                {f.applied_date ? `, applied ${shortDate(f.applied_date)}` : ""})
              </span>{" "}
              <Link to={`/jobs/${f.id}/apply`} className="text-brand underline">
                Open
              </Link>
            </span>
            <span className="flex gap-2">
              <Button variant="outline" small disabled={busy === f.id} onClick={() => act(f, "done")}>
                Done
              </Button>
              <Button variant="outline" small disabled={busy === f.id} onClick={() => act(f, "snooze")}>
                In 3 days
              </Button>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Tile({ value, label }: { value: ReactNode; label: string }) {
  return (
    <Card className="p-4">
      <div className="text-2xl font-semibold text-gray-800 dark:text-white/90">{value}</div>
      <div className="text-theme-sm text-muted">{label}</div>
    </Card>
  );
}

export function StatTiles({ data }: { data: Pick<Dashboard, "stats" | "urgent_days"> }) {
  const { stats } = data;
  if (!stats.total) return null;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Tile value={stats.total} label="Jobs you are tracking" />
      <Tile value={stats.submitted} label="Applications sent" />
      <Tile value={stats.average_match === null ? "–" : `${stats.average_match}%`} label={stats.average_match === null ? "Average fit (check a job first)" : "Average fit"} />
      <Tile value={stats.urgent} label={`Closing within ${data.urgent_days} days`} />
    </div>
  );
}
