"use client";

import { useQuery } from "@tanstack/react-query";
import { type KeyboardEvent, useRef, useState } from "react";
import { Button } from "@/components/ui";
import { errorText } from "@/lib/api";
import { Link } from "@/lib/router";
import { usePreferences } from "@/lib/use-preferences";
import { cn } from "@/lib/utils";
import { type Activity, type CalendarItem, type Funnel, type Goals, type Period, statsApi } from "./api";
import { Bar, Chart } from "./charts";
import { calendarTo, funnelEmpty, funnelSentence, goalLine, goalPercent, heatText, heatWeeks, KIND_WORDS, monthGrid, moveDay, PERIOD_LABELS, shiftMonth, stageShare, streakLine } from "./viz-logic";

// ---- the funnel -----------------------------------------------------------------------------------------------------------

const PERIODS: Period[] = ["30", "90", "all"];

/** Applications sent, heard back, interviews, offers: for the last 30 days, 90 days or all time. The tab is remembered on the account. */
export function FunnelChart({ funnel }: { funnel: Record<Period, Funnel> }) {
  const { prefs, update } = usePreferences();
  const period = prefs.insights_period;
  const f = funnel[period];
  const max = Math.max(1, f.stages[0].count);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (e: KeyboardEvent, i: number) => {
    const n = e.key === "ArrowRight" ? (i + 1) % 3 : e.key === "ArrowLeft" ? (i + 2) % 3 : -1;
    if (n < 0) return;
    e.preventDefault();
    update({ insights_period: PERIODS[n] });
    tabRefs.current[n]?.focus();
  };
  return (
    <div>
      <div role="tablist" aria-label="Period" className="mb-3 inline-flex rounded-xl border border-border p-0.5">
        {PERIODS.map((p, i) => (
          <button
            key={p}
            ref={(el) => {
              tabRefs.current[i] = el;
            }}
            id={`funnel-tab-${p}`}
            type="button"
            role="tab"
            aria-selected={period === p}
            aria-controls="funnel-panel"
            tabIndex={period === p ? 0 : -1}
            onClick={() => update({ insights_period: p })}
            onKeyDown={(e) => onKey(e, i)}
            className={cn("min-h-11 rounded-lg px-3 text-theme-sm sm:min-h-8", period === p ? "border border-brand bg-brand-soft font-medium text-fg" : "border border-transparent text-muted hover:text-fg")}
          >
            {PERIOD_LABELS[p]}
          </button>
        ))}
      </div>
      <div id="funnel-panel" role="tabpanel" aria-labelledby={`funnel-tab-${period}`}>
        {funnelEmpty(f) ? (
          <p className="text-theme-sm text-muted">
            No applications sent {period === "all" ? "yet" : `in the last ${period} days`}. Do this next: record an application on a job, and the steps after it fill in here.
          </p>
        ) : (
          <>
            <p className="mb-3 text-theme-sm">{funnelSentence(f, period)}</p>
            <Chart
              caption="From applications sent to offers"
              table={
                <table>
                  <caption>Funnel, {PERIOD_LABELS[period]}</caption>
                  <thead>
                    <tr>
                      <th scope="col">Step</th>
                      <th scope="col">People</th>
                    </tr>
                  </thead>
                  <tbody>
                    {f.stages.map((s, i) => (
                      <tr key={s.key}>
                        <th scope="row">{s.label}</th>
                        <td>{stageShare(s.count, i === 0 ? null : f.stages[i - 1].count)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              }
            >
              <div className="space-y-1.5">
                {f.stages.map((s) => (
                  <Bar key={s.key} label={s.label} value={s.count} max={max} />
                ))}
              </div>
            </Chart>
          </>
        )}
      </div>
    </div>
  );
}

// ---- the year of activity --------------------------------------------------------------------------------------------------

const STEPS = [0, 25, 45, 70, 100]; // percent of the brand colour for each step

/** A year as a grid of days, one column per week. Colour is only a hint: every day also has its counts as text for screen readers. */
export function Heatmap({ activity }: { activity: Activity }) {
  const weeks = heatWeeks(activity);
  const total = activity.total_applied + activity.total_interviews;
  if (total === 0) {
    return <p className="text-theme-sm text-muted">Nothing sent or scheduled in the last year. Do this next: record an application, and each day you do fills a square here.</p>;
  }
  const days = weeks.flat().filter((c) => c && c.total > 0);
  return (
    <figure className="min-w-0">
      <figcaption className="mb-2 text-theme-sm font-medium">
        {activity.total_applied} {activity.total_applied === 1 ? "application" : "applications"} and {activity.total_interviews} {activity.total_interviews === 1 ? "interview" : "interviews"} in the last year
      </figcaption>
      <div aria-hidden className="overflow-x-auto pb-1">
        <div className="flex gap-[3px]">
          {weeks.map((week, wi) => (
            <div key={wi} className="flex flex-col gap-[3px]">
              {week.map((c, di) => (
                <span
                  key={di}
                  title={c ? heatText(c) : undefined}
                  className={cn("block h-3 w-3 rounded-[3px]", c ? "border border-border" : "border border-transparent")}
                  style={c ? { background: `color-mix(in srgb, var(--brand) ${STEPS[c.level]}%, transparent)` } : undefined}
                />
              ))}
            </div>
          ))}
        </div>
        <p className="mt-2 flex items-center gap-1 text-theme-xs text-muted">
          Fewer
          {STEPS.map((s) => (
            <span key={s} className="inline-block h-3 w-3 rounded-[3px] border border-border" style={{ background: `color-mix(in srgb, var(--brand) ${s}%, transparent)` }} />
          ))}
          More
        </p>
      </div>
      <div className="sr-only">
        <table>
          <caption>Days with activity in the last year</caption>
          <thead>
            <tr>
              <th scope="col">Day</th>
              <th scope="col">Applications sent</th>
              <th scope="col">Interviews</th>
            </tr>
          </thead>
          <tbody>
            {days.map((c) => (
              <tr key={c!.date}>
                <th scope="row">{c!.date}</th>
                <td>{c!.applied}</td>
                <td>{c!.interviews}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}

// ---- goals --------------------------------------------------------------------------------------------------------------------

/** A ring that fills as `done` approaches `target`. The number in the middle is the same figure as text. */
export function Ring({ done, target, label }: { done: number; target: number; label: string }) {
  const pct = goalPercent(done, target);
  const r = 28;
  const c = 2 * Math.PI * r;
  return (
    <div role="img" aria-label={`${label}: ${done} of ${target}`} className="relative h-16 w-16 shrink-0">
      <svg viewBox="0 0 70 70" className="h-full w-full -rotate-90" aria-hidden>
        <circle cx="35" cy="35" r={r} fill="none" strokeWidth="7" stroke="var(--border)" />
        <circle cx="35" cy="35" r={r} fill="none" strokeWidth="7" stroke="var(--brand)" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - pct / 100)} />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-theme-sm font-semibold tabular-nums" aria-hidden>
        {done}/{target}
      </span>
    </div>
  );
}

export function GoalsBody({ goals }: { goals: Goals }) {
  return (
    <div className="space-y-2 text-theme-sm" data-testid="goals">
      <div className="flex flex-wrap items-center gap-4">
        {goals.daily_target > 0 && <Ring done={goals.today} target={goals.daily_target} label="Today" />}
        {goals.weekly_target > 0 && <Ring done={goals.week} target={goals.weekly_target} label="Last 7 days" />}
        <ul className="min-w-0 space-y-0.5">
          {goals.daily_target > 0 && <li>{goalLine(goals.today, goals.daily_target, "Today")}</li>}
          {goals.weekly_target > 0 && <li>{goalLine(goals.week, goals.weekly_target, "Last 7 days")}</li>}
          <li>{streakLine(goals)}</li>
        </ul>
      </div>
      <p>{goals.month.text}</p>
      <p className="text-theme-xs text-muted">{goals.explain}</p>
    </div>
  );
}

export function GoalsSection({ goals }: { goals: Goals | null | undefined }) {
  if (!goals) {
    return (
      <p className="text-theme-sm text-muted">
        Goals are off. If a daily or weekly target helps you, set one in{" "}
        <Link to="/profile#goals" className="text-brand underline">
          Profile
        </Link>
        . It is your choice, and you can turn it off again.
      </p>
    );
  }
  return <GoalsBody goals={goals} />;
}

// ---- calendar -----------------------------------------------------------------------------------------------------------------

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DOT: Record<CalendarItem["kind"], string> = { interview: "bg-brand", deadline: "bg-warn", followup: "bg-muted", offer: "bg-good" };

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function itemText(i: CalendarItem): string {
  return `${KIND_WORDS[i.kind]}: ${i.company}, ${i.role}`;
}

/** A month as a keyboard-friendly grid (arrow keys move between days; Tab leaves it), with the week ahead as a list beside it. */
export function CalendarSection() {
  const [month, setMonth] = useState(currentMonth);
  const [focus, setFocus] = useState<string | null>(null);
  const gridRef = useRef<HTMLTableElement>(null);
  const query = useQuery({ queryKey: ["stats", "calendar", month], queryFn: () => statsApi.calendar(month) });
  if (query.isPending) return <p className="text-theme-sm text-muted">Loading the calendar…</p>;
  if (query.isError) return <p role="alert" className="text-theme-sm text-bad">{errorText(query.error, "We could not load the calendar.")}</p>;
  const cal = query.data;
  const rows = monthGrid(cal);
  const stop = focus && focus >= cal.first && focus <= cal.last ? focus : cal.today >= cal.first && cal.today <= cal.last ? cal.today : cal.first;
  const empty = Object.keys(cal.days).length === 0 && cal.week_ahead.length === 0;
  const onKey = (e: KeyboardEvent<HTMLTableElement>) => {
    if (!e.key.startsWith("Arrow")) return;
    const next = moveDay(stop, e.key, cal.first, cal.last);
    e.preventDefault();
    setFocus(next);
    requestAnimationFrame(() => gridRef.current?.querySelector<HTMLElement>(`[data-date="${next}"]`)?.focus());
  };
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_16rem]">
      <div className="min-w-0">
        <div className="mb-2 flex items-center justify-between gap-2">
          <Button variant="outline" small onClick={() => setMonth(shiftMonth(month, -1))} aria-label="Previous month">
            Previous
          </Button>
          <h4 className="text-theme-sm font-medium" aria-live="polite">
            {cal.label}
          </h4>
          <Button variant="outline" small onClick={() => setMonth(shiftMonth(month, 1))} aria-label="Next month">
            Next
          </Button>
        </div>
        <table ref={gridRef} role="grid" aria-label={`Calendar, ${cal.label}`} onKeyDown={onKey} className="w-full table-fixed border-collapse text-theme-xs">
          <thead>
            <tr>
              {WEEKDAYS.map((d) => (
                <th key={d} scope="col" className="p-1 text-center font-medium text-muted">
                  {d}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri}>
                {row.map((date, ci) => {
                  if (!date) return <td key={ci} className="border border-border/50 bg-surface-2/40" />;
                  const items = cal.days[date] ?? [];
                  const isToday = date === cal.today;
                  return (
                    <td
                      key={date}
                      role="gridcell"
                      data-date={date}
                      tabIndex={date === stop ? 0 : -1}
                      aria-current={isToday ? "date" : undefined}
                      aria-label={`${date}${isToday ? ", today" : ""}${items.length ? `: ${items.map(itemText).join("; ")}` : ""}`}
                      onFocus={() => setFocus(date)}
                      className={cn("h-14 border border-border align-top p-1 focus:outline focus:outline-2 focus:outline-brand sm:h-20", isToday && "bg-surface-2 ring-2 ring-inset ring-brand")}
                    >
                      <span className={cn("block tabular-nums", isToday ? "font-bold text-brand" : "text-muted")}>
                        {Number(date.slice(8))}
                        {isToday && <span className="sr-only"> (today)</span>}
                      </span>
                      <span className="mt-0.5 flex flex-wrap gap-0.5" aria-hidden>
                        {items.slice(0, 4).map((i, n) => (
                          <span key={n} className={cn("inline-block h-2 w-2 rounded-full", DOT[i.kind])} />
                        ))}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-theme-xs text-muted">
          {(Object.keys(KIND_WORDS) as CalendarItem["kind"][]).map((k) => (
            <li key={k} className="flex items-center gap-1.5">
              <span className={cn("inline-block h-2 w-2 rounded-full", DOT[k])} />
              {KIND_WORDS[k]}
            </li>
          ))}
        </ul>
        <MonthList cal={cal} />
      </div>
      <div>
        <h4 className="mb-1 text-theme-sm font-medium">Week ahead</h4>
        {cal.week_ahead.length === 0 ? (
          <p className="text-theme-sm text-muted">Nothing in the next 7 days.{empty ? " Do this next: add an interview, a follow-up date or an apply-by date on a job and it shows here." : ""}</p>
        ) : (
          <ul className="space-y-1.5 text-theme-sm">
            {cal.week_ahead.map((i, n) => (
              <li key={n}>
                <span className="text-muted">{i.date.slice(5)}</span>{" "}
                <Link to={calendarTo(i)} className="link-target underline decoration-border underline-offset-2 hover:text-brand">
                  {itemText(i)}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/** The month's items as a plain list below the grid, so a link is one Tab away and phones do not need to tap tiny squares. */
function MonthList({ cal }: { cal: { days: Record<string, CalendarItem[]> } }) {
  const dates = Object.keys(cal.days).sort();
  if (dates.length === 0) return <p className="mt-3 text-theme-sm text-muted">Nothing on the calendar this month.</p>;
  return (
    <ul className="mt-3 space-y-1 text-theme-sm" aria-label="This month in a list">
      {dates.flatMap((d) =>
        cal.days[d].map((i, n) => (
          <li key={`${d}-${n}`}>
            <span className="text-muted">{d.slice(5)}</span>{" "}
            <Link to={calendarTo(i)} className="link-target underline decoration-border underline-offset-2 hover:text-brand">
              {itemText(i)}
            </Link>
          </li>
        )),
      )}
    </ul>
  );
}
