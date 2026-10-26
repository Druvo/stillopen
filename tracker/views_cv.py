"""CV downloads and the print page. Everything else about CVs (history, tailoring, approve, restore) is in the JSON API."""
import re

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from .models import CVVersion
from .services import cvexport


def _version(request, pk) -> CVVersion:
    return get_object_or_404(CVVersion.objects.select_related("application", "parent"), pk=pk, owner=request.user)


def _filename(version: CVVersion, ext: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", version.label or f"cv-{version.pk}").strip("-")[:60] or "cv"
    return f"{base}-v{version.pk}.{ext}"


def _require_exportable(version: CVVersion) -> None:
    if not version.exportable:
        raise Http404("Review and approve the flagged items first.")


def _template(request) -> str:
    name = request.GET.get("template", cvexport.DEFAULT_TEMPLATE)
    return name if name in cvexport.TEMPLATES else cvexport.DEFAULT_TEMPLATE


@login_required
@require_GET
def cv_download(request, pk, fmt):
    version = _version(request, pk)
    _require_exportable(version)
    if fmt == "docx":
        response = HttpResponse(
            cvexport.to_docx(version.content, _template(request)),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response["Content-Disposition"] = f'attachment; filename="{_filename(version, "docx")}"'
    elif fmt == "md":
        response = HttpResponse(version.content, content_type="text/markdown; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{_filename(version, "md")}"'
    else:
        raise Http404()
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_GET
def cv_print(request, pk):
    version = _version(request, pk)
    _require_exportable(version)
    style = cvexport.TEMPLATES[_template(request)]
    return render(request, "tracker/cv_print.html", {"v": version, "body": cvexport.to_html(version.content), "style": style})
