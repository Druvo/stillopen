"""Numbers about one person's own search, for the Insights screen and a small "This week" card.

Everything is counted from what the person has done in the app (jobs found, checked, applied to, interviews, follow-ups) and from what the
shared job boards listed for their roles. Plain counts and plain rates: never a prediction, never a comparison with other people, and
nothing that could show another person's data (every query starts from the owner)."""
import re
from collections import Counter
from datetime import date, datetime, time, timedelta
from statistics import median

from django.core.cache import cache
from django.utils import timezone

from ..models import Application, Interview, JobSource, Posting, PrepPlan, ScoreBand, SiteConfig, UserProfile
from . import apply as apply_service
from . import geo, quiz, scan, tz
from .cards import band_for

WEEKS = 8
WAITING_AFTER_DAYS = 7  # an application with no reply for this long shows up in "waiting longest"
MARKET_CACHE_SECONDS = 15 * 60
_MISSING = re.compile(r"doesn't mention:\s*(.+)$", re.I)


def _pct(part, whole):
    return round(100 * part / whole) if whole else None


def _day(value, zone=None):
    """A date from a date or a datetime (in the person's timezone; `zone` is theirs, else the site's)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return timezone.localtime(value, zone).date() if timezone.is_aware(value) else value.date()
    return value


def _week_starts(today: date) -> list[date]:
    """The start days of the last WEEKS 7-day windows, oldest first; the last window ends today."""
    return [today - timedelta(days=7 * i + 6) for i in reversed(range(WEEKS))]


def _skills(apps) -> dict:
    """Skills that keep coming up, from the fit checks already done: what the person's material shows, and what jobs ask for that it does not."""
    gaps, strengths = Counter(), Counter()
    for app in apps:
        seen_gap, seen_strength = set(), set()
        for insight in app.insights.all():
            text = insight.text.strip()
            if insight.kind == "gap":
                match = _MISSING.search(text)
                if match:  # only the keyword check's own wording: free-text AI gaps rarely repeat word for word
                    seen_gap.add(match.group(1).strip().lower())
            elif insight.kind == "strength" and 0 < len(text) <= 30:
                seen_strength.add(text.lower())
        gaps.update(seen_gap)
        strengths.update(seen_strength)
    def top(counter):
        return [{"term": term, "jobs": count} for term, count in counter.most_common(8) if count >= 2]
    return {"gaps": top(gaps), "strengths": top(strengths)}


def _market(user, profile) -> dict | None:
    """How many postings that match the person's roles the shared boards listed this week, against last week."""
    roles = [line.strip() for line in profile.target_roles.splitlines() if line.strip()]
    if not roles:
        return None
    key = f"stats-market:{user.pk}:{hash(tuple(roles))}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    now = timezone.now()
    sources = JobSource.for_user(user, enabled=True)
    rows = Posting.objects.filter(source__in=sources, first_seen_at__gte=now - timedelta(days=14)).values_list("title", "first_seen_at")[:20000]
    this_week = last_week = 0
    for title, seen in rows:
        if scan._matches(title, roles):
            if seen >= now - timedelta(days=7):
                this_week += 1
            else:
                last_week += 1
    result = {"this_week": this_week, "last_week": last_week, "roles": roles[:5]}
    cache.set(key, result, MARKET_CACHE_SECONDS)
    return result


def _prep(user, config, today: date) -> dict | None:
    if not config.prep_enabled:
        return None
    plans = list(PrepPlan.objects.filter(owner=user, status__in=["active", "done"]))
    if not plans:
        return {"active_plans": 0, "lessons_done": 0, "lessons_total": 0, "streak": 0}
    done = total = 0
    for plan in plans:
        d, t = plan.progress_counts()
        done, total = done + d, total + t
    return {
        "active_plans": sum(1 for p in plans if p.status == "active"),
        "lessons_done": done,
        "lessons_total": total,
        "streak": max(quiz.streak(plan, today) for plan in plans),
    }


def _n(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")


def summary_text(has_jobs: bool, week: dict, waiting: dict, skills: dict) -> str:
    """The week's numbers as three to five plain sentences. Free: it only rephrases counts already worked out, and predicts nothing."""
    if not has_jobs:
        return "Nothing to report yet. Add a job or run a search, and your week will be summed up here."
    parts = []
    if week["found"] or week["applied"]:
        parts.append(f"This week you added {_n(week['found'], 'job')} and applied to {week['applied']}.")
    else:
        parts.append("You have not added a job or applied to one in the last week.")
    if week["interviews_soon"]:
        parts.append(f"You have {_n(week['interviews_soon'], 'interview')} coming up.")
    if week["followups_due"]:
        parts.append(f"{_n(week['followups_due'], 'follow-up')} {'is' if week['followups_due'] == 1 else 'are'} due.")
    if waiting["count"]:
        longest = waiting["longest"][0]["days"] if waiting["longest"] else None
        tail = f"; the longest has waited {longest} days" if longest else ""
        parts.append(f"{waiting['count']} {'is' if waiting['count'] == 1 else 'are'} waiting for a reply{tail}.")
    if skills["gaps"]:
        parts.append(f"The skill that keeps coming up in your jobs and is not in your CV is {skills['gaps'][0]['term']}.")
    elif week["closing_soon"]:
        parts.append(f"{_n(week['closing_soon'], 'job')} close{'s' if week['closing_soon'] == 1 else ''} soon.")
    return " ".join(parts[:5])


CALIBRATION_MIN = 8
CALIBRATION_CAVEAT = "A small number of applications; read it as a hint, not a rule."


def calibration(applied, answered_ids: set, percents: dict, bands) -> dict:
    """Among the jobs the person applied to that have a match percent: per match band, how many they applied to and how many got a reply
    (an interview or an offer). A count of what happened, never a prediction; shown only from CALIBRATION_MIN scored applications on."""
    scored = [a for a in applied if percents.get(a.pk) is not None]
    out = {"enough": len(scored) >= CALIBRATION_MIN, "scored": len(scored), "needed": CALIBRATION_MIN, "caveat": CALIBRATION_CAVEAT, "bands": []}
    if not out["enough"]:
        return out
    rows = {b.label: {"label": b.label, "color": b.color, "min_percent": b.min_percent, "applied": 0, "replies": 0} for b in bands}
    for a in scored:
        band = band_for(percents[a.pk], bands)
        if band is None:
            continue
        rows[band.label]["applied"] += 1
        rows[band.label]["replies"] += 1 if a.pk in answered_ids else 0
    out["bands"] = [{**r, "reply_rate": _pct(r["replies"], r["applied"])} for r in rows.values()]
    return out


def candidate_stats(user, today: date | None = None) -> dict:
    zone = tz.zone_for(user)
    today = today or timezone.now().astimezone(zone).date()
    config = SiteConfig.for_user(user)
    profile = UserProfile.for_user(user)
    bands = list(ScoreBand.objects.all())
    apps = list(
        Application.objects.filter(owner=user)
        .select_related("status", "source", "posting__source")
        .prefetch_related("insights", "interviews", "offers")
    )
    week_start = today - timedelta(days=6)
    applied = [a for a in apps if a.applied_date or a.status.counts_as_applied]
    answered = [a for a in applied if a.interviews.all() or a.offers.all()]
    applied_ids = {a.pk for a in applied}
    answered_ids = {a.pk for a in answered}

    # --- this week ------------------------------------------------------------------------------
    window_end = datetime.combine(today + timedelta(days=15), time.min, tzinfo=zone)
    interviews_soon = Interview.objects.filter(owner=user, outcome="pending", scheduled_at__gte=timezone.now(), scheduled_at__lt=window_end).count()
    week = {
        "found": sum(1 for a in apps if a.found_date >= week_start),
        "checked": sum(1 for a in apps if a.ai_evaluated_at and _day(a.ai_evaluated_at, zone) >= week_start),
        "applied": sum(1 for a in apps if a.applied_date and a.applied_date >= week_start),
        "interviews_soon": interviews_soon,
        "followups_due": apply_service.due_followups(user, today).count(),
        "closing_soon": sum(1 for a in apps if a.deadline and 0 <= (a.deadline - today).days <= config.urgent_days and not a.status.is_terminal),
        "went_cold": sum(1 for a in apps if a.live_state == "expired" and a.live_checked_at and _day(a.live_checked_at, zone) >= week_start),
    }

    # --- the last eight weeks ---------------------------------------------------------------------
    starts = _week_starts(today)
    weekly = []
    for start in starts:
        end = start + timedelta(days=6)
        weekly.append({
            "start": start.isoformat(),
            "found": sum(1 for a in apps if start <= a.found_date <= end),
            "checked": sum(1 for a in apps if a.ai_evaluated_at and start <= _day(a.ai_evaluated_at, zone) <= end),
            "applied": sum(1 for a in apps if a.applied_date and start <= a.applied_date <= end),
        })

    # --- how good the matches are -------------------------------------------------------------------
    percents = {a.pk: a.match_percent(config.score_scale) for a in apps}
    counts = Counter()
    for a in apps:
        band = band_for(percents[a.pk], bands)
        counts[band.label if band else None] += 1
    scored = [p for p in percents.values() if p is not None]
    applied_scored = [percents[a.pk] for a in applied if percents[a.pk] is not None]
    top_band = bands[0] if bands else None
    match = {
        "bands": [{"label": b.label, "color": b.color, "count": counts.get(b.label, 0)} for b in bands],
        "not_checked": counts.get(None, 0),
        "average": round(sum(scored) / len(scored)) if scored else None,
        "average_applied": round(sum(applied_scored) / len(applied_scored)) if applied_scored else None,
        "top_band": top_band.label if top_band else "",
        "strong_share_applied": _pct(sum(1 for p in applied_scored if top_band and p >= top_band.min_percent), len(applied_scored)),
    }

    # --- where jobs come from -------------------------------------------------------------------------
    def source_of(app):
        if app.source_id:
            return app.source.name
        if app.posting_id:
            return app.posting.source.name
        return "Added by you"

    by_source: dict = {}
    for a in apps:
        row = by_source.setdefault(source_of(a), {"label": source_of(a), "found": 0, "applied": 0, "interviews": 0})
        row["found"] += 1
        if a.pk in applied_ids:
            row["applied"] += 1
            row["interviews"] += 1 if a.interviews.all() else 0
    sources = sorted(by_source.values(), key=lambda r: (-r["found"], r["label"]))[:6]

    work = Counter(a.arrangement or "unknown" for a in apps)
    countries = Counter(geo.country_name(a.country) for a in apps if a.country)

    # --- waiting for a reply ----------------------------------------------------------------------------
    waiting_rows = []
    for a in applied:
        if a.applied_date and not a.status.is_terminal and a.pk not in answered_ids:
            days = (today - a.applied_date).days
            if days >= WAITING_AFTER_DAYS:
                waiting_rows.append({"id": a.pk, "company": a.company, "role": a.role, "days": days})
    waiting_rows.sort(key=lambda r: -r["days"])
    waited = [(today - a.applied_date).days for a in applied if a.applied_date and a.pk not in answered_ids and not a.status.is_terminal]

    skills = _skills(apps)
    waiting_out = {"count": len(waited), "median_days": int(median(waited)) if waited else None, "longest": waiting_rows[:5], "after_days": WAITING_AFTER_DAYS}
    return {
        "as_of": today.isoformat(),
        "has_jobs": bool(apps),
        "summary_text": summary_text(bool(apps), week, waiting_out, skills),
        "week": week,
        "weekly": weekly,
        "match": match,
        "applied": {"count": len(applied), "reply_rate": _pct(len(answered), len(applied))},
        "calibration": calibration(applied, answered_ids, percents, bands),
        "sources": sources,
        "work": [{"kind": k, "count": c} for k, c in work.most_common()],
        "countries": [{"name": n, "count": c} for n, c in countries.most_common(5)],
        "waiting": waiting_out,
        "skills": skills,
        "prep": _prep(user, config, today),
        "market": _market(user, profile),
    }
