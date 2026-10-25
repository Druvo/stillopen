"""Documents about the person (projects, certificates, writing samples) for the new app.

Same rules as the classic Documents page: only the extracted text of an upload is kept and never the file, a limit on how many, and every
document is the person's own. Pushing a job's file to Paperless is for site admins only. Downloads of job files stay on `/document/<id>/`."""
import json

from django.conf import settings
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError

from .. import forms
from ..models import Document, KnowledgeSource, SiteConfig
from ..services import knowledge, tracking
from ..services.paperless import PaperlessClient, PaperlessError, push_document
from .common import ApiFormError, owned, validate_form

router = Router()

HIDDEN_KEYS = ["profile-cv", "careerops:cv.md"]  # the CV lives on the profile, not in this list


def _source(s: KnowledgeSource) -> dict:
    return {
        "id": s.pk, "title": s.title, "kind": s.kind, "kind_label": s.get_kind_display(), "enabled": s.enabled,
        "characters": len(s.text), "passages": len(s.chunks.all()), "updated": s.updated_at.date().isoformat(),
    }


@router.get("/documents", summary="The documents about the person that the AI may use, with the limits")
def list_documents(request):
    owned_sources = KnowledgeSource.objects.filter(owner=request.user)
    visible = owned_sources.exclude(key__in=HIDDEN_KEYS).prefetch_related("chunks")
    cv = owned_sources.filter(key__in=HIDDEN_KEYS).exclude(text="").first()
    return {
        "sources": [_source(s) for s in visible],
        "cv": {"present": cv is not None, "characters": len(cv.text) if cv else 0},
        "limits": {"max_documents": settings.STILLOPEN_MAX_KNOWLEDGE, "max_file_bytes": knowledge.MAX_FILE_BYTES, "max_text_characters": knowledge.MAX_TEXT_CHARS},
        "kinds": [{"value": v, "label": label} for v, label in KnowledgeSource.KINDS],
        "can_push_to_paperless": bool(request.user.is_staff),
    }


def _fields(request) -> tuple[dict, dict]:
    """The form's text fields and the upload, from a multipart post (a file) or a JSON body (text only)."""
    if (request.content_type or "").startswith("multipart/"):
        return {k: request.POST.get(k, "") for k in ("title", "kind", "text")}, request.FILES
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        raise HttpError(400, "Please check what you entered.")
    if not isinstance(body, dict):
        raise HttpError(400, "Please check what you entered.")
    return {k: "" if body.get(k) is None else str(body[k]) for k in ("title", "kind", "text")}, {}


@router.post("/documents", summary="Add a document: pasted text, or an uploaded .txt, .md or .pdf (up to 2 MB)")
def add_document(request):
    data, files = _fields(request)
    data.setdefault("kind", "other")
    if not data["kind"]:
        data["kind"] = "other"
    if KnowledgeSource.objects.filter(owner=request.user).count() >= settings.STILLOPEN_MAX_KNOWLEDGE:
        raise ApiFormError({}, tracking.knowledge_limit_message())
    form = forms.KnowledgeForm(data, files)
    validate_form(form)
    source = tracking.add_document(request.user, form, SiteConfig.for_user(request.user))
    source = KnowledgeSource.objects.prefetch_related("chunks").get(pk=source.pk)
    return _source(source)


@router.post("/documents/{doc_id}/toggle", summary="Hide a document from the AI, or use it again")
def toggle_document(request, doc_id: int):
    source = owned(KnowledgeSource, request, doc_id)
    tracking.toggle_document(source, SiteConfig.for_user(request.user))
    return {"ok": True, "enabled": source.enabled}


@router.delete("/documents/{doc_id}", summary="Delete a document")
def delete_document(request, doc_id: int):
    owned(KnowledgeSource, request, doc_id).delete()
    return {"ok": True}


@router.post("/documents/files/{file_id}/paperless", summary="Send a job's file to Paperless (site admins only)")
def push_to_paperless(request, file_id: int):
    doc = get_object_or_404(Document.objects.select_related("application", "kind"), pk=file_id, application__owner=request.user)
    if not request.user.is_staff:
        raise HttpError(403, "Only site admins can do that.")
    config = SiteConfig.for_user(request.user)
    try:
        client = PaperlessClient.from_config(config)
    except PaperlessError as exc:
        raise HttpError(400, str(exc))
    paperless_id = push_document(doc, client, config)
    doc.refresh_from_db()
    return {
        "ok": bool(paperless_id), "paperless_id": doc.paperless_id, "error": doc.paperless_error,
        "url": client.document_url(doc.paperless_id) if doc.paperless_id else "",
    }
