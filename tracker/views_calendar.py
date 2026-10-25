"""Calendar downloads for interviews (.ics). Plain files, not JSON, so they live next to the other downloads and not under /api/v1/."""
import re

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import Interview
from .services import ics


def _response(body: str, filename: str) -> HttpResponse:
    response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_GET
def interview_calendar(request, pk):
    """One interview of the signed-in person. Anyone else's is a 404."""
    item = get_object_or_404(Interview.objects.select_related("application"), pk=pk, owner=request.user)
    company = re.sub(r"[^A-Za-z0-9._-]+", "-", item.application.company).strip("-")[:40] or "interview"
    return _response(ics.calendar([item], name=ics.summary(item)), f"interview-{company}-{item.pk}.ics")


@login_required
@require_GET
def interviews_calendar(request):
    """Every interview of the signed-in person that has not happened yet and is still pending."""
    items = (
        Interview.objects.filter(owner=request.user, outcome="pending", scheduled_at__gte=timezone.now())
        .select_related("application").order_by("scheduled_at", "id")
    )
    return _response(ics.calendar(list(items)), "stillopen-interviews.ics")
