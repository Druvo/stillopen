"""Fixtures for the route inventory (see `_world_modules` in tests_api.py): one search area, one own job board and one assistant token per person."""
from .models import ApiToken, JobSource, SearchArea

BODIES = {
    ("PATCH", "/profile/areas/{area_id}"): {"city": "Dhaka"},
}


def world(owner, ids):
    area = SearchArea.objects.create(owner=owner, place="Bangladesh", allow_remote=True)
    source = JobSource.objects.create(owner=owner, name=f"{owner.username}-board", connector="greenhouse", board_token=f"{owner.username}board")
    token, _ = ApiToken.issue(owner, "Laptop")
    return {"area_id": area.pk, "source_id": source.pk, "token_id": token.pk}
