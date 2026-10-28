"""What a job's "download everything" zip would hold (the import route itself lives in `ats.py`, beside `/cv/builder`: it has to be registered before `/cv/{cv_id}`)."""
from django.urls import reverse
from ninja import Router

from ..models import CoverLetter, CVVersion
from .common import owned_job

router = Router()


def bundle_parts(owner, job):
    """(newest tailored CV, cover letter) of this person for this job; either may be None."""
    cv = CVVersion.objects.filter(owner=owner, application=job, kind="tailored").order_by("-created_at", "-pk").first()
    letter = CoverLetter.objects.filter(owner=owner, application=job).order_by("-updated_at", "-pk").first()
    return cv, letter


@router.get("/jobs/{job_id}/documents", summary="Can this job's CV and cover letter be downloaded together, and if not, why")
def documents(request, job_id: int):
    job = owned_job(request, job_id)
    cv, letter = bundle_parts(request.user, job)
    if cv is None and letter is None:
        return {"ready": False, "url": None, "reason": "Make a CV or a cover letter for this job first."}
    blocked = [name for name, doc in (("CV", cv), ("cover letter", letter)) if doc is not None and not doc.exportable]
    if blocked:
        return {"ready": False, "url": None, "reason": f"Review and approve the flagged items in the {' and '.join(blocked)} first, then they can be downloaded."}
    return {"ready": True, "url": reverse("job_documents_zip", args=[job.pk]), "has_cv": cv is not None, "has_cover": letter is not None, "reason": ""}
