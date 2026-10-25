"""The person's own numbers (see services/stats.py). Read-only, and only ever about the signed-in person."""
from ninja import Router

from ..services import stats

router = Router()


@router.get("/stats", summary="Numbers about this person's own search")
def my_stats(request):
    return stats.candidate_stats(request.user)
