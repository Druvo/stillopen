"""Fixtures of the match card and profile strength routes for the route inventory test (see `_world_modules` in tests_api.py).

Every route takes the job id the other worlds already made (`job_id`); the bodies below get a request past validation."""

BODIES = {
    ("POST", "/api/v1/jobs/{job_id}/match-card/fact"): {"text": "I have run Docker in production for three years."},
}


def world(owner, ids):
    return {}
