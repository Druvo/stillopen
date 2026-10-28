"""The person's own numbers (see services/stats.py). Read-only, and only ever about the signed-in person."""
from ninja import Router
from ninja.errors import HttpError

from ..services import dashviz, stats, tz

router = Router()


@router.get("/stats", summary="Numbers about this person's own search")
def my_stats(request):
    return stats.candidate_stats(request.user)


@router.get("/stats/calendar", summary="One month of interviews, follow-ups, deadlines and offer dates, plus the week ahead")
def my_calendar(request, month: str = ""):
    zone = tz.zone_for(request.user)
    today = tz.today_for(request.user)
    try:
        first = dashviz.parse_month(month, today)
    except ValueError as exc:
        raise HttpError(400, str(exc))
    return dashviz.month_view(request.user, first, today, zone)
