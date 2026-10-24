"""Cover letters: write for a job, edit, fact-check, approve, export."""
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import CoverLetter, SiteConfig
from .services import coverletter, cvexport
from .services.cvversions import CVError
from .views import owned_app, throttled


def _letter(request, pk) -> CoverLetter:
    return get_object_or_404(CoverLetter.objects.select_related("application"), pk=pk, owner=request.user)


def _filename(letter: CoverLetter, ext: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", f"cover-letter-{letter.application.company}").strip("-")[:60] or "cover-letter"
    return f"{base}-{letter.pk}.{ext}"


@login_required
@require_POST
def write_cover_letter(request, pk):
    app = owned_app(request, pk)
    if throttled(request.user, "cvgen", settings.STILLOPEN_CVGEN_PER_HOUR):
        messages.error(request, "Too many requests this hour. Try again later.")
        return redirect("apply_page", pk=app.pk)
    mode = request.POST.get("mode", "auto")
    try:
        letter = coverletter.generate(app, SiteConfig.for_user(request.user), mode if mode in ("auto", "ai", "keywords") else "auto")
    except CVError as exc:
        messages.error(request, str(exc))
        return redirect("apply_page", pk=app.pk)
    if letter.flagged:
        messages.error(request, f"Letter saved, but {len(letter.check_report)} claim(s) are not in your own material. Review them before using it.")
    else:
        messages.success(request, "Your cover letter is ready. Read it over and make it sound like you.")
    return redirect("cover_detail", pk=letter.pk)


@login_required
@require_http_methods(["GET", "POST"])
def cover_detail(request, pk):
    letter = _letter(request, pk)
    if request.method == "POST":
        try:
            coverletter.update(letter, request.POST.get("content", ""), SiteConfig.for_user(request.user))
        except CVError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Saved." if not letter.flagged else "Saved. Some claims are not in your own material, check them below.")
        return redirect("cover_detail", pk=letter.pk)
    return render(request, "tracker/cover_detail.html", {"config": SiteConfig.load(), "letter": letter})


@login_required
@require_POST
def cover_approve(request, pk):
    coverletter.approve(_letter(request, pk))
    messages.success(request, "Approved.")
    return redirect("cover_detail", pk=pk)


@login_required
@require_POST
def cover_delete(request, pk):
    letter = _letter(request, pk)
    app_pk = letter.application_id
    letter.delete()
    messages.success(request, "Deleted.")
    return redirect("apply_page", pk=app_pk)


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
