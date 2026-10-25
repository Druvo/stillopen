"""Saved layout preferences (see services/preferences.py). Each person reads and writes only their own."""
from ninja import Body, Router

from ..models import UserProfile
from ..services import preferences
from .common import ApiFormError

router = Router()


@router.get("/preferences", summary="How this person likes the app laid out")
def get_preferences(request):
    return preferences.read(UserProfile.for_user(request.user))


@router.put("/preferences", summary="Save some of those choices (send only what changed)")
def put_preferences(request, payload: dict = Body(...)):
    try:
        return preferences.update(UserProfile.for_user(request.user), payload)
    except preferences.PreferenceError as exc:
        raise ApiFormError(exc.fields)
