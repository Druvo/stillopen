"""Fixtures of the import-from-email and careers-page routes for the route inventory test (see `_world_modules` in tests_api.py).

Neither route has a path parameter (so no ids are made here); the two POST routes get a body that passes validation."""

BODIES = {
    ("POST", "/api/v1/jobs/import-email"): {"text": "Backend Engineer\nAcme\nBerlin\nhttps://jobs.example.org/apply/1"},
    ("POST", "/api/v1/sources/careers-page"): {"url": "https://careers.example.com/jobs", "name": "Example"},
}


def world(owner, ids):
    return {}
