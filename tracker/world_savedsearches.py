"""Fixtures for the saved-searches route (see `_world_modules` in tests_api.py): one saved search per person."""
from .models import SavedSearch


def world(owner, ids):
    search = SavedSearch.objects.create(owner=owner, name=f"{owner.username}-search", target_roles="Backend Engineer")
    return {"search_id": search.pk}
