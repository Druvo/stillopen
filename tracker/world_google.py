"""Bodies for the route inventory (see `_world_modules` in tests_api.py): the Google routes that take a body. No fixtures: a connection is made by the tests that need one."""


def world(owner, ids):
    return {}


_MSG = {"to": "hr@example.org", "subject": "Application", "body": "Hello"}
BODIES = {
    ("POST", "/api/v1/jobs/{job_id}/google/preview"): _MSG,
    ("POST", "/api/v1/jobs/{job_id}/google/send"): {**_MSG, "digest": "x", "confirm": True},
    ("POST", "/api/v1/jobs/{job_id}/google/check"): {},
    ("POST", "/api/v1/jobs/{job_id}/google/draft"): {"message_id": 1},
    ("PATCH", "/api/v1/google/settings"): {"calendar_sync": False},
}
