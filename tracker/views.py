import mimetypes

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from .models import Application, Document, KnowledgeSource, PrepAnswer, SiteConfig, UserProfile
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
        "prep_plans": [
            {"title": p.title, "summary": p.summary, "status": p.status, "weeks": p.weeks_count, "hours_per_week": p.hours_per_week,
             "for_job": f"{p.application.company} - {p.application.role}" if p.application else None, "gaps": p.gap_skills,
             "lessons": [{"week": w.order, "title": le.title, "gap": le.gap, "sources": le.sources, "done": bool(le.done_at)}
                         for w in p.weeks.all() for le in w.lessons.all()],
             "tasks": [{"week": w.order, "kind": m.kind, "text": m.text, "done": bool(m.done_at)} for w in p.weeks.all() for m in w.milestones.all()],
             "topics": [t.title for t in p.topics.all()],
             "practice_days": [{"number": c.number, "day": c.day.isoformat(), "finished": bool(c.completed_at)} for c in p.challenges.all()],
             "questions": [{"prompt": q.prompt, "choices": q.choices, "correct": q.correct, "explanation": q.explanation, "sources": q.sources}
                           for q in p.questions.filter(removed=False)],
             "answers": [{"question": a.question.prompt, "chosen": a.chosen, "correct": a.correct, "day": a.answered_on.isoformat(), "mode": a.mode}
                         for a in PrepAnswer.objects.filter(owner=user, question__plan=p).select_related("question")]}
            for p in user.prep_plans.select_related("application").prefetch_related("weeks__lessons")
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
        "interview_prep": [
            {"for_job": f"{ip.application.company} - {ip.application.role}", "created": ip.created_at.isoformat(), "content": ip.content}
            for ip in user.interview_preps.select_related("application")
        ],
        "own_job_sources": [
            {"name": s.name, "connector": s.connector, "board_token": s.board_token, "enabled": s.enabled}
            for s in user.job_sources.all()
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
