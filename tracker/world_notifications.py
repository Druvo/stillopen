"""Fixtures for the route inventory (see `_world_modules` in tests_api.py): one notice per person."""
from tracker.models import Notification


def world(owner, ids):
    note = Notification.objects.create(owner=owner, kind="search", title="Your search found 2 new jobs", link="/")
    return {"notification_id": note.pk}


BODIES = {
    ("PUT", "/api/v1/notifications/settings"): {"muted": ["search"]},
}
