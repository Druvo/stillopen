"""Cover letter downloads. Everything else about cover letters is in the JSON API."""
import re

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from .models import CoverLetter
from .services import cvexport


def _letter(request, pk) -> CoverLetter:
    return get_object_or_404(CoverLetter.objects.select_related("application"), pk=pk, owner=request.user)


def _filename(letter: CoverLetter, ext: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", f"cover-letter-{letter.application.company}").strip("-")[:60] or "cover-letter"
    return f"{base}-{letter.pk}.{ext}"


@login_required
@require_GET
def cover_download(request, pk, fmt):
    letter = _letter(request, pk)
    if not letter.exportable:
        raise Http404("Review and approve the flagged items first.")
    if fmt == "docx":
        response = HttpResponse(
            cvexport.to_docx(letter.content),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    elif fmt == "txt":
        response = HttpResponse(letter.content, content_type="text/plain; charset=utf-8")
    else:
        raise Http404()
    response["Content-Disposition"] = f'attachment; filename="{_filename(letter, fmt)}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response
