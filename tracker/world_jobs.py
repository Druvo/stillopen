"""Fixtures of the jobs, postings, documents and apply API for the route inventory test (see `_world_modules` in tests_api.py)."""
from tracker.models import Document, DocumentKind, JobSource, KnowledgeSource, Posting

BODIES = {
    ("POST", "/quickadd"): {"url": "https://jobs.example.com/1"},
    ("POST", "/jobs"): {"company": "Acme", "role": "Dev"},
    ("PUT", "/jobs/{job_id}/details"): {"company": "Acme", "role": "Dev"},
    ("POST", "/documents"): {"title": "Notes", "text": "I built things."},
    ("POST", "/jobs/{job_id}/applied"): {},
    ("POST", "/jobs/{job_id}/followup/snooze"): {"days": 3},
}


def world(owner, ids):
    """A person's own job source with one posting (so another person cannot see it), one document about them and one file on their job."""
    source = JobSource.objects.create(owner=owner, name=f"{owner.username}-board", connector="greenhouse", board_token=f"{owner.username}-board")
    posting = Posting.objects.create(source=source, url=f"https://boards.example.com/{owner.username}/1", company=source.name, title="Engineer", title_key=f"{source.name}|engineer")
    note = KnowledgeSource.objects.create(owner=owner, title="Projects", kind="project", text="I built a thing.")
    kind = DocumentKind.objects.first() or DocumentKind.objects.create(name="Other")
    file = Document.objects.create(application_id=ids["job_id"], kind=kind, title="cv.pdf")
    return {"posting_id": posting.pk, "doc_id": note.pk, "file_id": file.pk}
