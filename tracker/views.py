import mimetypes

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import Application, Bucket, Document, Event, ScoreBand, SiteConfig, Status
from .services import ai, careerops, liveness
from .services.files import resolve_document_path
from .services.paperless import PaperlessClient, PaperlessError, push_document


@require_GET
def landing(request):
    config = SiteConfig.load()
    if not config.landing_enabled:
        return redirect("dashboard")
    return render(request, "tracker/landing.html", {"config": config})


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
    config = SiteConfig.load()
    bands = list(ScoreBand.objects.all())
    buckets = list(Bucket.objects.all())
    statuses = list(Status.objects.all())
    apps = (
        Application.objects.select_related("status", "status__bucket", "source")
        .prefetch_related("insights", "documents__kind")
        .all()
    )

    tabs = {b.pk: [] for b in buckets}
    for app in apps:
        bucket = app.effective_bucket(config)
        tabs.setdefault(bucket.pk, []).append(card_for(app, config, bands))

    def sort_key(card):
        d = card["days_left"]
        urgent_first = 0 if card["urgent"] else 1
        return (urgent_first, -(card["percent"] if card["percent"] is not None else -1))

    tab_list = []
    for b in buckets:
        cards = sorted(tabs.get(b.pk, []), key=sort_key)
        tab_list.append({"bucket": b, "cards": cards})

    submitted = [c for t in tab_list for c in t["cards"] if c["app"].status.counts_as_applied]
    scored = [c["percent"] for t in tab_list for c in t["cards"] if c["percent"] is not None]
    run = liveness.current_run()
    context = {
        "config": config,
        "tabs": tab_list,
        "statuses": statuses,
        "stats": {
            "total": apps.count(),
            "submitted": len(submitted),
            "average_match": round(sum(scored) / len(scored)) if scored else None,
            "urgent": sum(1 for t in tab_list for c in t["cards"] if c["urgent"]),
        },
        "paperless_on": config.paperless_enabled and bool(config.effective_paperless_url),
        "paperless_url": config.effective_paperless_url,
        "run": run,
        "checked_at": apps.exclude(live_checked_at=None).order_by("-live_checked_at").values_list("live_checked_at", flat=True).first(),
    }
    return render(request, "tracker/dashboard.html", context)


@login_required
@require_POST
def set_status(request, pk):
    app = get_object_or_404(Application, pk=pk)
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
    app = get_object_or_404(Application, pk=pk)
    config = SiteConfig.load()
    try:
        result = ai.evaluate_application(app, config)
    except ai.AIError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    return JsonResponse({"ok": True, "match_percent": result["match_percent"], "method": app.ai_method})


@login_required
@require_POST
def liveness_start(request):
    run = liveness.start_run()
    return JsonResponse({"running": run.running, "done": run.done, "total": run.total})


@login_required
@require_GET
def liveness_status(request):
    run = liveness.current_run()
    if run is None:
        return JsonResponse({"running": False, "done": 0, "total": 0, "error": ""})
    return JsonResponse({"running": run.running, "done": run.done, "total": run.total, "error": run.error})


@login_required
@require_POST
def import_tracker(request):
    config = SiteConfig.load()
    try:
        counts = careerops.import_all(config)
    except careerops.ImportErrorMessage as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    return JsonResponse({"ok": True, **counts})


@login_required
@require_POST
def push_to_paperless(request, pk):
    doc = get_object_or_404(Document.objects.select_related("application", "kind"), pk=pk)
    config = SiteConfig.load()
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
    doc = get_object_or_404(Document, pk=pk)
    path = resolve_document_path(doc, SiteConfig.load())
    if path is None:
        raise Http404("File not available")
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if path.suffix.lower() == ".md":
        content_type = "text/plain; charset=utf-8"
    response = FileResponse(open(path, "rb"), content_type=content_type)
    response["Content-Disposition"] = f'inline; filename="{path.name}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response
