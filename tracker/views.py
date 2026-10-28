import mimetypes

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_http_methods

from .models import Application, Document, SiteConfig
from .services import dataexport
from .services.files import resolve_document_path

# Everything a signed-in person does lives in the app (/app/) and its JSON API (tracker/api). What stays here is the pages
# that are not part of the app: the email test for admins, privacy and terms, and the file and data downloads the app links to.


def mine(request):
    return Application.objects.filter(owner=request.user)


@staff_member_required
@require_http_methods(["GET", "POST"])
def email_test(request):
    """Send one test message to the signed-in admin through the email settings in use, and say plainly what happened."""
    from django.core.mail import send_mail

    from .services import integrations

    cfg = integrations.email_settings()
    result = None
    if request.method == "POST":
        if cfg is None:
            result = ("error", "Email is not set up yet. Fill in the Email tab in Site configuration first.")
        elif not request.user.email:
            result = ("error", "Your admin account has no email address. Add one to your profile first.")
        else:
            try:
                send_mail("StillOpen: test email", "If you can read this, StillOpen can send email.", cfg.from_email, [request.user.email], fail_silently=False)
                result = ("success", f"Sent to {request.user.email}. Check that inbox, and the spam folder.")
            except Exception as exc:  # noqa: BLE001 - the reason is the point of this page
                result = ("error", f"Sending failed: {exc.__class__.__name__}: {exc}")
    return render(request, "tracker/email_test.html", {"config": SiteConfig.load(), "cfg": cfg, "result": result})


@require_GET
def privacy(request):
    config = SiteConfig.load()
    return render(request, "tracker/legal.html", {"config": config, "title": "Privacy", "text": config.privacy_text})


@require_GET
def terms(request):
    config = SiteConfig.load()
    return render(request, "tracker/legal.html", {"config": config, "title": "Terms", "text": config.terms_text})


@login_required
@require_GET
def document_file(request, pk):
    doc = get_object_or_404(Document, pk=pk, application__owner=request.user)
    path = resolve_document_path(doc, SiteConfig.for_user(request.user))
    if path is None:
        raise Http404("File not available")
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if path.suffix.lower() == ".md":
        content_type = "text/plain; charset=utf-8"
    response = FileResponse(open(path, "rb"), content_type=content_type)
    response["Content-Disposition"] = f'inline; filename="{path.name}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


# --- your data ----------------------------------------------------------------------------------

@login_required
@require_GET
def export_data(request):
    """Everything this person has stored, as one JSON file. Secrets (API keys) are never included."""
    response = JsonResponse(dataexport.build(request.user), json_dumps_params={"indent": 2, "ensure_ascii": False})
    response["Content-Disposition"] = 'attachment; filename="stillopen-export.json"'
    return response
