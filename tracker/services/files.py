"""Safe resolution of document files on disk."""
from pathlib import Path

from django.conf import settings


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_document_path(doc, config) -> Path | None:
    """Return the file for a Document, or None if missing or outside the allowed folders."""
    if doc.file:
        try:
            p = Path(doc.file.path).resolve()
        except (ValueError, NotImplementedError):
            return None
        return p if p.is_file() else None

    if not doc.source_path:
        return None
    p = Path(doc.source_path).resolve()
    allowed = [Path(settings.MEDIA_ROOT).resolve()]
    if config.careerops_path:
        allowed.append(Path(config.careerops_path).resolve())
    if not any(_inside(p, a) for a in allowed):
        return None
    return p if p.is_file() else None
