"""CV versions: history, tailoring for a job, edit, compare, approve, restore, export."""
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import RestrictedError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import CVVersion, SiteConfig
from .services import cvexport, cvgen, cvversions
from .services.cvversions import CVError
from .views import owned_app, throttled


def _version(request, pk) -> CVVersion:
    return get_object_or_404(CVVersion.objects.select_related("application", "parent"), pk=pk, owner=request.user)


def _filename(version: CVVersion, ext: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", version.label or f"cv-{version.pk}").strip("-")[:60] or "cv"
    return f"{base}-v{version.pk}.{ext}"


@login_required
@require_GET
def cv_list(request):
    config = SiteConfig.for_user(request.user)
    try:
        cvversions.ensure_master(request.user, config)  # first visit: the profile CV becomes version 1
    except CVError:
        pass
    versions = CVVersion.objects.filter(owner=request.user).select_related("application")
    return render(request, "tracker/cv_list.html", {
        "config": SiteConfig.load(),
        "masters": [v for v in versions if v.kind == "master"],
        "tailored": [v for v in versions if v.kind == "tailored"],
    })


@login_required
@require_http_methods(["GET", "POST"])
def cv_detail(request, pk):
    version = _version(request, pk)
    if request.method == "POST":
        try:
            created = cvversions.new_version_from_edit(
                version, request.POST.get("content", ""), SiteConfig.for_user(request.user), request.POST.get("label", "").strip()[:140]
            )
        except CVError as exc:
            messages.error(request, str(exc))
            return redirect("cv_detail", pk=version.pk)
        messages.success(request, "Saved as a new version." if created.pk != version.pk else "No changes to save.")
        return redirect("cv_detail", pk=created.pk)
    return render(request, "tracker/cv_detail.html", {
        "config": SiteConfig.load(), "v": version, "preview": cvexport.to_html(version.content),
        "children": version.children.filter(owner=request.user).count(),
    })


@login_required
@require_GET
def cv_diff(request, pk):
    version = _version(request, pk)
    other_id = request.GET.get("against")
    if other_id:
        other = get_object_or_404(CVVersion, pk=other_id, owner=request.user)
    else:
        other = version.parent or cvversions.latest_master(request.user)
    if other is None or other.pk == version.pk:
        messages.info(request, "There is nothing to compare this version with yet.")
        return redirect("cv_detail", pk=version.pk)
    return render(request, "tracker/cv_diff.html", {
        "config": SiteConfig.load(), "v": version, "other": other, "rows": cvexport.line_diff(other.content, version.content),
        "choices": CVVersion.objects.filter(owner=request.user).exclude(pk=version.pk)[:50],
    })


@login_required
@require_POST
def cv_approve(request, pk):
    version = _version(request, pk)
    cvversions.approve(version)
    messages.success(request, "Approved. You can now download or print this version.")
    return redirect("cv_detail", pk=version.pk)


@login_required
@require_POST
def cv_restore(request, pk):
    version = _version(request, pk)
    try:
        created = cvversions.restore(version)
    except CVError as exc:
        messages.error(request, str(exc))
        return redirect("cv_detail", pk=version.pk)
    messages.success(request, "Restored as your current CV. The history is kept.")
    return redirect("cv_detail", pk=created.pk)


@login_required
@require_POST
def cv_delete(request, pk):
    version = _version(request, pk)
    if version.kind != "tailored":
        messages.error(request, "Master CV versions are your history and cannot be deleted. Delete your account to remove everything.")
        return redirect("cv_detail", pk=version.pk)
    try:
        version.delete()
    except RestrictedError:
        messages.error(request, "This CV is recorded as sent with an application, so it is kept as your record.")
        return redirect("cv_detail", pk=version.pk)
    messages.success(request, "Deleted.")
    return redirect("cv_list")


def _require_exportable(version: CVVersion) -> None:
    if not version.exportable:
        raise Http404("Review and approve the flagged items first.")


@login_required
@require_GET
def cv_download(request, pk, fmt):
    version = _version(request, pk)
    _require_exportable(version)
    if fmt == "docx":
        response = HttpResponse(
            cvexport.to_docx(version.content),
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
    return render(request, "tracker/cv_print.html", {"v": version, "body": cvexport.to_html(version.content)})


@login_required
@require_POST
def tailor_cv(request, pk):
    app = owned_app(request, pk)
    if throttled(request.user, "cvgen", settings.STILLOPEN_CVGEN_PER_HOUR):
        messages.error(request, "Too many CV requests this hour. Try again later.")
        return redirect("dashboard")
    mode = request.POST.get("mode", "auto")
    try:
        version = cvgen.tailor(app, SiteConfig.for_user(request.user), mode if mode in ("auto", "ai", "keywords") else "auto")
    except CVError as exc:
        messages.error(request, str(exc))
        return redirect("dashboard")
    if version.flagged:
        messages.error(request, f"Tailored CV saved, but {len(version.check_report)} claim(s) are not in your own material. Review them before using it.")
    else:
        messages.success(request, "Tailored CV saved. Nothing in it goes beyond your own material.")
    return redirect("cv_detail", pk=version.pk)
