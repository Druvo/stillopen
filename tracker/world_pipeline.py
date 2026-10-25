"""Fixtures for the route inventory (see `_world_modules` in tests_api.py): one interview, contact, referral and offer per person."""
from datetime import timedelta

from django.utils import timezone

from tracker.models import Application, Contact, Interview, Offer, Referral


def world(owner, ids):
    app = Application.objects.get(pk=ids["job_id"])
    interview = Interview.objects.create(owner=owner, application=app, scheduled_at=timezone.now() + timedelta(days=3), kind="video")
    contact = Contact.objects.create(owner=owner, name=f"{owner.username} friend", company="Acme")
    referral = Referral.objects.create(owner=owner, contact=contact, application=app)
    offer = Offer.objects.create(owner=owner, application=app, base=100000, currency="USD")
    return {"interview_id": interview.pk, "contact_id": contact.pk, "referral_id": referral.pk, "offer_id": offer.pk}


BODIES = {
    ("POST", "/api/v1/interviews/{interview_id}/outcome"): {"outcome": "done"},
    ("POST", "/api/v1/referrals/{referral_id}/status"): {"status": "asked"},
    ("POST", "/api/v1/offers/{offer_id}/status"): {"status": "accepted"},
    ("PATCH", "/api/v1/interviews/{interview_id}"): {"notes": "changed"},
    ("PATCH", "/api/v1/contacts/{contact_id}"): {"notes": "changed"},
    ("PATCH", "/api/v1/offers/{offer_id}"): {"notes": "changed"},
}
