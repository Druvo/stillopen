"""Server-drawn data behind the dashboard and Insights visuals: the funnel, the year of activity, daily goals and streaks, the month calendar
and the dashboard's "Worth a look next" list.

Everything is a plain count or a plain date from the person's own jobs (the callers pass rows that already start from the owner), counted
on the person's own calendar (`services/tz`). Nothing here predicts anything, compares people, or changes data."""
import calendar as _calendar
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from ..models import Application, Interview, Offer

# --- funnel ---------------------------------------------------------------------------------------------------------------

PERIODS = {"30": 30, "90": 90, "all": None}
# Statuses that say a company answered / that an interview or an offer happened, for jobs whose interview or offer was never entered.
_REPLIED = {"Responded", "Interview", "Offer", "Hired"}
_INTERVIEWED = {"Interview", "Offer", "Hired"}
_OFFERED = {"Offer", "Hired"}


def funnel(apps, today: date) -> dict:
    """Of the applications sent in each period (30 days, 90 days, all time; counted from the applied date), how many got an answer,
    reached an interview and reached an offer. A stage counts everyone who got at least that far, so each number is no bigger than the one
    before it. `apps` carry prefetched interviews and offers. A job marked as applied that has no applied date counts in "all time" only."""
    out = {}
    for key, days in PERIODS.items():
        since = None if days is None else today - timedelta(days=days - 1)
        sent = replied = interviewed = offered = 0
        for a in apps:
            if not (a.applied_date or a.status.counts_as_applied):
                continue
            if since is not None and not (a.applied_date and since <= a.applied_date <= today):
                continue
            name = a.status.name
            has_offer = bool(a.offers.all()) or name in _OFFERED
            has_interview = has_offer or bool(a.interviews.all()) or name in _INTERVIEWED
            sent += 1
            replied += 1 if has_interview or name in _REPLIED else 0
            interviewed += 1 if has_interview else 0
            offered += 1 if has_offer else 0
        out[key] = {
            "since": since.isoformat() if since else None,
            "stages": [
                {"key": "sent", "label": "Applications sent", "count": sent},
                {"key": "replied", "label": "Heard back", "count": replied},
                {"key": "interviews", "label": "Reached an interview", "count": interviewed},
                {"key": "offers", "label": "Got an offer", "count": offered},
            ],
        }
    return out


# --- the year of activity ---------------------------------------------------------------------------------------------------

ACTIVITY_DAYS = 365


def activity(apps, today: date, zone) -> dict:
    """Per day, for the last 365 days: applications sent and interviews held or planned (cancelled ones left out). Only days with
    something in them are listed, so a quiet year is a short answer."""
    start = today - timedelta(days=ACTIVITY_DAYS - 1)
    days: dict[str, dict] = {}

    def bump(day: date, field: str):
        if start <= day <= today:
            days.setdefault(day.isoformat(), {"applied": 0, "interviews": 0})[field] += 1

    for a in apps:
        if a.applied_date:
            bump(a.applied_date, "applied")
        for i in a.interviews.all():
            if i.outcome != "cancelled":
                bump(timezone.localtime(i.scheduled_at, zone).date(), "interviews")
    return {
        "start": start.isoformat(), "end": today.isoformat(), "days": days,
        "total_applied": sum(d["applied"] for d in days.values()),
        "total_interviews": sum(d["interviews"] for d in days.values()),
    }


# --- goals and streaks --------------------------------------------------------------------------------------------------------

def streaks(applied_days: set[date], today: date) -> tuple[int, int]:
    """(current, best): runs of days in a row with at least one application sent. The current run is still alive if today has none yet
    but yesterday did (the day is not over), so a streak never "breaks" while the person can still add to it."""
    best = run = 0
    previous = None
    for day in sorted(applied_days):
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = day
    anchor = today if today in applied_days else today - timedelta(days=1)
    current = 0
    while anchor in applied_days:
        current += 1
        anchor -= timedelta(days=1)
    return current, best


def month_summary(apps, today: date, zone) -> dict:
    first = today.replace(day=1)
    applied = sum(1 for a in apps if a.applied_date and first <= a.applied_date <= today)
    interviews = sum(
        1 for a in apps for i in a.interviews.all()
        if i.outcome != "cancelled" and first <= timezone.localtime(i.scheduled_at, zone).date() <= today
    )
    month = f"{first:%B}"
    if not applied and not interviews:
        text = f"Nothing recorded in {month} yet."
    else:
        text = f"So far in {month} you sent {applied} {'application' if applied == 1 else 'applications'} and had {interviews} {'interview' if interviews == 1 else 'interviews'}."
    return {"label": month, "applied": applied, "interviews": interviews, "text": text}


def goals(apps, prefs: dict, today: date, zone) -> dict | None:
    """Today's progress against the person's own targets; None while both targets are off (the default), so nothing shows until they ask."""
    daily, weekly = int(prefs.get("goal_daily") or 0), int(prefs.get("goal_weekly") or 0)
    if daily <= 0 and weekly <= 0:
        return None
    days = {a.applied_date for a in apps if a.applied_date}
    today_count = sum(1 for a in apps if a.applied_date == today)
    week_start = today - timedelta(days=6)
    week_count = sum(1 for a in apps if a.applied_date and week_start <= a.applied_date <= today)
    current, best = streaks(days, today)
    return {
        "daily_target": daily, "weekly_target": weekly, "today": today_count, "week": week_count,
        "current_streak": current, "best_streak": best,
        "explain": "A streak is the number of days in a row on which you sent at least one application. Days off are fine; it simply starts again.",
        "month": month_summary(apps, today, zone),
    }


# --- calendar -----------------------------------------------------------------------------------------------------------------

def items_between(user, start: date, end: date, zone) -> list[dict]:
    """Interviews, follow-up dates, apply-by deadlines and offer reply-by dates from `start` to `end` (both included), oldest first.
    Each: {kind, date, when, label, company, role, job_id}. Jobs at a closed-out (terminal) status keep no deadline or follow-up here."""
    items = []
    lo = datetime.combine(start, time.min, tzinfo=zone)
    hi = datetime.combine(end + timedelta(days=1), time.min, tzinfo=zone)
    for i in Interview.objects.filter(owner=user, scheduled_at__gte=lo, scheduled_at__lt=hi).exclude(outcome="cancelled").select_related("application"):
        local = timezone.localtime(i.scheduled_at, zone)
        items.append({
            "kind": "interview", "date": local.date().isoformat(), "when": i.scheduled_at.isoformat(), "label": i.get_kind_display(),
            "company": i.application.company, "role": i.application.role, "job_id": i.application_id,
        })
    open_jobs = Application.objects.filter(owner=user, status__is_terminal=False)
    for a in open_jobs.filter(deadline__gte=start, deadline__lte=end):
        items.append({"kind": "deadline", "date": a.deadline.isoformat(), "when": a.deadline.isoformat(), "label": "Apply by", "company": a.company, "role": a.role, "job_id": a.pk})
    for a in open_jobs.filter(follow_up_date__gte=start, follow_up_date__lte=end):
        items.append({"kind": "followup", "date": a.follow_up_date.isoformat(), "when": a.follow_up_date.isoformat(), "label": "Follow up", "company": a.company, "role": a.role, "job_id": a.pk})
    for o in Offer.objects.filter(owner=user, status="open", deadline__gte=start, deadline__lte=end).select_related("application"):
        items.append({"kind": "offer", "date": o.deadline.isoformat(), "when": o.deadline.isoformat(), "label": "Reply to the offer by", "company": o.application.company, "role": o.application.role, "job_id": o.application_id})
    items.sort(key=lambda x: (x["when"], x["kind"], x["job_id"]))
    return items


def parse_month(text: str | None, today: date) -> date:
    """The first day of a "YYYY-MM" month (this month when blank). Raises ValueError for anything else, or a year outside 2000-2100."""
    if not text:
        return today.replace(day=1)
    year_text, _, month_text = text.partition("-")
    if len(year_text) != 4 or not year_text.isdigit() or len(month_text) != 2 or not month_text.isdigit():
        raise ValueError("Use a month like 2026-10.")
    year, month = int(year_text), int(month_text)
    if not (2000 <= year <= 2100 and 1 <= month <= 12):
        raise ValueError("Use a month like 2026-10.")
    return date(year, month, 1)


def month_view(user, first: date, today: date, zone) -> dict:
    """One month: every day with something on it, plus the next seven days (from today) as "week ahead"."""
    last = first.replace(day=_calendar.monthrange(first.year, first.month)[1])
    by_day: dict[str, list] = {}
    for item in items_between(user, first, last, zone):
        by_day.setdefault(item["date"], []).append(item)
    ahead = items_between(user, today, today + timedelta(days=6), zone)
    return {
        "month": f"{first:%Y-%m}", "label": f"{first:%B %Y}", "first": first.isoformat(), "last": last.isoformat(),
        "weekday_of_first": first.weekday(),  # 0 is Monday: the grid starts the week on Monday
        "today": today.isoformat(), "days": by_day, "week_ahead": ahead,
    }


# --- Worth a look next --------------------------------------------------------------------------------------------------------

WORTH_MAX = 6
WORTH_PER_KIND = 3
QUIET_DEFAULT_DAYS = 10


def _day_word(day: date, today: date) -> str:
    gap = (day - today).days
    return "today" if gap == 0 else "tomorrow" if gap == 1 else f"on {day:%a %d %b}"


def worth_a_look(apps, followups, comings, drafts, quiet_days: int, today: date, zone=None) -> list[dict]:
    """What to look at next, at most WORTH_MAX items, in a fixed order: interviews coming up (soonest first), offers waiting for an answer
    (earliest reply-by first, no date last), follow-ups that are due (longest overdue first), CV drafts waiting for a check (newest first),
    then applications with no reply for `quiet_days` or more (quietest first). At most WORTH_PER_KIND of each kind so one long list cannot
    hide the rest. Built only from rows the dashboard already loaded: no queries here.

    `apps`: the person's applications with interviews and offers prefetched. `followups`: due follow-up applications. `comings`: the
    "coming up" items. `drafts`: [(application, cv_version)], newest first."""
    out: list[dict] = []

    def add(kind, job_id, label, reason, **extra):
        out.append({"kind": kind, "job_id": job_id, "label": label, "reason": reason, **extra})

    for i in [c for c in comings if c["kind"] == "interview"][:WORTH_PER_KIND]:
        when = datetime.fromisoformat(i["when"])
        if zone is not None and timezone.is_aware(when):
            when = when.astimezone(zone)
        add("interview", i["job_id"], f"{i['company']}, {i['role']}", f"{i['label']} {_day_word(date.fromisoformat(i['date']), today)} at {when:%H:%M}.")
    offers = sorted(
        ((o, a) for a in apps for o in a.offers.all() if o.status == "open"),
        key=lambda pair: (pair[0].deadline is None, pair[0].deadline or date.max, pair[0].pk),
    )
    for o, a in offers[:WORTH_PER_KIND]:
        reason = f"Offer waiting for your answer, reply by {o.deadline:%a %d %b}." if o.deadline else "Offer waiting for your answer. No reply-by date is set."
        add("offer", a.pk, f"{a.company}, {a.role}", reason)
    for a in followups[:WORTH_PER_KIND]:
        late = (today - a.follow_up_date).days
        add("followup", a.pk, f"{a.company}, {a.role}", "Follow-up due today." if late <= 0 else f"Follow-up was due {late} {'day' if late == 1 else 'days'} ago.")
    for a, v in drafts[:WORTH_PER_KIND]:
        add("draft", a.pk, f"{a.company}, {a.role}", "A tailored CV draft is waiting for you to check it.", version_id=v.pk)
    due = {a.pk for a in followups}
    quiet = sorted(
        (
            (a, (today - a.applied_date).days) for a in apps
            if a.applied_date and a.status.counts_as_applied and not a.status.is_terminal and not a.interviews.all() and not a.offers.all() and a.pk not in due
            and (today - a.applied_date).days >= quiet_days
        ),
        key=lambda pair: (-pair[1], pair[0].pk),
    )
    for a, days in quiet[:WORTH_PER_KIND]:
        add("quiet", a.pk, f"{a.company}, {a.role}", f"No reply for {days} days since you applied. A short note can help.")
    return out[:WORTH_MAX]
