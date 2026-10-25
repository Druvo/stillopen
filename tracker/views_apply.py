"""Apply assistant pages. Nothing here submits an application: the person applies on the employer's site themselves."""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .models import Application, CVVersion, SiteConfig
from .services import apply as apply_service
from .services import fit as fit_service
from .services.apply import ApplyError
from .views import owned_app
from .views_app import new_app_redirect


@login_required
@require_GET
def apply_page(request, pk):
    app = owned_app(request, pk)
    if go := new_app_redirect(request, f"/jobs/{app.pk}/apply"):
        return go
    config = SiteConfig.for_user(request.user)
    versions = apply_service.sendable_versions(app)
    return render(request, "tracker/apply.html", {
        "config": SiteConfig.load(),
        "app": app,
        "versions": versions,
        "selected": versions[0].pk if versions else None,
        "checks": apply_service.checklist(app, config, versions) + fit_service.fit_flags(app),
        "draft": apply_service.email_draft(app),
        "channels": [(v, label) for v, label in Application.CHANNELS if v],
        "followup_days": config.apply_followup_days,
        "has_flagged": CVVersion.objects.filter(owner=request.user, application=app).exists() and not any(v.kind == "tailored" for v in versions),
    })


@login_required
@require_POST
def mark_applied(request, pk):
    app = owned_app(request, pk)
    config = SiteConfig.for_user(request.user)
    back = redirect("apply_page", pk=app.pk)
    if app.live_state == "expired" and not request.POST.get("confirm_closed"):
        messages.error(request, "This posting looks closed. Tick the box to confirm you applied anyway.")
        return back
    chosen = request.POST.get("cv", "")
    version = None
    if chosen and chosen != "none":
        version = get_object_or_404(CVVersion, pk=chosen, owner=request.user)
    try:
        days = int(request.POST.get("days") or config.apply_followup_days)
        applied_on = date.fromisoformat(request.POST["applied_on"]) if request.POST.get("applied_on") else None
    except ValueError:
        messages.error(request, "Check the date and the number of days.")
        return back
    try:
        apply_service.record(app, version, request.POST.get("channel", ""), request.POST.get("note", ""), days, config, applied_on)
    except ApplyError as exc:
        messages.error(request, str(exc))
        return back
    messages.success(request, f"Good luck! We have noted it, and will remind you to follow up on {app.follow_up_date:%d %b %Y}.")
    return redirect("dashboard")


@login_required
@require_POST
def followup_action(request, pk, action):
    app = owned_app(request, pk)
    if action == "done":
        apply_service.followup_done(app)
        messages.success(request, "Marked done.")
    elif action == "snooze":
        try:
            days = int(request.POST.get("days") or 3)
        except ValueError:
            days = 3
        apply_service.followup_snooze(app, days)
        messages.success(request, f"Reminder moved to {app.follow_up_date:%d %b %Y}.")
    else:
        raise Http404()
    return redirect("dashboard")
