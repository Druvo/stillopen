"""Fixtures of the CV and cover letter API for the route inventory test (see `_world_modules` in tests_api.py)."""
from tracker.models import CoverLetter, CVVersion

BODIES = {
    ("POST", "/api/v1/cv/{cv_id}/edit"): {"content": "# Someone\n- a line"},
    ("POST", "/api/v1/cv/{cv_id}/improve"): {},  # ATS check (GET /cv/{cv_id}/ats) needs no body; improve asks the person's own AI, so a stranger's CV is refused first
    ("POST", "/api/v1/cv/builder"): {"answers": {}},
    ("POST", "/api/v1/jobs/{job_id}/tailor"): {"mode": "keywords"},
    ("POST", "/api/v1/cover/{cover_id}/save"): {"content": "Dear hiring team,"},
    ("POST", "/api/v1/jobs/{job_id}/cover-letter"): {"mode": "keywords"},
    ("POST", "/api/v1/cv/{cv_id}/refine"): {"message": "make it shorter"},
    ("POST", "/api/v1/cover/{cover_id}/refine"): {"message": "make it shorter"},
}


def world(owner, ids):
    master = CVVersion.objects.create(owner=owner, kind="master", content="# Master\n- built things", label="Initial CV", approved=True)
    tailored = CVVersion.objects.create(
        owner=owner, kind="tailored", application_id=ids["job_id"], parent=master, content="# Tailored\n- built things", label="Tailored",
        source="keywords", check_report=[{"kind": "name", "text": "Kubernetes", "line": 2}],
    )
    letter = CoverLetter.objects.create(owner=owner, application_id=ids["job_id"], content="Dear hiring team,")
    return {"cv_id": tailored.pk, "cover_id": letter.pk}
