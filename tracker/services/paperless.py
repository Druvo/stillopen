"""Minimal Paperless-ngx REST client and the push logic for tracker documents."""
import time
from pathlib import Path

import requests

from tracker.models import Document, SiteConfig
from tracker.services.files import resolve_document_path


class PaperlessError(Exception):
    pass


class PaperlessClient:
    def __init__(self, base_url: str, token: str, verify: bool = True, session=None, timeout: int = 30):
        if not base_url or not token:
            raise PaperlessError("Paperless URL and API token are required.")
        self.base = base_url.rstrip("/")
        self.verify = verify
        self.timeout = timeout
        self.http = session or requests.Session()
        self.http.headers.update({"Authorization": f"Token {token}", "Accept": "application/json; version=5"})

    @classmethod
    def from_config(cls, config: SiteConfig, session=None) -> "PaperlessClient":
        if not config.paperless_enabled:
            raise PaperlessError("Paperless integration is turned off in Site configuration.")
        return cls(config.effective_paperless_url, config.effective_paperless_token, config.paperless_verify_tls, session)

    def _request(self, method: str, path: str, **kw):
        try:
            r = self.http.request(method, f"{self.base}{path}", timeout=self.timeout, verify=self.verify, **kw)
        except requests.RequestException as exc:
            raise PaperlessError(f"Cannot reach Paperless: {exc.__class__.__name__}") from exc
        if r.status_code == 401 or r.status_code == 403:
            raise PaperlessError("Paperless rejected the API token.")
        if r.status_code >= 400:
            raise PaperlessError(f"Paperless returned HTTP {r.status_code}: {r.text[:200]}")
        return r

    def ping(self) -> bool:
        self._request("GET", "/api/documents/", params={"page_size": 1})
        return True

    def ensure_named(self, endpoint: str, name: str) -> int | None:
        """Return the id of a tag or document type, creating it if missing."""
        if not name:
            return None
        found = self._request("GET", f"/api/{endpoint}/", params={"name__iexact": name}).json().get("results", [])
        if found:
            return found[0]["id"]
        return self._request("POST", f"/api/{endpoint}/", json={"name": name}).json()["id"]

    def find_document(self, title: str) -> int | None:
        res = self._request("GET", "/api/documents/", params={"title__iexact": title, "page_size": 1}).json().get("results", [])
        return res[0]["id"] if res else None

    def upload(self, path: Path, title: str, tag_ids: list[int], doc_type_id: int | None) -> str:
        data = [("title", title)] + [("tags", str(t)) for t in tag_ids]
        if doc_type_id:
            data.append(("document_type", str(doc_type_id)))
        with open(path, "rb") as fh:
            r = self._request("POST", "/api/documents/post_document/", data=data, files={"document": (path.name, fh)})
        return r.json() if isinstance(r.json(), str) else str(r.json())

    def wait_for_document(self, task_id: str, timeout: int = 90, interval: float = 2.0) -> int | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            tasks = self._request("GET", "/api/tasks/", params={"task_id": task_id}).json()
            task = (tasks[0] if isinstance(tasks, list) and tasks else None) or {}
            if task.get("status") == "SUCCESS" and task.get("related_document"):
                return int(task["related_document"])
            if task.get("status") == "FAILURE":
                raise PaperlessError(f"Paperless could not process the file: {str(task.get('result'))[:200]}")
            time.sleep(interval)
        return None

    def document_url(self, doc_id: int) -> str:
        return f"{self.base}/documents/{doc_id}/details"


def push_document(doc: Document, client: PaperlessClient, config: SiteConfig, wait: bool = True) -> int | None:
    """Upload one tracker document to Paperless; stores the id (or the error) on the document."""
    path = resolve_document_path(doc, config)
    if path is None:
        doc.paperless_error = "File not found or outside the allowed folders."
        doc.save(update_fields=["paperless_error"])
        return None
    title = f"{doc.application.company} - {doc.application.role} - {doc.kind.name}"[:128]
    try:
        existing = client.find_document(title)
        if existing:
            doc.paperless_id, doc.paperless_error = existing, ""
            doc.save(update_fields=["paperless_id", "paperless_error"])
            return existing
        tag_ids = [t for t in (client.ensure_named("tags", "stillopen"), client.ensure_named("tags", doc.kind.paperless_tag)) if t]
        type_id = client.ensure_named("document_types", doc.kind.paperless_document_type)
        task_id = client.upload(path, title, tag_ids, type_id)
        doc_id = client.wait_for_document(task_id) if wait else None
        doc.paperless_id = doc_id
        doc.paperless_error = "" if doc_id or not wait else "Uploaded; Paperless is still processing it."
        doc.save(update_fields=["paperless_id", "paperless_error"])
        return doc_id
    except PaperlessError as exc:
        doc.paperless_error = str(exc)[:500]
        doc.save(update_fields=["paperless_error"])
        return None
