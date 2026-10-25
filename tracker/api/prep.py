"""Prep plans for the new app. Same rules as `views_prep.py`: switched off by the admin means 404, and every plan, lesson,
milestone and question that is not the person's own is a 404. A practice never shows answers or explanations before it is sent."""
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from ..models import Application, PrepLesson, PrepMilestone, PrepPlan, PrepQuestion, SiteConfig
from ..services import prep, quiz

router = Router()


def config_for(request) -> SiteConfig:
    config = SiteConfig.for_user(request.user)
    if not config.prep_enabled:
        raise Http404("Prep plans are switched off.")
    return config


def plan_for(request, plan_id) -> PrepPlan:
    return get_object_or_404(PrepPlan, pk=plan_id, owner=request.user)


def practice_plan(request, plan_id) -> PrepPlan:
    plan = plan_for(request, plan_id)
    if plan.status not in ("active", "done"):
        raise Http404("Start the plan first.")
    return plan


def _job(plan: PrepPlan):
    app = plan.application
    return {"id": app.pk, "role": app.role, "company": app.company} if app else None


def _sources(raw) -> list:
    return [{"title": s.get("title", ""), "url": s.get("url", ""), "checked": s.get("checked")} for s in raw or [] if isinstance(s, dict)]


def _summary(plan: PrepPlan) -> dict:
    return {
        "id": plan.pk, "title": plan.title, "status": plan.status, "status_label": plan.get_status_display(),
        "job": _job(plan), "lessons_total": plan.lessons_total, "lessons_done": plan.lessons_done,
    }


@router.get("/prep/plans", summary="The person's prep plans")
def list_plans(request):
    config_for(request)
    plans = PrepPlan.objects.filter(owner=request.user).select_related("application").annotate(
        lessons_total=Count("weeks__lessons", distinct=True),
        lessons_done=Count("weeks__lessons", filter=Q(weeks__lessons__done_at__isnull=False), distinct=True),
    )
    return {"plans": [_summary(p) for p in plans]}


def _question_for_review(q: PrepQuestion) -> dict:
    return {
        "id": q.pk, "prompt": q.prompt, "kind": q.kind, "kind_label": q.get_kind_display(), "choices": q.choices, "correct": q.correct,
        "explanation": q.explanation, "sources": _sources(q.sources),
    }


@router.get("/prep/plans/{plan_id}", summary="One prep plan, with its weeks, lessons and tasks")
def get_plan(request, plan_id: int):
    config_for(request)
    plan = plan_for(request, plan_id)
    draft = plan.status == "draft"
    started = plan.status in ("active", "done")
    done, total = plan.progress_counts()
    questions = list(plan.questions.filter(removed=False))
    weeks = []
    for week in plan.weeks.prefetch_related("lessons__questions", "milestones"):
        lessons = []
        for lesson in week.lessons.all():
            item = {
                "id": lesson.pk, "title": lesson.title, "topics": lesson.topics, "gap": lesson.gap, "sources": _sources(lesson.sources),
                "done": lesson.done_at is not None,
            }
            if draft:  # questions (with their answers) are only shown while reviewing the draft
                item["questions"] = [_question_for_review(q) for q in lesson.questions.all() if not q.removed]
            lessons.append(item)
        weeks.append({
            "id": week.pk, "order": week.order, "title": week.title, "goal": week.goal, "hours": week.hours, "lessons": lessons,
            "milestones": [{"id": m.pk, "kind": m.kind, "kind_label": m.get_kind_display(), "text": m.text, "done": m.done_at is not None} for m in week.milestones.all()],
        })
    return {
        **_summary(_with_counts(plan, done, total)),
        "summary": plan.summary, "progress": plan.progress, "error": plan.error, "gap_skills": plan.gap_skills,
        "hours_per_week": plan.hours_per_week, "generator": plan.generator,
        "percent": round(100 * done / total) if total else 0,
        "question_count": len(questions),
        "streak": quiz.streak(plan) if started else 0,
        "weak_topics": [{"slug": t.slug, "title": t.title} for t in quiz.weak_topics(plan)] if started else [],
        "done_today": plan.challenges.filter(day=timezone.localdate(), completed_at__isnull=False).exists(),
        "unchecked_links": sum(1 for q in questions if q.checks.get("sources_reachable") is False),
        "weeks": weeks,
    }


def _with_counts(plan: PrepPlan, done: int, total: int) -> PrepPlan:
    plan.lessons_done, plan.lessons_total = done, total
    return plan


class CreateIn(Schema):
    weeks: int | None = None
    hours: int | None = None


@router.post("/jobs/{job_id}/prep", summary="Ask for a prep plan for a job")
def create_plan(request, job_id: int, payload: CreateIn):
    config = config_for(request)
    app = get_object_or_404(Application, pk=job_id, owner=request.user)
    existing = PrepPlan.objects.filter(owner=request.user, application=app).exclude(status="failed").first()
    if existing:
        return {"id": existing.pk, "existing": True}
    try:
        plan = prep.create_plan(app, config, weeks=payload.weeks, hours=payload.hours)
    except prep.PrepError as exc:
        raise HttpError(400, str(exc))
    return {"id": plan.pk, "existing": False}


@router.post("/prep/plans/{plan_id}/start", summary="Start a reviewed draft")
def start_plan(request, plan_id: int):
    config = config_for(request)
    plan = plan_for(request, plan_id)
    try:
        prep.activate(plan, config)
    except prep.PrepError as exc:
        raise HttpError(400, str(exc))
    return {"ok": True}


@router.delete("/prep/plans/{plan_id}", summary="Discard a plan")
def discard_plan(request, plan_id: int):
    config_for(request)
    plan = plan_for(request, plan_id)
    if plan.status == "generating":
        raise HttpError(400, "This plan is still being written. You can discard it when it finishes.")
    plan.delete()
    return {"ok": True}


@router.delete("/prep/lessons/{lesson_id}", summary="Take a lesson out of a draft")
def remove_lesson(request, lesson_id: int):
    config_for(request)
    lesson = get_object_or_404(PrepLesson, pk=lesson_id, week__plan__owner=request.user)
    prep.remove_lesson(lesson)
    return {"ok": True}


@router.delete("/prep/questions/{question_id}", summary="Take a question out of a draft")
def remove_question(request, question_id: int):
    config_for(request)
    question = get_object_or_404(PrepQuestion, pk=question_id, plan__owner=request.user)
    prep.remove_question(question)
    return {"ok": True}


@router.post("/prep/lessons/{lesson_id}/tick", summary="Mark a lesson done, or not done again")
def tick_lesson(request, lesson_id: int):
    config_for(request)
    lesson = get_object_or_404(PrepLesson, pk=lesson_id, week__plan__owner=request.user)
    prep.toggle_done(lesson.week.plan, lesson)
    return {"ok": True, "done": lesson.done_at is not None}


@router.post("/prep/milestones/{milestone_id}/tick", summary="Mark a task done, or not done again")
def tick_milestone(request, milestone_id: int):
    config_for(request)
    milestone = get_object_or_404(PrepMilestone, pk=milestone_id, week__plan__owner=request.user)
    prep.toggle_done(milestone.week.plan, milestone)
    return {"ok": True, "done": milestone.done_at is not None}


# --- today's practice ----------------------------------------------------------------------------

@router.get("/prep/plans/{plan_id}/today", summary="Today's practice")
def today(request, plan_id: int):
    config = config_for(request)
    plan = practice_plan(request, plan_id)
    try:
        challenge = quiz.build_challenge(plan, config.prep_daily_questions)
    except quiz.QuizError as exc:
        raise HttpError(400, str(exc))
    finished = challenge.completed_at is not None
    rows = []
    if finished:
        for r in quiz.results(challenge):
            q = r["question"]
            rows.append({
                "id": q.pk, "topic": q.topic.title, "prompt": q.prompt, "kind": q.kind, "choices": q.choices, "review": r["review"],
                "chosen": r["chosen"], "right": r["correct"], "correct": q.correct, "explanation": q.explanation, "sources": _sources(q.sources),
            })
    else:  # nothing that gives the answer away before it is sent
        for item in challenge.items.select_related("question__topic"):
            q = item.question
            rows.append({"id": q.pk, "topic": q.topic.title, "prompt": q.prompt, "kind": q.kind, "choices": q.choices, "review": item.is_review})
    return {
        "plan": {"id": plan.pk, "title": plan.title}, "finished": finished, "rows": rows,
        "right": sum(1 for r in rows if r.get("right")), "total": len(rows),
        "streak": quiz.streak(plan), "weak_topics": [{"slug": t.slug, "title": t.title} for t in quiz.weak_topics(plan)],
    }


class AnswersIn(Schema):
    answers: dict[str, list[int]]


@router.post("/prep/plans/{plan_id}/answers", summary="Send today's answers")
def answer(request, plan_id: int, payload: AnswersIn):
    config = config_for(request)
    plan = practice_plan(request, plan_id)
    challenge = quiz.build_challenge(plan, config.prep_daily_questions)
    choices = {}
    for key, values in payload.answers.items():
        if key.isdigit():
            choices[int(key)] = values
    try:
        result = quiz.submit(challenge, choices)
    except quiz.QuizError as exc:
        raise HttpError(400, str(exc))
    return {"ok": True, **result}
