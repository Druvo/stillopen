"""Candidate knowledge base and retrieval (RAG). Everything here is scoped to one owner.

Documents about the candidate are split into passages. For each job, the most relevant passages are retrieved and
sent to the AI instead of the whole CV. Two rankers:
  - lexical: BM25 over the passages. Free, offline, nothing leaves the machine.
  - embeddings: cosine similarity over vectors from an OpenAI-compatible /embeddings endpoint (OpenAI, Ollama...).
If embeddings fail, retrieval falls back to lexical and says so.
"""
import math
import re
from collections import Counter
from pathlib import Path

import requests
from django.db.models import Q

from tracker.models import KnowledgeChunk, KnowledgeSource, SiteConfig
from tracker.services.netguard import FetchError, check_public_url
from tracker.services.text import terms

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 200_000
EMBED_BATCH = 48
QUERY_CHARS = 2500
CAREEROPS_FILES = [
    ("cv.md", "cv", "CV (career-ops cv.md)"),
    ("article-digest.md", "project", "Proof points (career-ops article-digest.md)"),
    ("modes/_profile.md", "other", "Targeting and narrative (career-ops _profile.md)"),
]


class KnowledgeError(Exception):
    pass


def _config(owner) -> SiteConfig:
    return SiteConfig.for_user(owner) if owner else SiteConfig.load()


# --- text in ------------------------------------------------------------------------------------

def extract_text(uploaded) -> str:
    """Read text from an uploaded .txt/.md/.pdf file object."""
    name = (getattr(uploaded, "name", "") or "").lower()
    if getattr(uploaded, "size", 0) > MAX_FILE_BYTES:
        raise KnowledgeError("That file is larger than 2 MB.")
    uploaded.seek(0)
    if name.endswith((".txt", ".md", ".markdown")):
        text = uploaded.read(MAX_FILE_BYTES + 1).decode("utf-8", errors="replace")
    elif name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise KnowledgeError("Reading PDFs needs pypdf: pip install pypdf") from exc
        try:
            reader = PdfReader(uploaded)
            if len(reader.pages) > 60:
                raise KnowledgeError("That PDF has more than 60 pages.")
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        except KnowledgeError:
            raise
        except Exception as exc:  # noqa: BLE001 - pypdf raises many types for damaged files
            raise KnowledgeError(f"Could not read that PDF ({exc.__class__.__name__}).") from exc
    else:
        raise KnowledgeError("Upload a .txt, .md or .pdf file.")
    text = text.replace("\x00", "").strip()
    if not text:
        raise KnowledgeError("No readable text was found in that file.")
    return text[:MAX_TEXT_CHARS]


def chunk_text(text: str, size: int = 900, overlap: int = 100) -> list[str]:
    """Split on blank lines and headings, packing paragraphs into passages of about `size` characters."""
    size = max(200, size)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, current = [], ""
    for para in paragraphs:
        while len(para) > size * 1.5:  # a very long paragraph is cut at a sentence or space near the limit
            cut = max(para.rfind(". ", 0, size), para.rfind("\n", 0, size), para.rfind(" ", 0, size))
            if cut < size // 2:
                cut = size
            if current:
                chunks.append(current)
                current = ""
            chunks.append(para[: cut + 1].strip())
            para = para[max(cut + 1 - overlap, 1) :].strip()  # always advances: cut >= size // 2 >= overlap
        if current and len(current) + len(para) + 2 > size:
            chunks.append(current)
            current = ""
        current = f"{current}\n\n{para}".strip() if current else para
    if current:
        chunks.append(current)
    return [c for c in chunks if c.strip()]


def reindex_source(source: KnowledgeSource, config: SiteConfig | None = None) -> int:
    """Rebuild the passages of one source (embeddings are computed later, on demand)."""
    config = config or _config(source.owner)
    source.chunks.all().delete()
    if not source.enabled or not source.text.strip():
        return 0
    pieces = chunk_text(source.text, config.rag_chunk_chars)
    KnowledgeChunk.objects.bulk_create(KnowledgeChunk(source=source, position=i, text=p) for i, p in enumerate(pieces))
    return len(pieces)


def _sync(owner, key: str, title: str, kind: str, text: str, config: SiteConfig) -> KnowledgeSource | None:
    """Keep an automatically managed source equal to `text` (created, updated or removed as needed)."""
    source = KnowledgeSource.objects.filter(owner=owner, key=key).first()
    if not text.strip():
        if source:
            source.delete()
        return None
    if source is None:
        source = KnowledgeSource.objects.create(owner=owner, key=key, title=title, kind=kind, text=text)
        reindex_source(source, config)
    elif source.text != text:
        source.text = text
        source.save()
        reindex_source(source, config)
    return source


def sync_cv(config: SiteConfig, owner) -> None:
    """The pasted CV (or, for admins with a career-ops folder, its cv.md) is always part of the knowledge base."""
    _sync(owner, "profile-cv", "CV (from your profile)", "cv", config.profile_cv, config)
    fallback = "" if config.profile_cv.strip() else _read(config, "cv.md")
    _sync(owner, "careerops:cv.md", CAREEROPS_FILES[0][2], "cv", fallback, config)


def _read(config: SiteConfig, rel: str) -> str:
    if not config.careerops_path:
        return ""
    path = Path(config.careerops_path) / rel
    try:
        return path.read_text(encoding="utf-8")[:MAX_TEXT_CHARS] if path.is_file() else ""
    except OSError:
        return ""


def import_careerops(config: SiteConfig, owner) -> list[str]:
    """Add or refresh sources from career-ops' user-authored files. Returns the titles imported."""
    done = []
    for rel, kind, title in CAREEROPS_FILES:
        text = _read(config, rel)
        if text.strip():
            _sync(owner, f"careerops:{rel}", title, kind, text, config)
            done.append(title)
    return done


# --- retrieval ----------------------------------------------------------------------------------

def _active_chunks(owner) -> list[KnowledgeChunk]:
    return list(KnowledgeChunk.objects.filter(source__owner=owner, source__enabled=True).select_related("source"))


def bm25_rank(query: str, chunks: list[KnowledgeChunk], k1: float = 1.5, b: float = 0.75) -> list[tuple[float, KnowledgeChunk]]:
    docs = [terms(c.text) for c in chunks]
    if not docs:
        return []
    avg = sum(len(d) for d in docs) / len(docs) or 1
    df = Counter(t for d in docs for t in set(d))
    n = len(docs)
    query_terms = set(terms(query))
    scored = []
    for chunk, doc in zip(chunks, docs):
        tf = Counter(doc)
        score = 0.0
        for t in query_terms:
            if t in tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(doc) / avg))
        scored.append((score, chunk))
    return sorted(scored, key=lambda s: -s[0])


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def embed_texts(texts: list[str], config: SiteConfig) -> list[list[float]]:
    base = (config.rag_embedding_base_url or config.ai_base_url or "https://api.openai.com/v1").rstrip("/")
    if not config.rag_embedding_model:
        raise KnowledgeError("Set the embedding model in your profile.")
    if getattr(config, "restricted", False):  # shared server: never call private or internal addresses
        try:
            check_public_url(base)
        except FetchError as exc:
            raise KnowledgeError(str(exc)) from exc
    key = config.effective_rag_key
    local = "127.0.0.1" in base or "localhost" in base
    if not key and not local:
        raise KnowledgeError("Add an API key for the embeddings service.")
    headers = {"content-type": "application/json"}
    if key:
        headers["authorization"] = f"Bearer {key}"
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start : start + EMBED_BATCH]
        try:
            r = requests.post(
                f"{base}/embeddings",
                headers=headers,
                json={"model": config.rag_embedding_model, "input": batch},
                timeout=config.ai_timeout,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise KnowledgeError(f"Cannot reach the embeddings API: {exc.__class__.__name__}") from exc
        if r.status_code >= 400:
            raise KnowledgeError(f"The embeddings API returned HTTP {r.status_code}.")
        try:
            data = sorted(r.json()["data"], key=lambda d: d.get("index", 0))
            vectors += [d["embedding"] for d in data]
        except (KeyError, ValueError, TypeError) as exc:
            raise KnowledgeError("The embeddings reply had an unexpected shape.") from exc
        if len(vectors) != start + len(batch):
            raise KnowledgeError("The embeddings API returned the wrong number of vectors.")
    return vectors


def embed_pending(config: SiteConfig, owner) -> int:
    """Compute vectors for this owner's passages that have none (or were made with another model)."""
    todo = [c for c in _active_chunks(owner) if not c.embedding or c.embedding_model != config.rag_embedding_model]
    if not todo:
        return 0
    for chunk, vector in zip(todo, embed_texts([c.text for c in todo], config)):
        chunk.embedding, chunk.embedding_model = vector, config.rag_embedding_model
        chunk.save(update_fields=["embedding", "embedding_model"])
    return len(todo)


def retrieve(query: str, config: SiteConfig, owner, k: int | None = None) -> tuple[list[KnowledgeChunk], dict]:
    """Most relevant passages of one owner's knowledge for `query`; info says how they were ranked and why a fallback happened."""
    sync_cv(config, owner)
    chunks = _active_chunks(owner)
    k = k or config.rag_top_k
    info = {"mode": config.rag_mode, "candidates": len(chunks), "fallback": ""}
    if not chunks:
        return [], info
    if config.rag_mode == "embeddings":
        try:
            embed_pending(config, owner)
            fresh = _active_chunks(owner)
            qvec = embed_texts([query[:QUERY_CHARS]], config)[0]
            ranked = sorted(((_cosine(qvec, c.embedding), c) for c in fresh if c.embedding), key=lambda s: -s[0])
            return [c for _, c in ranked[:k]], info
        except KnowledgeError as exc:
            info.update(mode="lexical", fallback=str(exc))
    ranked = bm25_rank(query, chunks)
    hits = [c for score, c in ranked[:k] if score > 0] or [c for _, c in ranked[:k]]
    return hits, info


def all_candidate_text(config: SiteConfig, owner) -> str:
    """Everything this candidate has written down, for the free keyword match."""
    sync_cv(config, owner)
    # key is NULL for hand-added sources, and NOT IN would drop NULL rows, so test for them explicitly.
    synced_cv = Q(key__in=["profile-cv", "careerops:cv.md"])
    parts = [config.effective_profile_cv] + list(
        KnowledgeSource.objects.filter(owner=owner, enabled=True).exclude(synced_cv).values_list("text", flat=True)
    )
    return "\n\n".join(p for p in parts if p)
