import functools
import mimetypes

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import forms, views_pipeline
from .models import (
    AIUsageEvent, Application, Bucket, Document, Event, JobSource, KnowledgeSource, Posting, ScoreBand, SiteConfig,
    Status, UserProfile,
)
from .services import ai, careerops, cvversions, jobtext, knowledge, liveness, scan
from .services import apply as apply_service
from .services import fit as fit_service, geo, guide
from .services.cvversions import CVError
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


def card_for(app, config, bands, areas=None, profile=None):
    percent = app.match_percent(config.score_scale)
    fit = fit_service.fit_flags(app, areas if areas is not None else [], profile)
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
        "cv": next(iter(app.cv_versions.all()), None),
        "fit": fit,
        "fit_level": fit_service.summary_level(fit),
        "fit_text": " ".join(f["text"] for f in fit if f["level"] != "ok") or " ".join(f["text"] for f in fit),
        "repost": scan.repost_signal(app.posting) if app.posting_id else None,
        "skill_matched": any(e.kind == "note" and "skill match" in e.text for e in app.events.all()),
    }


@login_required
@require_GET
def dashboard(request):
    config = SiteConfig.for_user(request.user)
    profile = UserProfile.for_user(request.user)
    bands = list(ScoreBand.objects.all())
    buckets = list(Bucket.objects.all())
    statuses = list(Status.objects.all())
    areas = list(request.user.search_areas.all())
    scan.maybe_auto_start(request.user)  # jobs simply appear: no button, no cron, no AI
    apps = mine(request).select_related("status", "status__bucket", "source", "posting", "posting__source").prefetch_related("insights", "documents__kind", "cv_versions", "events").select_related("applied_cv")

    tabs = {b.pk: [] for b in buckets}
    for app in apps:
        bucket = app.effective_bucket(config)
        tabs.setdefault(bucket.pk, []).append(card_for(app, config, bands, areas, profile))

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
        "followups": list(apply_service.due_followups(request.user)),
        "upcoming_interviews": views_pipeline.upcoming_interviews(request.user),
        "has_areas": bool(areas),
        "can_import": request.user.is_staff and bool(config.careerops_path),
        "run": liveness.current_run(request.user),
        "checked_at": apps.exclude(live_checked_at=None).order_by("-live_checked_at").values_list("live_checked_at", flat=True).first(),
        "scan_run": scan.current_run(request.user),
        "can_scan": JobSource.for_user(request.user, enabled=True).exists(),
        "greeting": guide.greeting(request.user, timezone.localtime()),
        "next_step": guide.next_step(
            profile, [c for t in tab_list for c in t["cards"]], has_areas=bool(areas),
            searching=bool(scan.current_run(request.user) and scan.current_run(request.user).running),
        ),
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
@require_POST
def scan_start(request):
    if throttled(request.user, "scan", settings.STILLOPEN_SCANS_PER_HOUR):
        return too_many()
    run = scan.start_run(request.user)
    return JsonResponse({"running": run.running, "done": run.done, "total": run.total})


@login_required
@require_GET
def scan_status(request):
    run = scan.current_run(request.user)
    if run is None:
        return JsonResponse({"running": False, "done": 0, "total": 0, "found": 0, "added": 0, "error": "", "entries": []})
    entries = [
        {
            "source": e.source_name,
            "connector": e.get_connector_display(),
            "found": e.found,
            "matched": e.matched,
            "added": e.added,
            "duplicates": e.duplicates,
            "outside": e.outside,
            "error": e.error,
        }
        for e in run.entries.all()
    ]
    return JsonResponse({
        "running": run.running, "done": run.done, "total": run.total,
        "found": run.found, "added": run.added, "error": run.error, "entries": entries,
    })


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
@require_POST
def quickadd_fetch(request):
    """Quick-add bar: given just a URL, best-effort fetch its title and description so the add-job form
    arrives prefilled. Nothing is saved here -- the person still reviews and submits the normal add-job
    form, same validation and the same limits as adding a job by hand."""
    if throttled(request.user, "quickadd", settings.STILLOPEN_QUICKADD_PER_HOUR):
        return too_many()
    url = request.POST.get("url", "").strip()
    if not url:
        return JsonResponse({"ok": False, "error": "Paste a job URL first."}, status=400)
    config = SiteConfig.for_user(request.user)
    try:
        posting = jobtext.fetch_posting(url, config)
    except jobtext.FetchError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    role, company = jobtext.guess_role_company(posting["title"]) if posting["title"] else ("", "")
    # Handed to add_job via the session, not a query string -- a full job description would routinely
    # blow past the ~8KB URL length most servers accept.
    request.session["quickadd_prefill"] = {
        "url": url,
        "role": role,
        "company": company,
        "description": posting["description"][:30000],
    }
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["GET", "POST"])
def add_job(request):
    initial = request.session.pop("quickadd_prefill", None) if request.method == "GET" else None
    form = forms.JobForm(request.POST or None, initial=initial)
    if request.method == "POST" and mine(request).count() >= settings.STILLOPEN_MAX_APPLICATIONS:
        form.add_error(None, f"You have reached the limit of {settings.STILLOPEN_MAX_APPLICATIONS} tracked jobs. Delete some first.")
    elif request.method == "POST" and form.is_valid():
        app = form.save(commit=False)
        app.owner = request.user
        app.status = (
            Status.objects.filter(name="Saved").first()
            or Status.objects.filter(bucket__is_closed=False).order_by("order").first()
            or Status.objects.first()
        )
        app.save()
        geo.fill_details(app)  # suggest location, arrangement, sponsorship and type from the posting
        Event.objects.create(application=app, kind="note", text="Added")
        messages.success(request, f"Saved {app.company} - {app.role}. Next, press Check my fit to see how well it suits you.")
        return redirect("dashboard")
    return render(request, "tracker/add_job.html", {"form": form, "config": SiteConfig.load()})


@login_required
@require_GET
def all_postings(request):
    """Every posting any scan has ever seen, matched or not -- shared across everyone, since a posting is a
    fact about the job market, not about any one person's search (same reasoning as the repost signal itself).
    This is the answer to "it found 586 but only tracked 11 -- where did the rest go?": nowhere, they were
    never hidden, just never auto-added because they didn't match your target roles."""
    qs = Posting.objects.filter(source__in=JobSource.for_user(request.user)).select_related("source").order_by("-last_seen_at")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(company__icontains=q))
    source_id = request.GET.get("source", "").strip()
    if source_id:
        qs = qs.filter(source_id=source_id)
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    tracked_urls = set(Application.objects.filter(owner=request.user).exclude(url="").values_list("url", flat=True))
    rows = [{"posting": p, "repost": scan.repost_signal(p), "tracked": p.url in tracked_urls} for p in page]
    qs_no_page = request.GET.copy()
    qs_no_page.pop("page", None)
    return render(request, "tracker/postings.html", {
        "config": SiteConfig.for_user(request.user),
        "page": page,
        "rows": rows,
        "q": q,
        "source_id": source_id,
        "sources": JobSource.for_user(request.user).order_by("name"),
        "qs": qs_no_page.urlencode(),
    })


@login_required
@require_POST
def add_posting(request, pk):
    posting = get_object_or_404(Posting, pk=pk, source__in=JobSource.for_user(request.user))
    target = reverse("all_postings")
    qs = request.POST.get("qs", "")
    if qs:
        target = f"{target}?{qs}"
    if mine(request).filter(url=posting.url).exists():
        messages.info(request, "Already in your tracker.")
        return redirect(target)
    if mine(request).count() >= settings.STILLOPEN_MAX_APPLICATIONS:
        messages.error(request, f"You have reached the limit of {settings.STILLOPEN_MAX_APPLICATIONS} tracked jobs. Delete some first.")
        return redirect(target)
    app = Application(
        owner=request.user,
        company=posting.company or posting.source.name,
        role=posting.title,
        url=posting.url,
        location_text=posting.location,
        posting=posting,
        status=(
            Status.objects.filter(name="Saved").first()
            or Status.objects.filter(bucket__is_closed=False).order_by("order").first()
            or Status.objects.first()
        ),
        found_date=timezone.localdate(),
    )
    app.save()
    geo.fill_details(app)
    Event.objects.create(application=app, kind="note", text="Added from All postings")
    messages.success(request, f"Added {app.company} - {app.role}.")
    return redirect(target)


def _save_cv_history(request, obj, form):
    knowledge.sync_cv(SiteConfig.for_user(request.user), request.user)
    if "profile_cv" in form.changed_data and obj.profile_cv.strip():
        try:
            cvversions.record_master(request.user, obj.profile_cv)  # every CV change is kept in the history
        except CVError:
            pass


@login_required
@require_http_methods(["GET", "POST"])
def welcome(request):
    """A short, skippable first stop after sign-up."""
    obj = UserProfile.for_user(request.user)
    form = forms.WelcomeForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        _save_cv_history(request, obj, form)
        forms.create_default_areas(request.user, obj.home_country, form.cleaned_data.get("open_remote", False), form.cleaned_data.get("other_places", ""))
        obj.onboarding_done = True
        obj.save(update_fields=["onboarding_done"])
        messages.success(request, "Lovely, that helps. We are searching for jobs that fit you now; they will appear here in a minute.")
        return redirect("dashboard")
    return render(request, "tracker/welcome.html", {"form": form, "config": SiteConfig.load()})


@login_required
@require_POST
def welcome_skip(request):
    obj = UserProfile.for_user(request.user)
    obj.onboarding_done = True
    obj.save(update_fields=["onboarding_done"])
    return redirect("dashboard")


@login_required
@require_http_methods(["GET", "POST"])
def profile(request):
    obj = UserProfile.for_user(request.user)
    form = forms.ProfileForm(request.POST or None, request.FILES or None, instance=obj)
    with_areas = request.method == "POST" and "areas-TOTAL_FORMS" in request.POST  # a post without the rows leaves them as they are
    areas = forms.SearchAreaFormSet(request.POST if with_areas else None, instance=request.user, prefix="areas")
    if request.method == "POST" and form.is_valid() and (areas.is_valid() if with_areas else True):
        form.save()
        if with_areas:
            forms.save_areas(areas, request.user)
            for place in areas.unrecognised_places:
                messages.warning(request, f'"{place}" is not a place we recognise, so jobs are matched to it by name only.')
        _save_cv_history(request, obj, form)
        messages.success(request, "Saved. Your next matches will use this.")
        return redirect("profile")
    return render(request, "tracker/profile.html", {
        "form": form, "areas": areas, "profile": obj, "config": SiteConfig.load(), "welcome": request.GET.get("welcome"),
        "sources": KnowledgeSource.objects.filter(owner=request.user).exclude(key__in=["profile-cv", "careerops:cv.md"]).count(),
        "account": {
            "email": request.user.email,
            "jobs": mine(request).count(),
            "cv_versions": request.user.cv_versions.count(),
            "cover_letters": request.user.cover_letters.count(),
            "interviews": request.user.interviews.count(),
            "contacts": request.user.contacts.count(),
            "offers": request.user.offers.count(),
            "documents": KnowledgeSource.objects.filter(owner=request.user).exclude(key__in=["profile-cv", "careerops:cv.md"]).count(),
            "google": request.user.socialaccount_set.filter(provider="google").exists(),
        },
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
    now = timezone.localtime()
    usage = AIUsageEvent.objects.filter(
        owner=request.user, created_at__year=now.year, created_at__month=now.month,
    ).aggregate(input_tokens=Sum("input_tokens"), output_tokens=Sum("output_tokens"), cost_usd=Sum("cost_usd"), calls=Count("id"))
    usage["total_tokens"] = (usage["input_tokens"] or 0) + (usage["output_tokens"] or 0)
    usage["any_estimated"] = AIUsageEvent.objects.filter(
        owner=request.user, created_at__year=now.year, created_at__month=now.month, cost_is_estimate=True, cost_usd__isnull=False,
    ).exists()
    return render(request, "tracker/profile_ai.html", {
        "form": form, "config": SiteConfig.load(), "has_key": bool(obj.ai_key_encrypted),
        "has_rag_key": bool(obj.rag_embedding_key_encrypted), "usage": usage,
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
            "target_roles": profile.target_roles, "employment_types": profile.employment_types,
            "seniority_levels": profile.seniority_levels, "industries": profile.industries, "languages": profile.languages,
            "notice_period": profile.notice_period, "salary_floor": profile.salary_floor,
            "search_areas": [a.describe() for a in user.search_areas.all()],
            "deal_breakers": profile.deal_breakers, "about": profile.about, "cv": profile.profile_cv,
        },
        "knowledge": [
            {"title": s.title, "kind": s.kind, "enabled": s.enabled, "text": s.text}
            for s in KnowledgeSource.objects.filter(owner=user).exclude(key__in=["profile-cv", "careerops:cv.md"])
        ],
        "cv_versions": [
            {"label": v.label, "kind": v.kind, "source": v.source, "created": v.created_at.isoformat(),
             "for_job": f"{v.application.company} - {v.application.role}" if v.application else None, "content": v.content}
            for v in user.cv_versions.select_related("application")
        ],
        "interviews": [
            {"for_job": f"{i.application.company} - {i.application.role}", "when": i.scheduled_at.isoformat(), "kind": i.kind,
             "where": i.where, "notes": i.notes, "outcome": i.outcome}
            for i in user.interviews.select_related("application")
        ],
        "contacts": [
            {"name": c.name, "company": c.company, "title": c.title, "email": c.email, "link": c.link, "notes": c.notes,
             "last_contacted": c.last_contacted.isoformat() if c.last_contacted else None,
             "referrals": [{"for_job": f"{r.application.company} - {r.application.role}", "status": r.status, "note": r.note} for r in c.referrals.all()]}
            for c in user.contacts.prefetch_related("referrals__application")
        ],
        "offers": [
            {"for_job": f"{o.application.company} - {o.application.role}", "status": o.status, "currency": o.currency,
             "base": str(o.base), "period": o.period, "bonus": str(o.bonus), "equity": str(o.equity),
             "other_benefits": str(o.other_benefits), "signing": str(o.signing),
             "deadline": o.deadline.isoformat() if o.deadline else None, "notes": o.notes}
            for o in user.offers.select_related("application")
        ],
        "cover_letters": [
            {"for_job": f"{l.application.company} - {l.application.role}", "source": l.source,
             "created": l.created_at.isoformat(), "content": l.content}
            for l in user.cover_letters.select_related("application")
        ],
        "applications": [
            {
                "company": a.company, "role": a.role, "url": a.url, "status": a.status.name,
                "score": a.score, "verdict": a.decision, "summary": a.summary, "notes": a.notes,
                "applied_channel": a.applied_channel, "applied_note": a.applied_note, "applied_cv_label": a.applied_cv.label if a.applied_cv else None,
                "follow_up_date": a.follow_up_date.isoformat() if a.follow_up_date else None, "description_at_apply": a.jd_at_apply,
                "location": a.location_text, "country": a.country, "arrangement": a.arrangement,
                "sponsorship": a.sponsorship, "relocation": a.relocation, "employment_type": a.employment_type, "seniority": a.seniority,
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


@login_required
@require_http_methods(["GET", "POST"])
def job_edit(request, pk):
    app = owned_app(request, pk)
    form = forms.JobEditForm(request.POST or None, instance=app)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Saved.")
        return redirect("job_edit", pk=app.pk)
    return render(request, "tracker/job_edit.html", {"form": form, "app": app, "config": SiteConfig.load(),
                                                    "fit": fit_service.fit_flags(app)})


@login_required
@require_POST
def job_redetect(request, pk):
    app = owned_app(request, pk)
    if app.details_source == "manual":
        messages.error(request, "You set these details yourself, so they are left alone. Clear a field and save to let detection fill it.")
    else:
        changed = geo.fill_details(app, overwrite=True)
        messages.success(request, "Re-read the posting." + (f" Updated: {', '.join(changed)}." if changed else " Nothing to change."))
    return redirect("job_edit", pk=app.pk)
