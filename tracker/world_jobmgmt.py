"""Fixtures of the job-management API (remove, bulk, undo, history, import, reply reading) for the route inventory test (see `_world_modules` in tests_api.py).

Every route here takes the job id the other worlds already made (`job_id`), so no new rows or path parameters are needed; the routes with a body get one.
(No timeline line is made here: the inventory test asserts another person's job gains no events.)"""

BODIES = {
    ("POST", "/api/v1/jobs/{job_id}/reply-parse"): {"text": "Thank you for applying. We will be in touch."},
    ("POST", "/api/v1/jobs/bulk"): {"ids": [], "action": "remove"},
}


def world(owner, ids):
    return {}
