import { useRouter, type Href } from "expo-router";
import React, { useEffect, useMemo, useState } from "react";
import { TouchableOpacity, View } from "react-native";

import { pipelineApi, type Insights } from "../../api/pipeline";
import { statsApi, type CalendarItem, type Goals, type Period, type Stats } from "../../api/stats";
import { BarList, Donut, FunnelBars, GroupedBars, Heatmap, LineChart, Ring, StatTile } from "../../components/charts";
import { Button, Card, Choice, Empty, ErrorBox, Field, Loading, Muted, notify, Row, Screen, SectionTitle, Text, useTheme } from "../../ui";
import { useAction, useLoad } from "../../ui/useApi";
import {
  anyChecked, averageText, calendarTo, calibrationLine, calibrationWaiting, count, currentMonth, dayLabel, funnelEmpty, funnelSentence, goalLine, heatText, heatWeeks, KIND_WORDS, marketText,
  monthGrid, monthLabel, PERIOD_LABELS, prepText, shiftMonth, stageShare, streakLine, strongShareText, waitingText, weekLabel, weekTiles, weeklyHasData, workLabel,
} from "./logic";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View>
      <SectionTitle>{title}</SectionTitle>
      <Card>{children}</Card>
    </View>
  );
}

function Table({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  const { colors } = useTheme();
  return (
    <View>
      <Row style={{ gap: 6, borderBottomWidth: 1, borderBottomColor: colors.border, paddingBottom: 6 }}>
        {head.map((h, i) => (
          <Text key={h} style={{ flex: i === 0 ? 2 : 1, textAlign: i === 0 ? "left" : "right", color: colors.textMuted, fontSize: 12, fontWeight: "600" }}>
            {h}
          </Text>
        ))}
      </Row>
      {rows.map((r, ri) => (
        <Row key={ri} style={{ gap: 6, paddingVertical: 7, borderBottomWidth: ri === rows.length - 1 ? 0 : 1, borderBottomColor: colors.border }}>
          {r.map((c, i) => (
            <Text key={i} style={{ flex: i === 0 ? 2 : 1, textAlign: i === 0 ? "left" : "right", fontSize: 13 }}>
              {String(c)}
            </Text>
          ))}
        </Row>
      ))}
    </View>
  );
}

// ---- pipeline insights (/insights) ----------------------------------------------------------------------------------------------

function PipelineInsights({ f }: { f: Insights }) {
  const router = useRouter();
  const rate = (n: number, r: number | null) => (r !== null ? `${n} (${r}%)` : String(n));
  if (f.applied === 0) {
    return (
      <Empty title="Nothing to show yet" hint="Once you record an application, this page shows how far your applications get and which channels lead to interviews." action={{ label: "Go to my dashboard", onPress: () => router.push("/" as Href) }} />
    );
  }
  return (
    <View>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10, marginBottom: 12 }}>
        <StatTile label="Tracked" value={f.tracked} />
        <StatTile label="Applied" value={f.applied} />
        <StatTile label="Reached an interview" value={f.interviewed} note={f.interview_rate !== null ? `${f.interview_rate}% of applied` : undefined} />
        <StatTile label="Got an offer" value={f.offered} note={f.offer_rate !== null ? `${f.offer_rate}% of applied` : undefined} />
      </View>
      {f.median_days_to_interview !== null ? <Text style={{ marginBottom: 6 }}>Typically {count(f.median_days_to_interview, "day")} from applying to your first interview.</Text> : null}
      {f.median_days_to_offer !== null ? <Text style={{ marginBottom: 6 }}>Typically {count(f.median_days_to_offer, "day")} from applying to your first offer.</Text> : null}
      {f.referred_applied > 0 ? <Text style={{ marginBottom: 6 }}>You were referred for {f.referred_applied} of the jobs you applied to; {f.referred_interviewed} of those reached an interview.</Text> : null}

      <Section title="Where you applied">
        <Table head={["Channel", "Applied", "Interviews", "Offers"]} rows={f.channels.map((r) => [r.label, r.applied, r.interviews, r.offers])} />
        <Muted style={{ marginTop: 8 }}>Interviews and offers count once you add them on the Interviews and Offers screens.</Muted>
      </Section>

      {f.by_score.length > 0 ? (
        <Section title="Does a higher match score lead anywhere?">
          <Muted style={{ marginBottom: 8 }}>Your own applications, grouped by the match band shown on the card when you applied. A band with one or two applications says little either way.</Muted>
          <Table head={["Match band", "Applied", "Interviews", "Offers"]} rows={f.by_score.map((r) => [r.label, r.applied, rate(r.interviews, r.interview_rate), rate(r.offers, r.offer_rate)])} />
        </Section>
      ) : null}

      {f.monthly_trend.length > 0 ? (
        <Section title="How your search has moved over time">
          <Muted style={{ marginBottom: 8 }}>Applications grouped by the month you applied, oldest first. A changed CV or channel shows up here as a shift in the rate, not just the total.</Muted>
          {f.monthly_trend.length > 1 ? (
            <View style={{ marginBottom: 12 }}>
              <LineChart
                caption="Applications and interviews by month"
                labels={f.monthly_trend.map((r) => monthLabel(r.month))}
                series={[
                  { label: "Applied", values: f.monthly_trend.map((r) => r.applied) },
                  { label: "Interviews", values: f.monthly_trend.map((r) => r.interviews) },
                ]}
              />
            </View>
          ) : null}
          <Table head={["Month", "Applied", "Interviews", "Offers"]} rows={f.monthly_trend.map((r) => [monthLabel(r.month), r.applied, rate(r.interviews, r.interview_rate), rate(r.offers, r.offer_rate)])} />
        </Section>
      ) : null}

      {f.rejection_patterns.length > 0 ? (
        <Section title="Keeps coming up in your rejections">
          <Muted style={{ marginBottom: 8 }}>
            Gap terms the free keyword match flagged on more than one job you were later rejected from. Not a verdict, a rejection usually has more than one reason, just a pattern worth a look.
          </Muted>
          <Row style={{ flexWrap: "wrap", gap: 6 }}>
            {f.rejection_patterns.map((r) => (
              <Text key={r.term} style={{ fontSize: 13 }}>
                {r.term} x{r.count}
              </Text>
            ))}
          </Row>
        </Section>
      ) : null}
    </View>
  );
}

// ---- your numbers (/stats) ---------------------------------------------------------------------------------------------------------

function Funnel({ stats }: { stats: Stats }) {
  const [period, setPeriod] = useState<Period>("90");
  const prefs = useLoad(() => statsApi.preferences());
  useEffect(() => {
    if (prefs.data?.insights_period) setPeriod(prefs.data.insights_period);
  }, [prefs.data?.insights_period]);
  if (!stats.funnel) return null;
  const f = stats.funnel[period];
  const pick = (p: Period) => {
    setPeriod(p);
    statsApi.savePreferences({ insights_period: p }).catch(() => {}); // remembered on the account; the screen already shows the choice
  };
  return (
    <View>
      <Choice<Period> options={(Object.keys(PERIOD_LABELS) as Period[]).map((p) => ({ value: p, label: PERIOD_LABELS[p] }))} value={period} onChange={pick} />
      {funnelEmpty(f) ? (
        <Muted>No applications sent {period === "all" ? "yet" : `in the last ${period} days`}. Do this next: record an application on a job, and the steps after it fill in here.</Muted>
      ) : (
        <View>
          <Text style={{ marginBottom: 12 }}>{funnelSentence(f, period)}</Text>
          <FunnelBars stages={f.stages.map((s, i) => ({ label: s.label, count: s.count, share: stageShare(s.count, i === 0 ? null : f.stages[i - 1].count) }))} />
        </View>
      )}
    </View>
  );
}

function GoalsBody({ goals, onSaved }: { goals: Goals | null | undefined; onSaved: () => void }) {
  const act = useAction();
  const [daily, setDaily] = useState(String(goals?.daily_target ?? 0));
  const [weekly, setWeekly] = useState(String(goals?.weekly_target ?? 0));
  const [editing, setEditing] = useState(false);
  useEffect(() => {
    setDaily(String(goals?.daily_target ?? 0));
    setWeekly(String(goals?.weekly_target ?? 0));
  }, [goals?.daily_target, goals?.weekly_target]);
  const save = async () => {
    const d = Math.max(0, Math.min(50, parseInt(daily, 10) || 0));
    const w = Math.max(0, Math.min(200, parseInt(weekly, 10) || 0));
    if (await act.run(() => statsApi.savePreferences({ goal_daily: d, goal_weekly: w }))) {
      notify("Goals saved.");
      setEditing(false);
      onSaved();
    }
  };
  return (
    <View>
      {goals ? (
        <View>
          <Row style={{ gap: 16, flexWrap: "wrap", marginBottom: 10 }}>
            {goals.daily_target > 0 ? <Ring done={goals.today} target={goals.daily_target} label="Today" /> : null}
            {goals.weekly_target > 0 ? <Ring done={goals.week} target={goals.weekly_target} label="Last 7 days" /> : null}
            <View style={{ flex: 1, minWidth: 160 }}>
              {goals.daily_target > 0 ? <Text>{goalLine(goals.today, goals.daily_target, "Today")}</Text> : null}
              {goals.weekly_target > 0 ? <Text>{goalLine(goals.week, goals.weekly_target, "Last 7 days")}</Text> : null}
              <Text>{streakLine(goals)}</Text>
            </View>
          </Row>
          <Text style={{ marginBottom: 6 }}>{goals.month.text}</Text>
          <Muted>{goals.explain}</Muted>
        </View>
      ) : (
        <Muted>Goals are off. If a daily or weekly target helps you, set one here. It is your choice, and you can turn it off again.</Muted>
      )}
      <View style={{ height: 10 }} />
      {editing ? (
        <View>
          <Field label="Applications I would like to send each day" value={daily} onChangeText={setDaily} keyboardType="number-pad" hint="0 turns the daily goal off." error={act.fields?.goal_daily} />
          <Field label="Applications I would like to send each week" value={weekly} onChangeText={setWeekly} keyboardType="number-pad" hint="Counted over the last 7 days. 0 turns the weekly goal off." error={act.fields?.goal_weekly} />
          {act.error && !act.fields ? <ErrorBox message={act.error} /> : null}
          <Row>
            <Button label="Save goals" busy={act.busy} onPress={save} />
            <Button label="Cancel" variant="ghost" onPress={() => setEditing(false)} />
          </Row>
        </View>
      ) : (
        <Button label={goals ? "Change my goals" : "Set a goal"} variant="secondary" onPress={() => setEditing(true)} />
      )}
    </View>
  );
}

function CalendarSection() {
  const { colors } = useTheme();
  const router = useRouter();
  const [month, setMonth] = useState(currentMonth);
  const [day, setDay] = useState<string | null>(null);
  const load = useLoad(() => statsApi.calendar(month), [month]);
  const cal = load.data;
  const rows = useMemo(() => (cal ? monthGrid(cal) : []), [cal]);
  const dot: Record<CalendarItem["kind"], string> = { interview: colors.accent, deadline: colors.warn, followup: colors.textMuted, offer: colors.good };
  const text = (i: CalendarItem) => `${KIND_WORDS[i.kind]}: ${i.company}, ${i.role}`;
  const go = (i: CalendarItem) => router.push(calendarTo(i) as Href);
  const Item = ({ i, withDate }: { i: CalendarItem; withDate?: boolean }) => (
    <TouchableOpacity onPress={() => go(i)} style={{ minHeight: 44, justifyContent: "center" }} accessibilityRole="link">
      <Text>
        {withDate ? <Text style={{ color: colors.textMuted }}>{i.date.slice(5)} </Text> : null}
        <Text style={{ color: colors.accent }}>{text(i)}</Text>
      </Text>
    </TouchableOpacity>
  );
  if (!cal) return load.error ? <ErrorBox message={load.error} onRetry={load.reload} /> : <Loading />;
  const dates = Object.keys(cal.days).sort();
  const dayItems = day ? cal.days[day] ?? [] : [];
  return (
    <View>
      <Row style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <Button label="Previous" variant="secondary" onPress={() => { setDay(null); setMonth(shiftMonth(month, -1)); }} />
        <Text style={{ fontWeight: "700" }}>{cal.label}</Text>
        <Button label="Next" variant="secondary" onPress={() => { setDay(null); setMonth(shiftMonth(month, 1)); }} />
      </Row>
      <Row style={{ gap: 0 }}>
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
          <Text key={d} style={{ flex: 1, textAlign: "center", fontSize: 11, color: colors.textMuted }}>
            {d}
          </Text>
        ))}
      </Row>
      {rows.map((row, ri) => (
        <Row key={ri} style={{ gap: 0 }}>
          {row.map((date, ci) => {
            if (!date) return <View key={ci} style={{ flex: 1, height: 46 }} />;
            const items = cal.days[date] ?? [];
            const today = date === cal.today;
            const picked = date === day;
            return (
              <TouchableOpacity
                key={date}
                onPress={() => setDay(picked ? null : date)}
                accessibilityLabel={`${dayLabel(date)}${today ? ", today" : ""}${items.length ? `: ${items.map(text).join("; ")}` : ""}`}
                style={{
                  flex: 1, height: 46, alignItems: "center", paddingTop: 4, borderRadius: 8, borderWidth: today || picked ? 2 : 0,
                  borderColor: picked ? colors.accent : colors.textMuted, backgroundColor: items.length ? colors.accentSoft : "transparent",
                }}
              >
                <Text style={{ fontSize: 13, fontWeight: today ? "700" : "400", color: today ? colors.accent : colors.text }}>{Number(date.slice(8))}</Text>
                <Row style={{ gap: 2, marginTop: 2 }}>
                  {items.slice(0, 3).map((i, n) => (
                    <View key={n} style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: dot[i.kind] }} />
                  ))}
                </Row>
              </TouchableOpacity>
            );
          })}
        </Row>
      ))}
      <Row style={{ flexWrap: "wrap", gap: 12, marginTop: 8 }}>
        {(Object.keys(KIND_WORDS) as CalendarItem["kind"][]).map((k) => (
          <Row key={k} style={{ gap: 5 }}>
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: dot[k] }} />
            <Muted>{KIND_WORDS[k]}</Muted>
          </Row>
        ))}
      </Row>
      {day ? (
        <View style={{ marginTop: 10 }}>
          <Text style={{ fontWeight: "700" }}>{dayLabel(day)}</Text>
          {dayItems.length === 0 ? <Muted>Nothing on this day.</Muted> : dayItems.map((i, n) => <Item key={n} i={i} />)}
        </View>
      ) : null}
      <Text style={{ fontWeight: "700", marginTop: 14 }}>Week ahead</Text>
      {cal.week_ahead.length === 0 ? (
        <Muted>Nothing in the next 7 days. Do this next: add an interview, a follow-up date or an apply-by date on a job and it shows here.</Muted>
      ) : (
        cal.week_ahead.map((i, n) => <Item key={n} i={i} withDate />)
      )}
      <Text style={{ fontWeight: "700", marginTop: 14 }}>This month</Text>
      {dates.length === 0 ? <Muted>Nothing on the calendar this month.</Muted> : dates.flatMap((d) => cal.days[d].map((i, n) => <Item key={`${d}-${n}`} i={i} withDate />))}
    </View>
  );
}

function YourNumbers({ onGoalsSaved }: { onGoalsSaved: () => void }) {
  const router = useRouter();
  const load = useLoad(() => statsApi.get());
  const s = load.data;
  if (load.loading) return <Loading />;
  if (!s) return <ErrorBox message={load.error ?? "We could not load your numbers."} onRetry={load.reload} />;
  const avg = averageText(s.match.average, s.match.average_applied);
  const heat = s.activity ? heatWeeks(s.activity) : [];
  return (
    <View>
      <Text style={{ fontSize: 20, fontWeight: "700", marginTop: 16 }}>Your numbers</Text>
      <Muted>Plain counts from your own search. They say what happened, not what will.</Muted>
      {s.summary_text ? (
        <Card style={{ marginTop: 10 }}>
          <Text>{s.summary_text}</Text>
        </Card>
      ) : null}
      {!s.has_jobs ? (
        <Empty title="No jobs yet" hint="Paste a job link on your dashboard or search for jobs, and your numbers fill in here." action={{ label: "Go to my dashboard", onPress: () => router.push("/" as Href) }} />
      ) : (
        <>
          <Section title="This week">
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
              {weekTiles(s.week).map((t) => (
                <StatTile key={t.key} label={t.label} value={t.value} note={t.note} />
              ))}
            </View>
            <Muted style={{ marginTop: 8 }}>The last 7 days, up to {dayLabel(s.as_of)}.</Muted>
          </Section>
          {s.funnel ? (
            <Section title="From sent to offer">
              <Funnel stats={s} />
            </Section>
          ) : null}
          <Section title="Last 8 weeks">
            {weeklyHasData(s.weekly) ? (
              <GroupedBars
                caption="Found, checked and applied each week"
                series={[{ label: "Found" }, { label: "Checked" }, { label: "Applied" }]}
                groups={s.weekly.map((w) => ({ label: weekLabel(w.start), values: [w.found, w.checked, w.applied] }))}
              />
            ) : (
              <Muted>Nothing in the last 8 weeks yet. Search for jobs or add one, and the weeks fill in.</Muted>
            )}
          </Section>
          {s.activity ? (
            <Section title="Your year">
              {s.activity.total_applied + s.activity.total_interviews === 0 ? (
                <Muted>Nothing sent or scheduled in the last year. Do this next: record an application, and each day you do fills a square here.</Muted>
              ) : (
                <View>
                  <Text style={{ fontWeight: "600", marginBottom: 8 }}>
                    {count(s.activity.total_applied, "application")} and {count(s.activity.total_interviews, "interview")} in the last year
                  </Text>
                  <Heatmap
                    weeks={heat.map((w) => w.map((c) => (c ? { date: c.date, level: c.level, text: heatText(c) } : null)))}
                  />
                </View>
              )}
            </Section>
          ) : null}
          <Section title="Goals and streak">
            <GoalsBody goals={s.goals} onSaved={() => { load.reload(); onGoalsSaved(); }} />
          </Section>
          <Section title="Calendar">
            <CalendarSection />
          </Section>
          <Section title="Match quality">
            {!anyChecked(s.match) && s.match.not_checked === 0 ? (
              <Muted>Check how well a few jobs fit you and the match quality will show here.</Muted>
            ) : (
              <View>
                <Donut slices={[...s.match.bands.map((b) => ({ label: b.label, value: b.count, color: b.color })), { label: "Not checked yet", value: s.match.not_checked }]} />
                {!anyChecked(s.match) ? <Muted style={{ marginTop: 8 }}>None of your jobs has been checked yet. Press Check my fit on a few jobs and the chart fills in.</Muted> : null}
                <View style={{ marginTop: 10, gap: 4 }}>
                  <Text>{avg.all}</Text>
                  <Text>{avg.applied}</Text>
                  <Text>{strongShareText(s.match)}</Text>
                </View>
              </View>
            )}
          </Section>
          {s.calibration ? (
            <Section title="Match and replies">
              {!s.calibration.enough ? (
                <Muted>{calibrationWaiting(s.calibration)}</Muted>
              ) : (
                <View>
                  <Text>Of the {s.calibration.scored} jobs you applied to that had a match percent, here is how many in each band got a reply (an interview or an offer).</Text>
                  <View style={{ marginTop: 8, gap: 4 }}>
                    {s.calibration.bands.map((b) => (
                      <Text key={b.label}>{calibrationLine(b)}</Text>
                    ))}
                  </View>
                  <Muted style={{ marginTop: 8 }}>{s.calibration.caveat}</Muted>
                </View>
              )}
            </Section>
          ) : null}
          <Section title="Waiting for a reply">
            <Text>{waitingText(s.waiting)}</Text>
            {s.waiting.longest.length > 0 ? (
              <View style={{ marginTop: 8 }}>
                <Muted>Waiting longest (no reply after {count(s.waiting.after_days, "day")} or more):</Muted>
                {s.waiting.longest.map((w) => (
                  <TouchableOpacity key={w.id} onPress={() => router.push(`/jobs/${w.id}/apply` as Href)} style={{ minHeight: 44, justifyContent: "center" }} accessibilityRole="link">
                    <Text>
                      {w.company} - {w.role} <Muted>({count(w.days, "day")}) Open</Muted>
                    </Text>
                  </TouchableOpacity>
                ))}
                <Muted>A short, polite follow-up is often welcome after a week or so. Open a job to write one.</Muted>
              </View>
            ) : null}
          </Section>
          <Section title="Where jobs come from">
            {s.sources.length === 0 ? (
              <Muted>Once you have jobs, this shows where they came from and which sources led to applications.</Muted>
            ) : (
              <Table head={["Source", "Found", "Applied", "Interviews"]} rows={s.sources.map((r) => [r.label, r.found, r.applied, r.interviews])} />
            )}
          </Section>
          <Section title="Kinds of work and countries">
            {s.work.length === 0 && s.countries.length === 0 ? (
              <Muted>Once your jobs say whether they are remote or where they are, this shows the mix.</Muted>
            ) : (
              <View style={{ gap: 14 }}>
                <BarList caption="Kinds of work" items={s.work.map((w) => ({ label: workLabel(w.kind), value: w.count }))} />
                {s.countries.length > 0 ? <BarList caption="Countries" items={s.countries.map((c) => ({ label: c.name, value: c.count }))} /> : <Muted>No country is stated on your jobs yet.</Muted>}
              </View>
            )}
          </Section>
          <Section title="Skills that keep coming up">
            {s.skills.gaps.length === 0 && s.skills.strengths.length === 0 ? (
              <Muted>Check how well a few jobs fit you and the skills that keep coming up will appear here.</Muted>
            ) : (
              <View style={{ gap: 12 }}>
                <View>
                  <Text style={{ fontWeight: "600" }}>Asked for, but your CV does not mention it</Text>
                  {s.skills.gaps.length === 0 ? <Muted>Nothing keeps coming up yet.</Muted> : s.skills.gaps.map((g) => <Text key={g.term}>{g.term} <Muted>({count(g.jobs, "job")} asked for it)</Muted></Text>)}
                  {s.skills.gaps.length > 0 ? <Muted style={{ marginTop: 4 }}>If you do have these skills, add them to your CV in Profile.{s.prep ? " To learn them, see your Prep plans." : ""}</Muted> : null}
                </View>
                <View>
                  <Text style={{ fontWeight: "600" }}>Strengths that keep showing up</Text>
                  {s.skills.strengths.length === 0 ? <Muted>Nothing keeps coming up yet.</Muted> : s.skills.strengths.map((g) => <Text key={g.term}>{g.term} <Muted>({count(g.jobs, "job")})</Muted></Text>)}
                </View>
              </View>
            )}
          </Section>
          {s.prep ? (
            <Section title="Prep">
              {s.prep.active_plans === 0 && s.prep.lessons_total === 0 ? (
                <Muted>You have no prep plan yet. Open a job with gaps and press Prepare for this job, or look at your Prep plans.</Muted>
              ) : (
                <View style={{ gap: 4 }}>
                  <Text>{prepText(s.prep).plans}</Text>
                  <Text>{prepText(s.prep).lessons}</Text>
                  <Text>{prepText(s.prep).streak}</Text>
                </View>
              )}
            </Section>
          ) : null}
          <Section title="Roles on the boards">
            {s.market ? <Text>{marketText(s.market)}</Text> : <Muted>Add the roles you want in Profile and we show how many matching postings the job boards listed each week.</Muted>}
          </Section>
        </>
      )}
    </View>
  );
}

export default function InsightsScreen() {
  const load = useLoad(() => pipelineApi.insights());
  const [nonce, setNonce] = useState(0);
  return (
    <Screen
      title="Insights"
      onRefresh={async () => {
        await load.refresh();
        setNonce((n) => n + 1);
      }}
      refreshing={load.refreshing}
    >
      <Text style={{ fontSize: 20, fontWeight: "700" }}>How your search is going</Text>
      <Muted style={{ marginBottom: 12 }}>Plain counts from your own tracker. They describe what happened, they do not predict anything, and small numbers say little.</Muted>
      {load.loading ? <Loading /> : load.error && !load.data ? <ErrorBox message={load.error} onRetry={load.reload} /> : null}
      {load.data ? <PipelineInsights f={load.data} /> : null}
      <YourNumbers key={nonce} onGoalsSaved={() => {}} />
    </Screen>
  );
}
