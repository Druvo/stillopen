"""Fixtures of the optional AI helpers for the route inventory test (see `_world_modules` in tests_api.py).

These routes take no new path parameters (only `job_id`), so there is nothing to add; the bodies below get a request past validation."""

BODIES = {
    ("POST", "/api/v1/jobs/{job_id}/interview-prep/feedback"): {"question": "Why this role?", "answer": "Because I enjoy building reliable systems."},
    ("POST", "/api/v1/jobs/{job_id}/application-answer"): {"question": "Why do you want this role?"},
    ("POST", "/api/v1/jobs/{job_id}/message-draft"): {"kind": "follow_up"},
    ("POST", "/api/v1/profile/suggest"): {},
}


def world(owner, ids):
    return {}
