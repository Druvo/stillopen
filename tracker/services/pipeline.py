"""Interview reminder emails and the funnel numbers behind the Insights page. Nothing here changes a job."""
from datetime import timedelta
from statistics import median

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from tracker.models import Application, Interview, ScoreBand, SiteConfig
from tracker.services import integrations
from tracker.services.cards import band_for

REMINDER_HOURS = 24


def due_interview_reminders(owner, now=None, hours: int = REMINDER_HOURS):
    """Pending interviews starting within `hours` that this person has not been reminded about yet."""
    now = now or timezone.now()
    return list(
        Interview.objects.filter(
            owner=owner, outcome="pending", reminded_at__isnull=True,
            scheduled_at__gte=now, scheduled_at__lte=now + timedelta(hours=hours),
        ).select_related("application").order_by("scheduled_at")
    )


def reminder_text(items) -> str:
    lines = ["Interviews coming up on your StillOpen tracker:", ""]
    for i in items:
        when = timezone.localtime(i.scheduled_at)
        lines.append(f"- {when:%a %d %b, %H:%M}: {i.get_kind_display()} for {i.application.company} - {i.application.role}")
        if i.where:
            lines.append(f"  Where: {i.where}")
        if i.notes:
            lines.append(f"  Your notes: {i.notes[:300]}")
    lines += ["", "Good luck. Mark how it went on your Interviews page afterwards."]
    return "\n".join(lines)


def send_interview_reminders(owner, items) -> bool:
    """One email per person per run. Needs a verified address; nothing is marked as sent otherwise."""
    from allauth.account.models import EmailAddress

    if not items:
        return False
    if not EmailAddress.objects.filter(user=owner, email=owner.email, verified=True).exists():
        return False
    send_mail(
        subject=f"StillOpen: {len(items)} interview{'s' if len(items) != 1 else ''} in the next day",
        message=reminder_text(items),
        from_email=integrations.from_email(),
        recipient_list=[owner.email],
        fail_silently=False,
    )
    Interview.objects.filter(pk__in=[i.pk for i in items]).update(reminded_at=timezone.now())
    return True


def _days(start, end):
    return max(0, (end - start).days)


def _pct(part, whole):
    return round(100 * part / whole) if whole else None


def by_score(owner, applied) -> list[dict]:
    """Outcome calibration: does a higher match score actually turn into more interviews and offers?

    Groups applied jobs by the match-percent band shown on their card at the time of viewing (not frozen
    at apply time -- a re-evaluated job moves band). One row per band that has at least one applied job,
    plus a "Not scored" row for jobs applied to without ever being evaluated, sorted highest band first.
    Small rows say little; the page itself carries that caveat, this just supplies the counts."""
    config = SiteConfig.for_user(owner)
    bands = list(ScoreBand.objects.all())
    groups: dict[int, dict] = {}
    for a in applied:
        band = band_for(a.match_percent(config.score_scale), bands)
        key = band.pk if band else -1
        row = groups.setdefault(key, {"label": band.label if band else "Not scored", "min_percent": band.min_percent if band else -1, "applied": 0, "interviews": 0, "offers": 0})
        row["applied"] += 1
        row["interviews"] += 1 if a.interviews.all() else 0
        row["offers"] += 1 if a.offers.all() else 0
    return [
        {
            "label": row["label"], "applied": row["applied"], "interviews": row["interviews"], "offers": row["offers"],
            "interview_rate": _pct(row["interviews"], row["applied"]), "offer_rate": _pct(row["offers"], row["applied"]),
        }
        for row in sorted(groups.values(), key=lambda r: -r["min_percent"])
    ]


def monthly_trend(applied, interviewed_ids: set, offered_ids: set) -> list[dict]:
    """How the funnel has moved over time: applied jobs grouped by the month you applied, each with its own
    interview/offer rate. Lets a person see whether a changed approach (a new CV, a new channel) is actually
    working, not just a single cumulative percentage. Months with nothing applied are left out rather than
    padded with zeroes; the oldest 12 months with data are kept so a long history doesn't dwarf recent months."""
    months: dict[str, dict] = {}
    for a in applied:
        if not a.applied_date:
            continue
        key = a.applied_date.strftime("%Y-%m")
        row = months.setdefault(key, {"month": key, "applied": 0, "interviews": 0, "offers": 0})
        row["applied"] += 1
        row["interviews"] += 1 if a.pk in interviewed_ids else 0
        row["offers"] += 1 if a.pk in offered_ids else 0
    rows = [months[key] for key in sorted(months)][-12:]
    for row in rows:
        row["interview_rate"] = _pct(row["interviews"], row["applied"])
        row["offer_rate"] = _pct(row["offers"], row["applied"])
    return rows


def funnel(owner) -> dict:
    """Plain counts for one person: how far their applications get, and what seems to work. Never a prediction."""
    apps = list(
        Application.objects.filter(owner=owner).select_related("status")
        .prefetch_related("interviews", "offers")
    )
    applied = [a for a in apps if a.applied_date or a.status.counts_as_applied]
    interviewed = [a for a in applied if a.interviews.all()]
    offered = [a for a in applied if a.offers.all()]
    first_interview_days = []
    for a in interviewed:
        if a.applied_date:
            first = min(timezone.localtime(i.scheduled_at).date() for i in a.interviews.all())
            first_interview_days.append(_days(a.applied_date, first))
    first_offer_days = []
    for a in offered:
        if a.applied_date:
            first = min(timezone.localtime(o.created_at).date() for o in a.offers.all())
            first_offer_days.append(_days(a.applied_date, first))

    pct = _pct
    channels = {}
    for a in applied:
        label = dict(Application.CHANNELS).get(a.applied_channel) or "Not recorded"
        row = channels.setdefault(label, {"label": label, "applied": 0, "interviews": 0, "offers": 0})
        row["applied"] += 1
        row["interviews"] += 1 if a.interviews.all() else 0
        row["offers"] += 1 if a.offers.all() else 0
    return {
        "by_score": by_score(owner, applied),
        "monthly_trend": monthly_trend(applied, {a.pk for a in interviewed}, {a.pk for a in offered}),
        "tracked": len(apps),
        "applied": len(applied),
        "interviewed": len(interviewed),
        "offered": len(offered),
        "interview_rate": pct(len(interviewed), len(applied)),
        "offer_rate": pct(len(offered), len(applied)),
        "median_days_to_interview": int(median(first_interview_days)) if first_interview_days else None,
        "median_days_to_offer": int(median(first_offer_days)) if first_offer_days else None,
        "channels": sorted(channels.values(), key=lambda r: -r["applied"]),
        "referred_applied": sum(1 for a in applied if a.referrals.exists()),
        "referred_interviewed": sum(1 for a in interviewed if a.referrals.exists()),
    }


# --- interviews, contacts, referrals, offers: the rules shared by the classic pages and the new app ------

def at_limit(owner, model) -> bool:
    """True when this person already keeps as many rows of `model` as the admin allows."""
    return model.objects.filter(owner=owner).count() >= settings.STILLOPEN_MAX_PIPELINE


def limit_message() -> str:
    return f"You have reached the limit of {settings.STILLOPEN_MAX_PIPELINE} saved items here. Delete some first."


def _note(application, kind: str, text: str) -> None:
    from tracker.models import Event

    Event.objects.create(application=application, kind=kind, text=text)


def save_interview(form, owner):
    """Save a valid InterviewForm as a new interview and note it on the job."""
    item = form.save(commit=False)
    item.owner = owner
    item.save()
    _note(item.application, "interview", f"{item.get_kind_display()} scheduled for {timezone.localtime(item.scheduled_at):%d %b %Y %H:%M}")
    return item


def set_interview_outcome(item, outcome: str) -> bool:
    """False (nothing changed) when `outcome` is not one of the known outcomes."""
    if outcome not in dict(Interview.OUTCOMES):
        return False
    item.outcome = outcome
    item.save(update_fields=["outcome"])
    _note(item.application, "interview", f"{item.get_kind_display()}: {item.get_outcome_display()}")
    return True


def save_contact(form, owner):
    item = form.save(commit=False)
    item.owner = owner
    item.save()
    return item


def save_referral(form, owner):
    item = form.save(commit=False)
    item.owner = owner
    item.save()
    _note(item.application, "note", f"Referral with {item.contact.name}: {item.get_status_display()}")
    return item


def set_referral_status(item, status: str) -> bool:
    from tracker.models import Referral

    if status not in dict(Referral.STATUSES):
        return False
    item.status = status
    item.save(update_fields=["status"])
    _note(item.application, "note", f"Referral with {item.contact.name}: {item.get_status_display()}")
    return True


def save_offer(form, owner):
    item = form.save(commit=False)
    item.owner = owner
    item.save()
    _note(item.application, "note", "Offer recorded")
    return item


def set_offer_status(item, status: str) -> bool:
    from tracker.models import Offer

    if status not in dict(Offer.STATUSES):
        return False
    item.status = status
    item.save(update_fields=["status"])
    _note(item.application, "note", f"Offer: {item.get_status_display()}")
    return True


def comparison(offers):
    """Offers grouped by currency (no exchange rates are guessed), best yearly total first, with the gap to the best. Declined offers are left out."""
    from collections import defaultdict
    from decimal import Decimal

    groups = defaultdict(list)
    for offer in offers:
        if offer.status != "declined":
            groups[offer.currency].append(offer)
    out = []
    for currency in sorted(groups):
        rows = sorted(groups[currency], key=lambda o: o.yearly_total, reverse=True)
        best = rows[0].yearly_total
        out.append({
            "currency": currency,
            "rows": [{"offer": o, "behind": best - o.yearly_total if best > o.yearly_total else Decimal(0), "best": o is rows[0] and len(rows) > 1} for o in rows],
        })
    return out


def upcoming_interviews(user, limit: int = 5):
    return list(
        Interview.objects.filter(owner=user, outcome="pending", scheduled_at__gte=timezone.now())
        .select_related("application").order_by("scheduled_at")[:limit]
    )
