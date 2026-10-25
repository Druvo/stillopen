"""The jobs spreadsheet download. A file, not JSON, so it lives beside the other downloads rather than under /api/v1/."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .services import jobexport


@login_required
@require_GET
@never_cache
def jobs_csv(request):
    """Every job of the signed-in person, as CSV. Another person's jobs are never in it (the query starts from the owner)."""
    response = HttpResponse(jobexport.to_csv(request.user), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="stillopen-jobs-{timezone.localdate():%Y-%m-%d}.csv"'
    response["Cache-Control"] = "no-store, private"
    response["X-Content-Type-Options"] = "nosniff"
    return response
