"""Extra, named role lists searched alongside the profile's own target_roles (see services/scan.py's `_roles`).
Owner-scoped like everything else; a row's enabled flag, not deletion, is how a person turns one off and on."""
from typing import Any

from django.conf import settings
from ninja import Body, Router
from ninja.errors import HttpError

from ..forms import SavedSearchForm
from ..models import SavedSearch
from ..services import scan
from .common import owned, validate_form

router = Router()

Raw = Body[dict[str, Any]]


def _item(item: SavedSearch) -> dict:
    return {"id": item.pk, "name": item.name, "target_roles": item.target_roles, "enabled": item.enabled}


@router.get("/saved-searches", summary="This person's extra, named searches")
def list_saved_searches(request):
    return {"saved_searches": [_item(s) for s in SavedSearch.objects.filter(owner=request.user)]}


@router.post("/saved-searches", summary="Add a named search")
def create_saved_search(request, payload: Raw):
    if SavedSearch.objects.filter(owner=request.user).count() >= settings.STILLOPEN_MAX_SAVED_SEARCHES:
        raise HttpError(400, f"You have reached the limit of {settings.STILLOPEN_MAX_SAVED_SEARCHES} saved searches. Delete one first.")
    form = SavedSearchForm({"enabled": True, **payload}, owner=request.user)
    validate_form(form)
    item = scan.save_saved_search(form, request.user)
    return _item(item)


@router.patch("/saved-searches/{search_id}", summary="Change a named search")
def update_saved_search(request, search_id: int, payload: Raw):
    item = owned(SavedSearch, request, search_id)
    current = {"name": item.name, "target_roles": item.target_roles, "enabled": item.enabled}
    form = SavedSearchForm({**current, **payload}, owner=request.user, instance=item)
    validate_form(form)
    form.save()
    return _item(item)


@router.delete("/saved-searches/{search_id}", summary="Delete a named search")
def delete_saved_search(request, search_id: int):
    owned(SavedSearch, request, search_id).delete()
    return {"ok": True}
