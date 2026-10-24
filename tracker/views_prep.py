"""Prep plans: ask for one from a job's gaps, read and decide on the draft, then follow it.

Every lookup is owner-scoped: a plan, lesson, milestone or question that is not yours answers 404. See docs/design/prep-plans.md.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import Application, PrepLesson, PrepMilestone, PrepPlan, PrepQuestion, SiteConfig
from .services import prep


def _config(request) -> SiteConfig:
    config = SiteConfig.for_user(request.user)
    if not config.prep_enabled:
        raise Http404("Prep plans are switched off.")
    return config


def _plan(request, pk) -> PrepPlan:
    return get_object_or_404(PrepPlan, pk=pk, owner=request.user)


def _int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@login_required
@require_GET
def prep_list(request):
    _config(request)
    plans = PrepPlan.objects.filter(owner=request.user).select_related("application").annotate(
        lessons_total=Count("weeks__lessons", distinct=True),
        lessons_done=Count("weeks__lessons", filter=Q(weeks__lessons__done_at__isnull=False), distinct=True),
    )
    return render(request, "tracker/prep_list.html", {"plans": plans, "config": SiteConfig.load()})


@login_required
@require_POST
def prep_create(request, pk):
    config = _config(request)
    app = get_object_or_404(Application, pk=pk, owner=request.user)
    existing = PrepPlan.objects.filter(owner=request.user, application=app).exclude(status="failed").first()
    if existing:
        messages.info(request, "You already have a prep plan for this job.")
        return redirect("prep_plan", pk=existing.pk)
    try:
        plan = prep.create_plan(app, config, weeks=_int(request.POST.get("weeks")), hours=_int(request.POST.get("hours")))
    except prep.PrepError as exc:
        messages.error(request, str(exc))
        return redirect("dashboard")
    return redirect("prep_plan", pk=plan.pk)


@login_required
@require_GET
def prep_plan(request, pk):
    _config(request)
    plan = _plan(request, pk)
    weeks = plan.weeks.prefetch_related("lessons__questions", "milestones")
    done, total = plan.progress_counts()
    return render(request, "tracker/prep_plan.html", {
        "config": SiteConfig.load(), "plan": plan, "weeks": weeks, "done": done, "total": total, "percent": round(100 * done / total) if total else 0,
        "question_count": plan.questions.filter(removed=False).count(),
        "unchecked_links": sum(1 for q in plan.questions.filter(removed=False) if q.checks.get("sources_reachable") is False),
    })


@login_required
@require_POST
def prep_activate(request, pk):
    config = _config(request)
    plan = _plan(request, pk)
    try:
        prep.activate(plan, config)
    except prep.PrepError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Your prep plan has started. Tick lessons off as you finish them.")
    return redirect("prep_plan", pk=plan.pk)


@login_required
@require_POST
def prep_discard(request, pk):
    _config(request)
    plan = _plan(request, pk)
    if plan.status == "generating":
        messages.error(request, "This plan is still being written. You can discard it when it finishes.")
        return redirect("prep_plan", pk=plan.pk)
    plan.delete()
    messages.success(request, "Prep plan discarded.")
    return redirect("prep_list")


@login_required
@require_POST
def prep_remove(request, kind, pk):
    """While reviewing a draft: take out a lesson (and its questions) or a single question."""
    _config(request)
    if kind == "lesson":
        lesson = get_object_or_404(PrepLesson, pk=pk, week__plan__owner=request.user)
        plan = lesson.week.plan
        if plan.status == "draft":
            lesson.questions.update(removed=True)
            lesson.delete()
    elif kind == "question":
        question = get_object_or_404(PrepQuestion, pk=pk, plan__owner=request.user)
        plan = question.plan
        if plan.status == "draft":
            question.removed = True
            question.save(update_fields=["removed"])
    else:
        raise Http404("Unknown item.")
    return redirect("prep_plan", pk=plan.pk)


@login_required
@require_POST
def prep_tick(request, kind, pk):
    """Mark a lesson or a milestone done, or not done again, once the plan has started."""
    _config(request)
    if kind == "lesson":
        item = get_object_or_404(PrepLesson, pk=pk, week__plan__owner=request.user)
        plan = item.week.plan
    elif kind == "milestone":
        item = get_object_or_404(PrepMilestone, pk=pk, week__plan__owner=request.user)
        plan = item.week.plan
    else:
        raise Http404("Unknown item.")
    if plan.status in ("active", "done"):
        item.done_at = None if item.done_at else timezone.now()
        item.save(update_fields=["done_at"])
        done, total = plan.progress_counts()
        new_status = "done" if total and done == total else "active"
        if new_status != plan.status:
            plan.status = new_status
            plan.save(update_fields=["status"])
    return redirect("prep_plan", pk=plan.pk)
