"""Fixtures of the parse-text, offer-comparison and referral-draft routes for the route inventory test (see `_world_modules` in tests_api.py).

These routes take no new path parameters beyond `contact_id` (made by world_pipeline), so there is nothing to add; the bodies below get a request
past validation. Someone else's contact is a 404 before the job in the body is looked at."""

BODIES = {
    ("POST", "/api/v1/jobs/parse-text"): {"text": "Platform Engineer at Gamma\n\nLocation: Remote\nApply by 30 November 2026."},
    ("POST", "/api/v1/offers/compare-note"): {"offer_ids": [1, 2]},
    ("POST", "/api/v1/contacts/{contact_id}/referral-draft"): {"job_id": 1},
}


def world(owner, ids):
    return {}
