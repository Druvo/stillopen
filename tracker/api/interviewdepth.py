"""Interview and company depth for the new app: a job's hiring-process timeline, "this came up" ticks on prep questions, the
person's own question bank and company pages.

Every row is the person's own and anything else is a 404. Links on a company page are stored as text and never fetched."""
from typing import Any

from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Body, Router, Schema
from ninja.errors import HttpError

from ..models import Application, BankQuestion, Interview, PrepQuestion
from ..services import assist, interviewdepth
from .common import owned, owned_job

router = Router()
Raw = Body[dict[str, Any]]


# --- the hiring process of one job -----------------------------------------------------------------

@router.get("/jobs/{job_id}/process", summary="The stages of one job's hiring process, in order, with who interviewed")
def job_process(request, job_id: int):
    app = get_object_or_404(Application.objects.select_related("status"), pk=job_id, owner=request.user)
    return interviewdepth.timeline(app)


# --- "this came up" ---------------------------------------------------------------------------------

class CameUpIn(Schema):
    value: bool


class JobCameUpIn(Schema):
    key: str
    value: bool


def _prep_keys(app) -> list[str]:
    content = assist.stored_interview_prep(app) or {}
    return [q["id"] for g in content.get("groups", []) if isinstance(g, dict) for q in g.get("questions", []) if isinstance(q, dict) and q.get("id")]


@router.get("/jobs/{job_id}/came-up", summary="Which of a job's interview-prep questions the person ticked as really asked")
def job_came_up(request, job_id: int):
    app = owned_job(request, job_id)
    return interviewdepth.job_tally(request.user, app, _prep_keys(app))


@router.post("/jobs/{job_id}/came-up", summary="Tick or untick one interview-prep question as having come up")
def set_job_came_up(request, job_id: int, payload: JobCameUpIn):
    app = owned_job(request, job_id)
    keys = _prep_keys(app)
    if payload.key not in keys:
        raise HttpError(400, "That question is not in this job's list.")
    interviewdepth.set_came_up(request.user, application=app, key=payload.key, value=payload.value)
    return interviewdepth.job_tally(request.user, app, keys)


@router.get("/prep/plans/{plan_id}/came-up", summary="Which of a plan's quiz questions the person ticked as really asked")
def plan_came_up(request, plan_id: int):
    from .prep import config_for, plan_for

    config_for(request)
    return interviewdepth.plan_tally(request.user, plan_for(request, plan_id))


@router.post("/prep/questions/{question_id}/came-up", summary="Tick or untick a plan's quiz question as having come up")
def set_plan_came_up(request, question_id: int, payload: CameUpIn):
    from .prep import config_for

    config_for(request)
    question = get_object_or_404(PrepQuestion, pk=question_id, plan__owner=request.user)
    interviewdepth.set_came_up(request.user, prep_question=question, value=payload.value)
    return interviewdepth.plan_tally(request.user, question.plan)


# --- the question bank ------------------------------------------------------------------------------

def _bank_fields(payload: dict, existing: BankQuestion | None = None) -> dict:
    out: dict = {}
    if "question" in payload or existing is None:
        text = " ".join(str(payload.get("question") or "").split())
        if not text:
            raise HttpError(400, "Write the question first.")
        if len(text) > 400:
            raise HttpError(400, "A question can be up to 400 characters.")
        out["question"] = text
    if "answer" in payload:
        answer = "" if payload["answer"] is None else str(payload["answer"])
        if len(answer) > 4000:
            raise HttpError(400, "An answer can be up to 4000 characters.")
        out["answer"] = answer
    if "tags" in payload:
        try:
            out["tags"] = interviewdepth.clean_tags(payload["tags"])
        except ValueError as exc:
            raise HttpError(400, str(exc)) from exc
    return out


def _ids(payload: dict, name: str) -> list[int] | None:
    if name not in payload:
        return None
    raw = payload[name]
    if not isinstance(raw, list) or len(raw) > 50 or not all(isinstance(i, int) and not isinstance(i, bool) for i in raw):
        raise HttpError(400, "Pick from the list.")
    return raw


def _links(request, item: BankQuestion, payload: dict) -> None:
    """Only the person's own interviews and jobs can be linked; anything else is refused, not skipped."""
    interviews, jobs = _ids(payload, "interview_ids"), _ids(payload, "job_ids")
    if interviews is not None:
        found = list(Interview.objects.filter(owner=request.user, pk__in=interviews))
        if len(found) != len(set(interviews)):
            raise HttpError(400, "One of those interviews is not yours.")
        item.interviews.set(found)
    if jobs is not None:
        found_jobs = list(Application.objects.filter(owner=request.user, pk__in=jobs))
        if len(found_jobs) != len(set(jobs)):
            raise HttpError(400, "One of those jobs is not yours.")
        item.applications.set(found_jobs)


def _fresh(request, pk: int) -> dict:
    item = BankQuestion.objects.filter(owner=request.user, pk=pk).prefetch_related("interviews__application", "applications").get()
    return interviewdepth.bank_row(item)


@router.get("/bank", summary="The person's own interview questions, with their answers")
def list_bank(request, q: str = "", tag: str = ""):
    return {
        "questions": [interviewdepth.bank_row(x) for x in interviewdepth.bank_list(request.user, q[:100], tag[:40])],
        "tags": interviewdepth.all_tags(request.user),
        "interviews": [
            {"id": i.pk, "label": f"{i.stage_name} · {i.application.company}"}
            for i in Interview.objects.filter(owner=request.user).select_related("application")
        ],
        "jobs": [{"id": a.pk, "label": f"{a.company} - {a.role}"} for a in Application.objects.filter(owner=request.user).order_by("company", "role")],
    }


@router.post("/bank", summary="Save a question to the person's bank")
def create_bank(request, payload: Raw):
    fields = _bank_fields(payload)
    if BankQuestion.objects.filter(owner=request.user).count() >= interviewdepth.MAX_BANK:
        raise HttpError(400, f"Your question bank is full ({interviewdepth.MAX_BANK}). Delete some first.")
    with transaction.atomic():
        item = BankQuestion.objects.create(owner=request.user, **fields)
        _links(request, item, payload)
    return _fresh(request, item.pk)


@router.patch("/bank/{bank_id}", summary="Change a saved question")
def update_bank(request, bank_id: int, payload: Raw):
    item = owned(BankQuestion, request, bank_id)
    fields = _bank_fields(payload, item)
    with transaction.atomic():
        for name, value in fields.items():
            setattr(item, name, value)
        item.save()
        _links(request, item, payload)
    return _fresh(request, item.pk)


@router.delete("/bank/{bank_id}", summary="Delete a saved question (ask first when it is linked to an interview or job)")
def delete_bank(request, bank_id: int, confirm: bool = False):
    item = owned(BankQuestion, request, bank_id)
    if (item.interviews.exists() or item.applications.exists()) and not confirm:
        raise HttpError(409, "This question is linked to an interview or a job. Delete it anyway?")
    item.delete()
    return {"ok": True}


# --- companies --------------------------------------------------------------------------------------

@router.get("/companies", summary="Every company in the person's jobs and contacts")
def list_companies(request):
    return {"companies": interviewdepth.companies(request.user)}


@router.get("/companies/page", summary="One company: jobs, contacts, interviews, offers, notes and links")
def company_page(request, key: str):
    page = interviewdepth.company_page(request.user, key)
    if page is None:
        raise Http404("No company with that name in your tracker.")
    return page


@router.patch("/companies/page", summary="Change a company's notes, links or watch star")
def update_company(request, key: str, payload: Raw):
    page = interviewdepth.company_page(request.user, key)
    if page is None:
        raise Http404("No company with that name in your tracker.")
    try:
        interviewdepth.save_company(request.user, key, page["name"], payload)
    except ValueError as exc:
        raise HttpError(400, str(exc)) from exc
    return interviewdepth.company_page(request.user, key)
