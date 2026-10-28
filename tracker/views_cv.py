"""CV downloads and the print page. Everything else about CVs (history, tailoring, approve, restore) is in the JSON API."""
import io
import re
import zipfile

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST

from .models import Application, CVVersion
from .services import cvbuilder, cvexport
from .services.cvversions import CVError
from .services.throttle import throttled


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


PREVIEW_HEADERS = {
    # the preview is shown in a sandboxed frame (no scripts, no same-origin); the page also carries its own policy, this is the belt to that braces
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; sandbox",
    "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
}


def _preview_response(content: str, label: str, template: str):
    """The very page the print view produces for this look, minus the print bar, for a sandboxed frame."""
    style = cvexport.TEMPLATES[template]
    html = render_to_string("tracker/cv_print.html", {"v": {"label": label}, "body": cvexport.to_html(content), "style": style, "preview": True})
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    for key, value in PREVIEW_HEADERS.items():
        response[key] = value
    return response


def _message_page(text: str):
    from django.utils.html import escape

    response = HttpResponse(f'<!doctype html><meta charset="utf-8"><body style="font:15px system-ui;padding:24px;color:#333"><p>{escape(text)}</p></body>', content_type="text/html; charset=utf-8")
    for key, value in PREVIEW_HEADERS.items():
        response[key] = value
    return response


@login_required
@require_GET
@xframe_options_sameorigin
def cv_preview(request, pk):
    """A saved CV as it will print. Not a download: it shows the person text they already see in the editor, so a version waiting for approval can be previewed too."""
    version = _version(request, pk)
    return _preview_response(version.content, version.label, _template(request))


@login_required
@require_POST
@xframe_options_sameorigin
def builder_preview(request):
    """The builder's unsaved answers as they will print (a form post into the frame, so nothing personal is ever in an address). Saves nothing."""
    import json

    if throttled(request.user, "cvpreview", settings.STILLOPEN_CVPREVIEW_PER_HOUR):
        return _message_page("Too many previews this hour. Try again later.")
    try:
        answers = json.loads(request.POST.get("answers") or "{}")
        content = cvbuilder.to_markdown(cvbuilder.clean_answers(answers))
    except CVError as exc:
        return _message_page(f"The preview needs a little more first. {exc}")
    except ValueError:
        return _message_page("We could not read those answers. Reload the page and try again.")
    return _preview_response(content, "Preview", _template(request))


def _slug(text: str, fallback: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-")[:40] or fallback


@login_required
@require_GET
def job_documents_zip(request, pk):
    """The person's newest tailored CV and cover letter for one job as DOCX, plain text and Markdown. Same rule as each download: anything flagged and not approved refuses the whole zip."""
    from .api.cvimport import bundle_parts

    job = get_object_or_404(Application, pk=pk, owner=request.user)
    cv, letter = bundle_parts(request.user, job)
    if cv is None and letter is None:
        raise Http404("Make a CV or a cover letter for this job first.")
    for doc in (cv, letter):
        if doc is not None and not doc.exportable:
            raise Http404("Review and approve the flagged items first.")
    base = _slug(job.company, "job")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        if cv is not None:
            z.writestr(f"{base}-cv.docx", cvexport.to_docx(cv.content, _template(request)))
            z.writestr(f"{base}-cv.txt", cvexport.to_text(cv.content))
            z.writestr(f"{base}-cv.md", cv.content)
        if letter is not None:
            z.writestr(f"{base}-cover-letter.docx", cvexport.to_docx(letter.content))
            z.writestr(f"{base}-cover-letter.txt", letter.content)
            z.writestr(f"{base}-cover-letter.md", letter.content)
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{base}-application-documents.zip"'
    response["X-Content-Type-Options"] = "nosniff"
    return response
