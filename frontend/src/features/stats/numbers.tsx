"use client";

import type { ReactNode } from "react";
import { buttonClass, Card, ErrorBox } from "@/components/ui";
import { errorText } from "@/lib/api";
import { Link } from "@/lib/router";
import { cn } from "@/lib/utils";
import { type Stats, useStats } from "./api";
import { BarList, WeeklyChart } from "./charts";
import { FunnelChart, CalendarSection, GoalsSection, Heatmap } from "./viz";
import { anyChecked, averageText, calibrationLine, calibrationWaiting, count, marketText, prepText, strongShareText, waitingText, weekTiles, weeklyHasData, workLabel } from "./logic";

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="mt-6">
      <h3 id={id} className="mb-2 font-semibold">
        {title}
      </h3>
      <Card>{children}</Card>
    </section>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="text-theme-sm text-muted">{children}</p>;
}

function ThisWeek({ week }: { week: Stats["week"] }) {
  return (
    <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
      {weekTiles(week).map((t) => (
        <li key={t.key} className={cn("rounded-xl border border-border p-3", t.value > 0 && t.to && "bg-surface-2")}>
          <p className="text-2xl font-semibold tabular-nums">{t.value}</p>
          <p className="text-theme-xs text-muted">{t.label}</p>
          {t.to && (
            <Link to={t.to} className="link-target mt-1 text-theme-xs text-brand underline">
              {t.note ?? "See them"}
            </Link>
          )}
        </li>
      ))}
    </ul>
  );
}

function MatchQuality({ match }: { match: Stats["match"] }) {
  if (!anyChecked(match) && match.not_checked === 0) return <Empty>Check how well a few jobs fit you and the match quality will show here.</Empty>;
  const avg = averageText(match.average, match.average_applied);
  const items = [...match.bands.map((b) => ({ label: b.label, value: b.count })), { label: "Not checked yet", value: match.not_checked }];
  const fills = [...match.bands.map((b) => b.color), undefined];
  return (
    <div className="space-y-3">
      <BarList caption="Your jobs by how well they match you" items={items} unit="Jobs" fills={fills} />
      {!anyChecked(match) && <Empty>None of your jobs has been checked yet. Press Check my fit on a few jobs and the bars above fill in.</Empty>}
      <ul className="space-y-1 text-theme-sm">
        <li>{avg.all}</li>
        <li>{avg.applied}</li>
        <li>{strongShareText(match)}</li>
      </ul>
    </div>
  );
}

function Calibration({ calibration }: { calibration: NonNullable<Stats["calibration"]> }) {
  if (!calibration.enough) return <Empty>{calibrationWaiting(calibration)}</Empty>;
  return (
    <div>
      <p className="text-theme-sm">Of the {calibration.scored} jobs you applied to that had a match percent, here is how many in each band got a reply (an interview or an offer).</p>
      <ul className="mt-2 space-y-1 text-theme-sm" data-testid="calibration">
        {calibration.bands.map((b) => (
          <li key={b.label}>{calibrationLine(b)}</li>
        ))}
      </ul>
      <p className="mt-2 text-theme-xs text-muted">{calibration.caveat}</p>
    </div>
  );
}

function Waiting({ waiting }: { waiting: Stats["waiting"] }) {
  return (
    <div>
      <p className="text-theme-sm">{waitingText(waiting)}</p>
      {waiting.longest.length > 0 && (
        <>
          <p className="mt-2 text-theme-xs text-muted">Waiting longest (no reply after {count(waiting.after_days, "day")} or more):</p>
          <ul className="mt-1 divide-y divide-border text-theme-sm">
            {waiting.longest.map((w) => (
              <li key={w.id} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 py-1.5">
                <span className="min-w-0 break-words">
                  {w.company} — {w.role}
                </span>
                <span className="flex items-baseline gap-3">
                  <span className="text-muted">{count(w.days, "day")}</span>
                  <Link to={`/jobs/${w.id}/apply`} className="text-brand underline">
                    Open
                  </Link>
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-theme-sm text-muted">A short, polite follow-up is often welcome after a week or so. Open a job to write one.</p>
        </>
      )}
    </div>
  );
}

function Sources({ sources }: { sources: Stats["sources"] }) {
  if (sources.length === 0) return <Empty>Once you have jobs, this shows where they came from and which sources led to applications.</Empty>;
  return (
    <div className="-mx-1 overflow-x-auto">
      <table className="w-full text-theme-sm">
        <caption className="sr-only">Where your jobs come from</caption>
        <thead>
          <tr className="border-b border-border text-left text-muted">
            <th scope="col" className="p-2 font-medium">Source</th>
            <th scope="col" className="p-2 text-right font-medium">Found</th>
            <th scope="col" className="p-2 text-right font-medium">Applied</th>
            <th scope="col" className="p-2 text-right font-medium">Interviews</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((s) => (
            <tr key={s.label} className="border-b border-border last:border-0">
              <th scope="row" className="p-2 text-left font-normal">{s.label}</th>
              <td className="p-2 text-right tabular-nums">{s.found}</td>
              <td className="p-2 text-right tabular-nums">{s.applied}</td>
              <td className="p-2 text-right tabular-nums">{s.interviews}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Skills({ skills, prepOn }: { skills: Stats["skills"]; prepOn: boolean }) {
  if (skills.gaps.length === 0 && skills.strengths.length === 0) {
    return <Empty>Check how well a few jobs fit you and the skills that keep coming up will appear here.</Empty>;
  }
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div>
        <h4 className="text-theme-sm font-medium">Asked for, but your CV does not mention it</h4>
        {skills.gaps.length === 0 ? (
          <Empty>Nothing keeps coming up yet.</Empty>
        ) : (
          <ul className="mt-1 space-y-1 text-theme-sm">
            {skills.gaps.map((g) => (
              <li key={g.term}>
                <strong>{g.term}</strong> <span className="text-muted">— {count(g.jobs, "job")} asked for it</span>
              </li>
            ))}
          </ul>
        )}
        {skills.gaps.length > 0 && (
          <p className="mt-2 text-theme-xs text-muted">
            If you do have these skills, add them to your CV in{" "}
            <Link to="/profile" className="text-brand underline">Profile</Link>.
            {prepOn && (
              <>
                {" "}To learn them, see your{" "}
                <Link to="/prep" className="text-brand underline">Prep plans</Link>.
              </>
            )}
          </p>
        )}
      </div>
      <div>
        <h4 className="text-theme-sm font-medium">Strengths that keep showing up</h4>
        {skills.strengths.length === 0 ? (
          <Empty>Nothing keeps coming up yet.</Empty>
        ) : (
          <ul className="mt-1 space-y-1 text-theme-sm">
            {skills.strengths.map((g) => (
              <li key={g.term}>
                <strong>{g.term}</strong> <span className="text-muted">— {count(g.jobs, "job")}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/** "Your numbers": plain counts from the person's own search. They describe what happened; they predict nothing and compare with no one. */
export function YourNumbers() {
  const query = useStats();
  if (query.isPending) return <p className="mt-6 text-muted">Loading your numbers…</p>;
  if (query.isError) return <div className="mt-6"><ErrorBox message={errorText(query.error, "We could not load your numbers.")} onRetry={() => query.refetch()} /></div>;
  const s = query.data;
  return (
    <div id="your-numbers" className="mt-8 scroll-mt-20">
      <h2 className="text-lg font-semibold">Your numbers</h2>
      <p className="text-theme-sm text-muted">Plain counts from your own search. They say what happened, not what will.</p>
      {s.summary_text && (
        <p data-testid="week-summary" className="mt-3 rounded-xl border border-border bg-surface-2 px-4 py-3 text-theme-sm">
          {s.summary_text}
        </p>
      )}
      {!s.has_jobs ? (
        <Card className="mt-3 py-8 text-center">
          <p className="mx-auto max-w-md text-theme-sm text-muted">
            You are not tracking any jobs yet. Paste a job link on your dashboard or search for jobs, and your numbers fill in here.
          </p>
          <Link to="/" className={`${buttonClass("primary")} mt-4`}>
            Go to my dashboard
          </Link>
        </Card>
      ) : (
        <>
          <Section id="stats-week" title="This week">
            <ThisWeek week={s.week} />
            <p className="mt-2 text-theme-xs text-muted">The last 7 days, up to {s.as_of}.</p>
          </Section>
          {s.funnel && (
            <Section id="stats-funnel" title="From sent to offer">
              <FunnelChart funnel={s.funnel} />
            </Section>
          )}
          <Section id="stats-weeks" title="Last 8 weeks">
            {weeklyHasData(s.weekly) ? <WeeklyChart weekly={s.weekly} /> : <Empty>Nothing in the last 8 weeks yet. Search for jobs or add one, and the weeks fill in.</Empty>}
          </Section>
          {s.activity && (
            <Section id="stats-activity" title="Your year">
              <Heatmap activity={s.activity} />
            </Section>
          )}
          <Section id="stats-goals" title="Goals and streak">
            <GoalsSection goals={s.goals} />
          </Section>
          <Section id="stats-calendar" title="Calendar">
            <CalendarSection />
          </Section>
          <Section id="stats-match" title="Match quality">
            <MatchQuality match={s.match} />
          </Section>
          {s.calibration && (
            <Section id="stats-calibration" title="Match and replies">
              <Calibration calibration={s.calibration} />
            </Section>
          )}
          <Section id="stats-waiting" title="Waiting for a reply">
            <Waiting waiting={s.waiting} />
          </Section>
          <Section id="stats-sources" title="Where jobs come from">
            <Sources sources={s.sources} />
          </Section>
          <Section id="stats-work" title="Kinds of work and countries">
            {s.work.length === 0 && s.countries.length === 0 ? (
              <Empty>Once your jobs say whether they are remote or where they are, this shows the mix.</Empty>
            ) : (
              <div className="grid gap-6 md:grid-cols-2">
                <BarList caption="Kinds of work" unit="Jobs" items={s.work.map((w) => ({ label: workLabel(w.kind), value: w.count }))} />
                {s.countries.length > 0 ? <BarList caption="Countries" unit="Jobs" items={s.countries.map((c) => ({ label: c.name, value: c.count }))} /> : <Empty>No country is stated on your jobs yet.</Empty>}
              </div>
            )}
          </Section>
          <Section id="stats-skills" title="Skills that keep coming up">
            <Skills skills={s.skills} prepOn={s.prep !== null} />
          </Section>
          {s.prep && (
            <Section id="stats-prep" title="Prep">
              {s.prep.active_plans === 0 && s.prep.lessons_total === 0 ? (
                <Empty>
                  You have no prep plan yet. Open a job with gaps and press Prepare for this job, or look at your{" "}
                  <Link to="/prep" className="text-brand underline">Prep plans</Link>.
                </Empty>
              ) : (
                <ul className="space-y-1 text-theme-sm">
                  <li>{prepText(s.prep).plans}</li>
                  <li>{prepText(s.prep).lessons}</li>
                  <li>{prepText(s.prep).streak}</li>
                </ul>
              )}
            </Section>
          )}
          <Section id="stats-market" title="Roles on the boards">
            {s.market ? (
              <p className="text-theme-sm">{marketText(s.market)}</p>
            ) : (
              <Empty>
                Add the roles you want in <Link to="/profile" className="text-brand underline">Profile</Link> and we show how many matching postings the job boards listed each week.
              </Empty>
            )}
          </Section>
        </>
      )}
    </div>
  );
}
