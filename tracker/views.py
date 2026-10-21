import functools
import mimetypes

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import forms
from .models import (
    Application, Bucket, Document, Event, KnowledgeSource, ScoreBand, SiteConfig, Status, UserProfile,
)
from .services import ai, careerops, knowledge, liveness
from .services.files import resolve_document_path
from .services.paperless import PaperlessClient, PaperlessError, push_document


# --- helpers ------------------------------------------------------------------------------------

def staff_required(view):
    """Server-level features (career-ops folder, Paperless) are for site admins only."""

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            if request.path.startswith("/api/"):
                return JsonResponse({"ok": False, "error": "Only site admins can do that."}, status=403)
            return HttpResponseForbidden("Only site admins can do that.")
        return view(request, *args, **kwargs)

    return wrapper


def throttled(user, action: str, limit: int, window: int = 3600) -> bool:
    """True when `user` has already done `action` `limit` times within `window` seconds (per server process)."""
    key = f"throttle:{action}:{user.pk}"
    cache.add(key, 0, timeout=window)
    try:
        return cache.incr(key) > limit
    except ValueError:
        cache.set(key, 1, timeout=window)
        return False


def too_many():
    return JsonResponse({"ok": False, "error": "Too many requests. Try again later."}, status=429)


def mine(request):
    return Application.objects.filter(owner=request.user)


def owned_app(request, pk):
    return get_object_or_404(Application, pk=pk, owner=request.user)


# --- public pages -------------------------------------------------------------------------------

@require_GET
def landing(request):
    config = SiteConfig.load()
    if not config.landing_enabled:
        return redirect("dashboard")
    return render(request, "tracker/landing.html", {"config": config})


@require_GET
def privacy(request):
    config = SiteConfig.load()
    return render(request, "tracker/legal.html", {"config": config, "title": "Privacy", "text": config.privacy_text})


@require_GET
def terms(request):
    config = SiteConfig.load()
    return render(request, "tracker/legal.html", {"config": config, "title": "Terms", "text": config.terms_text})


# --- dashboard ----------------------------------------------------------------------------------

def band_for(percent, bands):
    if percent is None:
        return None
    for band in bands:  # ordered highest threshold first
        if percent >= band.min_percent:
            return band
    return None


def card_for(app, config, bands):
    percent = app.match_percent(config.score_scale)
    band = band_for(percent, bands)
    days = app.days_left()
    return {
        "app": app,
        "percent": percent,
        "band": band,
        "days_left": days,
        "urgent": days is not None and 0 <= days <= config.urgent_days,
        "overdue": days is not None and days < 0,
        "strengths": [i for i in app.insights.all() if i.kind == "strength"],
        "gaps": [i for i in app.insights.all() if i.kind == "gap"],
        "documents": list(app.documents.all()),
    }


@login_required
@require_GET
def dashboard(request):
    config = SiteConfig.for_user(request.user)
    profile = UserProfile.for_user(request.user)
    bands = list(ScoreBand.objects.all())
    buckets = list(Bucket.objects.all())
    statuses = list(Status.objects.all())
    apps = mine(request).select_related("status", "status__bucket", "source").prefetch_related("insights", "documents__kind")

    tabs = {b.pk: [] for b in buckets}
    for app in apps:
        bucket = app.effective_bucket(config)
        tabs.setdefault(bucket.pk, []).append(card_for(app, config, bands))

    def sort_key(card):
        urgent_first = 0 if card["urgent"] else 1
        return (urgent_first, -(card["percent"] if card["percent"] is not None else -1))

    tab_list = [{"bucket": b, "cards": sorted(tabs.get(b.pk, []), key=sort_key)} for b in buckets]
    submitted = [c for t in tab_list for c in t["cards"] if c["app"].status.counts_as_applied]
    scored = [c["percent"] for t in tab_list for c in t["cards"] if c["percent"] is not None]
    paperless_on = request.user.is_staff and config.paperless_enabled and bool(config.effective_paperless_url)
    context = {
        "config": config,
        "profile": profile,
        "tabs": tab_list,
        "statuses": statuses,
        "stats": {
            "total": apps.count(),
            "submitted": len(submitted),
            "average_match": round(sum(scored) / len(scored)) if scored else None,
            "urgent": sum(1 for t in tab_list for c in t["cards"] if c["urgent"]),
        },
        "paperless_on": paperless_on,
        "paperless_url": config.effective_paperless_url if paperless_on else "",
        "can_import": request.user.is_staff and bool(config.careerops_path),
        "run": liveness.current_run(request.user),
        "checked_at": apps.exclude(live_checked_at=None).order_by("-live_checked_at").values_list("live_checked_at", flat=True).first(),
    }
    return render(request, "tracker/dashboard.html", context)


@login_required
@require_POST
def set_status(request, pk):
    app = owned_app(request, pk)
    status = get_object_or_404(Status, pk=request.POST.get("status"))
    if app.status_id != status.pk:
        app.status = status
        if status.counts_as_applied and not app.applied_date:
            app.applied_date = timezone.localdate()
        app.save()
        Event.objects.create(
            application=app,
            kind="applied" if status.counts_as_applied else "status",
            text=f"Status set to {status.name}",
        )
    return JsonResponse({"ok": True, "status": status.name})


@login_required
@require_POST
def evaluate(request, pk):
    app = owned_app(request, pk)
    if throttled(request.user, "evaluate", settings.STILLOPEN_EVALS_PER_HOUR):
        return too_many()
    config = SiteConfig.for_user(request.user)
    try:
        result = ai.evaluate_application(app, config)
    except ai.AIError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    return JsonResponse({"ok": True, "match_percent": result["match_percent"], "method": app.ai_method})


@login_required
@require_POST
def liveness_start(request):
    if throttled(request.user, "liveness", settings.STILLOPEN_CHECKS_PER_HOUR):
        return too_many()
    run = liveness.start_run(request.user)
    return JsonResponse({"running": run.running, "done": run.done, "total": run.total})


@login_required
@require_GET
def liveness_status(request):
    run = liveness.current_run(request.user)
    if run is None:
        return JsonResponse({"running": False, "done": 0, "total": 0, "error": ""})
    return JsonResponse({"running": run.running, "done": run.done, "total": run.total, "error": run.error})


@login_required
@staff_required
@require_POST
def import_tracker(request):
    config = SiteConfig.for_user(request.user)
    try:
        counts = careerops.import_all(config, request.user)
    except careerops.ImportErrorMessage as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    return JsonResponse({"ok": True, **counts})


@login_required
@staff_required
@require_POST
def push_to_paperless(request, pk):
    doc = get_object_or_404(Document.objects.select_related("application", "kind"), pk=pk, application__owner=request.user)
    config = SiteConfig.for_user(request.user)
    try:
        client = PaperlessClient.from_config(config)
    except PaperlessError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    doc_id = push_document(doc, client, config)
    doc.refresh_from_db()
    return JsonResponse(
        {
            "ok": bool(doc_id),
            "paperless_id": doc.paperless_id,
            "error": doc.paperless_error,
            "url": client.document_url(doc.paperless_id) if doc.paperless_id else "",
        }
    )


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


# --- adding jobs, profile, knowledge -------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def add_job(request):
    form = forms.JobForm(request.POST or None)
    if request.method == "POST" and mine(request).count() >= settings.STILLOPEN_MAX_APPLICATIONS:
        form.add_error(None, f"You have reached the limit of {settings.STILLOPEN_MAX_APPLICATIONS} tracked jobs. Delete some first.")
    elif request.method == "POST" and form.is_valid():
        app = form.save(commit=False)
        app.owner = request.user
        app.status = Status.objects.filter(bucket__is_closed=False).order_by("order").first() or Status.objects.first()
        app.save()
        Event.objects.create(application=app, kind="note", text="Added")
        messages.success(request, f"Added {app.company} - {app.role}.")
        return redirect("dashboard")
    return render(request, "tracker/add_job.html", {"form": form, "config": SiteConfig.load()})


@login_required
@require_http_methods(["GET", "POST"])
def profile(request):
    obj = UserProfile.for_user(request.user)
    form = forms.ProfileForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        knowledge.sync_cv(SiteConfig.for_user(request.user), request.user)
        messages.success(request, "Profile saved.")
        return redirect("profile")
    return render(request, "tracker/profile.html", {
        "form": form, "profile": obj, "config": SiteConfig.load(), "welcome": request.GET.get("welcome"),
        "sources": KnowledgeSource.objects.filter(owner=request.user).exclude(key__in=["profile-cv", "careerops:cv.md"]).count(),
    })


@login_required
@require_http_methods(["GET", "POST"])
def profile_ai(request):
    obj = UserProfile.for_user(request.user)
    form = forms.AISettingsForm(request.POST or None, instance=obj, restricted=not request.user.is_staff)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "AI settings saved.")
        return redirect("profile_ai")
    return render(request, "tracker/profile_ai.html", {
        "form": form, "config": SiteConfig.load(), "has_key": bool(obj.ai_key_encrypted),
        "has_rag_key": bool(obj.rag_embedding_key_encrypted),
    })


@login_required
@require_http_methods(["GET", "POST"])
def knowledge_list(request):
    owned = KnowledgeSource.objects.filter(owner=request.user)
    visible = owned.exclude(key__in=["profile-cv", "careerops:cv.md"]).prefetch_related("chunks")
    form = forms.KnowledgeForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and owned.count() >= settings.STILLOPEN_MAX_KNOWLEDGE:
        form.add_error(None, f"You have reached the limit of {settings.STILLOPEN_MAX_KNOWLEDGE} documents.")
    elif request.method == "POST" and form.is_valid():
        source = form.save(commit=False)
        source.owner = request.user
        source.file = ""  # only the extracted text is kept, never the uploaded file
        source.save()
        knowledge.reindex_source(source, SiteConfig.for_user(request.user))
        messages.success(request, f"Added {source.title}.")
        return redirect("knowledge")
    return render(request, "tracker/knowledge.html", {"form": form, "sources": visible, "config": SiteConfig.load()})


@login_required
@require_POST
def knowledge_action(request, pk, action):
    source = get_object_or_404(KnowledgeSource, pk=pk, owner=request.user)
    if action == "delete":
        source.delete()
        messages.success(request, "Deleted.")
    elif action == "toggle":
        source.enabled = not source.enabled
        source.save()
        knowledge.reindex_source(source, SiteConfig.for_user(request.user))
    else:
        raise Http404()
    return redirect("knowledge")


# --- your data ----------------------------------------------------------------------------------

@login_required
@require_GET
def export_data(request):
    """Everything this person has stored, as one JSON file. Secrets (API keys) are never included."""
    user, profile = request.user, UserProfile.for_user(request.user)
    data = {
        "exported_at": timezone.now().isoformat(),
        "account": {"username": user.get_username(), "email": user.email},
        "profile": {
            "target_roles": profile.target_roles, "locations": profile.locations,
            "remote_preference": profile.remote_preference, "salary_floor": profile.salary_floor,
            "deal_breakers": profile.deal_breakers, "about": profile.about, "cv": profile.profile_cv,
        },
        "knowledge": [
            {"title": s.title, "kind": s.kind, "enabled": s.enabled, "text": s.text}
            for s in KnowledgeSource.objects.filter(owner=user).exclude(key__in=["profile-cv", "careerops:cv.md"])
        ],
        "applications": [
            {
                "company": a.company, "role": a.role, "url": a.url, "status": a.status.name,
                "score": a.score, "verdict": a.decision, "summary": a.summary, "notes": a.notes,
                "found": a.found_date.isoformat(), "applied": a.applied_date.isoformat() if a.applied_date else None,
                "deadline": a.deadline.isoformat() if a.deadline else None, "description": a.description,
                "strengths": [i.text for i in a.insights.all() if i.kind == "strength"],
                "gaps": [i.text for i in a.insights.all() if i.kind == "gap"],
                "timeline": [f"{e.happened_at:%Y-%m-%d} {e.get_kind_display()}: {e.text}" for e in a.events.all()],
            }
            for a in mine(request).select_related("status").prefetch_related("insights", "events")
        ],
    }
    response = JsonResponse(data, json_dumps_params={"indent": 2, "ensure_ascii": False})
    response["Content-Disposition"] = 'attachment; filename="stillopen-export.json"'
    return response


@login_required
@require_POST
def delete_account(request):
    user = request.user
    if user.is_staff:
        messages.error(request, "Site admin accounts cannot be deleted here. Ask another admin.")
        return redirect("profile")
    if request.POST.get("confirm", "").strip() != user.get_username():
        messages.error(request, "Type your username exactly to confirm.")
        return redirect("profile")
    for doc in Document.objects.filter(application__owner=user):  # delete stored files too, not just rows
        if doc.file:
            doc.file.delete(save=False)
    for source in KnowledgeSource.objects.filter(owner=user):
        if source.file:
            source.file.delete(save=False)
    logout(request)
    user.delete()  # cascades to profile, applications, knowledge, events, runs
    return redirect("landing")
