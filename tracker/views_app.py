"""Serves the new app: a static export built by Next.js (frontend/), with no Node process at run time.

`/app/` and every path under it answer with the same shell page, so deep links and refresh work; the page reads its own
path in the browser. The hashed files under `/app/_next/` are plain assets and carry no personal data."""
import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.utils._os import safe_join
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET

from .models import SiteConfig, UserProfile


def build_dir() -> Path:
    return Path(settings.STILLOPEN_FRONTEND_DIR)


def _asset(path: str):
    """A built asset under `_next/` or another real file in the export, never a directory or anything outside it."""
    try:
        full = Path(safe_join(build_dir(), path))
    except Exception:  # noqa: BLE001 - safe_join raises for paths that climb out of the folder
        return None
    return full if full.is_file() and full.name != "index.html" else None


@require_GET
def app_asset(request, path):
    full = _asset(path)
    if full is None:
        raise Http404("No such file.")
    response = FileResponse(open(full, "rb"), content_type=mimetypes.guess_type(full.name)[0] or "application/octet-stream")
    if path.startswith("_next/static/"):
        response["Cache-Control"] = "public, max-age=31536000, immutable"  # the file name carries a content hash
    return response


@login_required
@ensure_csrf_cookie
@require_GET
def app_shell(request, path=""):
    if not SiteConfig.load().new_app_enabled:
        return redirect("dashboard")
    if not UserProfile.for_user(request.user).use_new_app:
        return redirect("profile")  # opting in is a switch in the person's own profile
    index = build_dir() / "index.html"
    if not index.is_file():
        raise Http404("The new app has not been built on this server.")
    response = FileResponse(open(index, "rb"), content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-store"
    return response
