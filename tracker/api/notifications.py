"""The notification centre (the bell): a person's own short notices (see services/notifications.py). Owner-only, and a notice that is not
the person's answers 404."""
from ninja import Router, Schema

from ..models import Notification
from ..services import notifications
from .common import owned

router = Router()


class MutedIn(Schema):
    muted: list[str] = []


def _settings(user) -> dict:
    muted = notifications.muted_kinds(user)
    return {"kinds": [{"key": k, "label": label, "on": k not in muted} for k, label in notifications.KINDS.items()]}


@router.get("/notifications/summary", summary="How many notices are unread (small, polled by the bell)")
def summary(request):
    return notifications.summary(request.user)


@router.get("/notifications", summary="The person's notices, newest first")
def listing(request, limit: int = 100):
    return notifications.listing(request.user, limit)


@router.post("/notifications/read-all", summary="Mark every notice as read")
def read_all(request):
    notifications.mark_all_read(request.user)
    return notifications.summary(request.user)


@router.post("/notifications/clear", summary="Clear every notice")
def clear(request):
    notifications.clear_all(request.user)
    return notifications.summary(request.user)


@router.get("/notifications/settings", summary="Which kinds of notice the person gets")
def get_settings(request):
    return _settings(request.user)


@router.put("/notifications/settings", summary="Switch kinds of notice on or off (the list holds the kinds switched OFF)")
def put_settings(request, payload: MutedIn):
    notifications.set_muted(request.user, payload.muted)
    return _settings(request.user)


@router.post("/notifications/{notification_id}/read", summary="Mark one notice as read")
def read_one(request, notification_id: int):
    owned(Notification, request, notification_id, cleared=False)
    notifications.mark_read(request.user, notification_id)
    return notifications.summary(request.user)


@router.delete("/notifications/{notification_id}", summary="Clear one notice")
def clear_one(request, notification_id: int):
    owned(Notification, request, notification_id, cleared=False)
    notifications.clear_one(request.user, notification_id)
    return notifications.summary(request.user)
