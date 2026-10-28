"""The stage after "Applied" for the new app: interviews, contacts and referrals, offers, and the insights numbers.

Same rules as `views_pipeline.py`: every row belongs to one person, a row that is not theirs is a 404, the forms are the classic
pages' own forms built with the owner (so a job or contact that is not theirs is refused), offers are compared per currency and
never converted, and nothing here contacts anyone."""
from typing import Any

from django.utils import timezone
from ninja import Body, Router, Schema
from ninja.errors import HttpError

from ..forms import ContactForm, InterviewForm, OfferForm, ReferralForm
from ..models import Application, Contact, Interview, Offer, Referral
from ..services import board, gcal, googleconnect, pipeline
from .common import owned, validate_form

router = Router()


# Whatever fields the form sends: the classic page's own form decides what is valid.
Raw = Body[dict[str, Any]]

LOCAL_FORMAT = "%Y-%m-%dT%H:%M"


def _job(app: Application) -> dict:
    return {"id": app.pk, "role": app.role, "company": app.company}


def _jobs(request) -> list[dict]:
    return [{"id": a.pk, "label": f"{a.company} - {a.role}"} for a in Application.objects.filter(owner=request.user).order_by("company", "role")]


def _choices(pairs) -> list[dict]:
    return [{"value": value, "label": label} for value, label in pairs]


def _check_room(request, model) -> None:
    if pipeline.at_limit(request.user, model):
        raise HttpError(400, pipeline.limit_message())


def _merged(current: dict, payload: dict) -> dict:
    """An edit keeps what it does not mention: the form sees the saved values with the sent ones on top."""
    return {**current, **{k: v for k, v in payload.items() if k in current}}


def _text(value) -> str:
    return "" if value is None else str(value)


# --- interviews -----------------------------------------------------------------------------------

def _interview(item: Interview, now) -> dict:
    return {
        "id": item.pk, "job": _job(item.application), "scheduled_at": item.scheduled_at.isoformat(),
        "scheduled_local": timezone.localtime(item.scheduled_at).strftime(LOCAL_FORMAT),
        "kind": item.kind, "kind_label": item.get_kind_display(), "where": item.where, "notes": item.notes,
        "outcome": item.outcome, "outcome_label": item.get_outcome_display(),
        "upcoming": item.outcome == "pending" and item.scheduled_at >= now,
    }


def _interview_current(item: Interview) -> dict:
    return {
        "application": item.application_id, "scheduled_at": timezone.localtime(item.scheduled_at).strftime(LOCAL_FORMAT),
        "kind": item.kind, "where": item.where, "notes": item.notes,
    }


def _google(request) -> dict:
    connection = googleconnect.for_user(request.user)
    return {"connected": connection is not None, "sync": bool(connection and connection.calendar_sync)}


@router.get("/interviews", summary="The person's interviews, coming up and past")
def list_interviews(request):
    mine = list(Interview.objects.filter(owner=request.user).select_related("application"))
    now = timezone.now()
    rows = [_interview(i, now) for i in mine]
    return {
        "upcoming": [r for r in rows if r["upcoming"]],
        "past": [r for r in reversed(rows) if not r["upcoming"]],
        "jobs": _jobs(request), "kinds": _choices(Interview.KINDS), "outcomes": _choices(Interview.OUTCOMES),
        "google": _google(request),
    }


@router.post("/interviews", summary="Add an interview")
def create_interview(request, payload: Raw):
    form = InterviewForm(payload, owner=request.user)
    validate_form(form)
    _check_room(request, Interview)
    item = pipeline.save_interview(form, request.user)
    return {"id": item.pk, "suggest_status": board.suggest_for(item.application, "Interview"), "calendar_note": gcal.push(item)}


@router.patch("/interviews/{interview_id}", summary="Change an interview")
def update_interview(request, interview_id: int, payload: Raw):
    item = owned(Interview.objects.select_related("application"), request, interview_id)
    form = InterviewForm(_merged(_interview_current(item), payload), owner=request.user, instance=item)
    validate_form(form)
    form.save()
    return {"id": item.pk, "suggest_status": board.suggest_for(item.application, "Interview"), "calendar_note": gcal.push(item)}


class OutcomeIn(Schema):
    outcome: str


@router.post("/interviews/{interview_id}/outcome", summary="Say how an interview went")
def interview_outcome(request, interview_id: int, payload: OutcomeIn):
    item = owned(Interview.objects.select_related("application"), request, interview_id)
    if not pipeline.set_interview_outcome(item, payload.outcome):
        raise HttpError(400, "Pick one of the outcomes in the list.")
    return {"ok": True, "outcome": item.outcome, "outcome_label": item.get_outcome_display(), "calendar_note": gcal.push(item)}


@router.delete("/interviews/{interview_id}", summary="Delete an interview")
def delete_interview(request, interview_id: int):
    item = owned(Interview.objects.select_related("application", "owner"), request, interview_id)
    note = gcal.remove(item)
    item.delete()
    return {"ok": True, "calendar_note": note}


# --- contacts and referrals -------------------------------------------------------------------------

def _referral(item: Referral) -> dict:
    return {
        "id": item.pk, "job": _job(item.application), "status": item.status, "status_label": item.get_status_display(), "note": item.note,
    }


def _contact(item: Contact) -> dict:
    return {
        "id": item.pk, "name": item.name, "company": item.company, "title": item.title, "email": item.email, "link": item.link,
        "notes": item.notes, "last_contacted": item.last_contacted.isoformat() if item.last_contacted else "",
        "referrals": [_referral(r) for r in item.referrals.all()],
    }


@router.get("/contacts", summary="The person's contacts, with the referrals each one may give")
def list_contacts(request):
    people = Contact.objects.filter(owner=request.user).prefetch_related("referrals__application")
    return {
        "contacts": [_contact(c) for c in people],
        "jobs": _jobs(request), "referral_statuses": _choices(Referral.STATUSES),
    }


@router.post("/contacts", summary="Add a contact")
def create_contact(request, payload: Raw):
    form = ContactForm(payload, owner=request.user)
    validate_form(form)
    _check_room(request, Contact)
    item = pipeline.save_contact(form, request.user)
    return {"id": item.pk}


@router.patch("/contacts/{contact_id}", summary="Change a contact")
def update_contact(request, contact_id: int, payload: Raw):
    item = owned(Contact, request, contact_id)
    current = {
        "name": item.name, "company": item.company, "title": item.title, "email": item.email, "link": item.link,
        "last_contacted": item.last_contacted.isoformat() if item.last_contacted else "", "notes": item.notes,
    }
    form = ContactForm(_merged(current, payload), owner=request.user, instance=item)
    validate_form(form)
    form.save()
    return {"id": item.pk}


@router.delete("/contacts/{contact_id}", summary="Delete a contact and its referrals")
def delete_contact(request, contact_id: int):
    owned(Contact, request, contact_id).delete()
    return {"ok": True}


@router.post("/referrals", summary="Note that a contact may refer the person for a job")
def create_referral(request, payload: Raw):
    form = ReferralForm(payload, owner=request.user)
    validate_form(form)
    _check_room(request, Referral)
    item = pipeline.save_referral(form, request.user)
    return {"id": item.pk}


class StatusIn(Schema):
    status: str


@router.post("/referrals/{referral_id}/status", summary="Say where a referral stands")
def referral_status(request, referral_id: int, payload: StatusIn):
    item = owned(Referral.objects.select_related("application", "contact"), request, referral_id)
    if not pipeline.set_referral_status(item, payload.status):
        raise HttpError(400, "Pick one of the statuses in the list.")
    return {"ok": True, "status": item.status, "status_label": item.get_status_display()}


@router.delete("/referrals/{referral_id}", summary="Delete a referral")
def delete_referral(request, referral_id: int):
    owned(Referral, request, referral_id).delete()
    return {"ok": True}


# --- offers -----------------------------------------------------------------------------------------

def _offer(item: Offer) -> dict:
    return {
        "id": item.pk, "job": _job(item.application), "base": str(item.base), "period": item.period, "period_label": item.get_period_display(),
        "currency": item.currency, "bonus": str(item.bonus), "equity": str(item.equity), "signing": str(item.signing),
        "other_benefits": str(item.other_benefits), "deadline": item.deadline.isoformat() if item.deadline else "",
        "status": item.status, "status_label": item.get_status_display(), "notes": item.notes,
        "yearly_base": str(item.yearly_base), "yearly_total": str(item.yearly_total), "first_year_total": str(item.first_year_total),
    }


@router.get("/offers", summary="The person's offers, side by side per currency")
def list_offers(request):
    mine = list(Offer.objects.filter(owner=request.user).select_related("application"))
    groups = [
        {
            "currency": g["currency"],
            "rows": [{"offer": _offer(r["offer"]), "behind": str(r["behind"]), "best": r["best"]} for r in g["rows"]],
        }
        for g in pipeline.comparison(mine)
    ]
    return {
        "offers": [_offer(o) for o in mine], "groups": groups,
        "jobs": _jobs(request), "periods": _choices(Offer.PERIODS), "statuses": _choices(Offer.STATUSES),
    }


OPTIONAL_MONEY = ("bonus", "equity", "other_benefits", "signing")


def _offer_data(data: dict) -> dict:
    """Extras left out or blank count as zero, like a person who simply has none of them."""
    out = {"period": "year", "currency": "USD", **data}
    for name in OPTIONAL_MONEY:
        if out.get(name) in (None, ""):
            out[name] = "0"
    return out


@router.post("/offers", summary="Record an offer")
def create_offer(request, payload: Raw):
    form = OfferForm(_offer_data(payload), owner=request.user)
    validate_form(form)
    _check_room(request, Offer)
    item = pipeline.save_offer(form, request.user)
    return {"id": item.pk, "suggest_status": board.suggest_for(item.application, "Offer")}


@router.patch("/offers/{offer_id}", summary="Change an offer")
def update_offer(request, offer_id: int, payload: Raw):
    item = owned(Offer.objects.select_related("application"), request, offer_id)
    current = {
        "application": item.application_id, "base": str(item.base), "period": item.period, "currency": item.currency,
        "bonus": str(item.bonus), "equity": str(item.equity), "other_benefits": str(item.other_benefits), "signing": str(item.signing),
        "deadline": item.deadline.isoformat() if item.deadline else "", "notes": _text(item.notes),
    }
    form = OfferForm(_offer_data(_merged(current, payload)), owner=request.user, instance=item)
    validate_form(form)
    form.save()
    return {"id": item.pk, "suggest_status": board.suggest_for(item.application, "Offer")}


@router.post("/offers/{offer_id}/status", summary="Say whether an offer is open, accepted or declined")
def offer_status(request, offer_id: int, payload: StatusIn):
    item = owned(Offer.objects.select_related("application"), request, offer_id)
    if not pipeline.set_offer_status(item, payload.status):
        raise HttpError(400, "Pick one of the statuses in the list.")
    return {"ok": True, "status": item.status, "status_label": item.get_status_display()}


@router.delete("/offers/{offer_id}", summary="Delete an offer")
def delete_offer(request, offer_id: int):
    owned(Offer, request, offer_id).delete()
    return {"ok": True}


# --- insights ---------------------------------------------------------------------------------------

@router.get("/insights", summary="How far the person's applications get")
def insights(request):
    return pipeline.funnel(request.user)
