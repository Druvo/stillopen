"""Serves the app: a static export built by Next.js (frontend/), with no Node process at run time.

`/app/` and every path under it answer with the same shell page, so deep links and refresh work; the page reads its own
path in the browser. The hashed files under `/app/_next/` are plain assets and carry no personal data."""
import base64
import functools
import hashlib
import mimetypes
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse
from django.utils._os import safe_join
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET


_INLINE_SCRIPT = re.compile(rb"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)


@functools.lru_cache(maxsize=4)
def _policy(path: str, mtime_ns: int) -> str:
    """A strict Content-Security-Policy for the shell page: scripts only from this site plus the exact inline bootstrap scripts the build produced.

    The export's inline scripts change with every build, so their hashes are worked out here from the file itself (cached per file version)."""
    html = Path(path).read_bytes()
    hashes = " ".join(f"'sha256-{base64.b64encode(hashlib.sha256(body).digest()).decode()}'" for body in _INLINE_SCRIPT.findall(html))
    return "; ".join([
        "default-src 'self'",
        f"script-src 'self' {hashes}".strip(),
        "style-src 'self'",
        "style-src-attr 'unsafe-inline'",  # React sets sizes on elements (progress bars, drag positions)
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])


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


_NOT_BUILT = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>The app has not been built yet</title>
<style>body{font-family:system-ui,sans-serif;max-width:40rem;margin:4rem auto;padding:0 1rem;line-height:1.5}code,pre{background:#f2f2f2;padding:.1rem .3rem;border-radius:4px}pre{padding:.75rem;overflow:auto}</style>
</head><body>
<h1>The app has not been built yet</h1>
<p>StillOpen's screens are a front end that is built once, ahead of time. This server has the back end but not the built front end, so there is nothing to show here yet.</p>
<p>If you run StillOpen yourself, build it once from the project folder (you need Node.js and pnpm):</p>
<pre>cd frontend
pnpm install
pnpm build</pre>
<p>Then reload this page. You can also skip the build by using the Docker image, which already includes it. See <code>docs/SELF-HOSTING.md</code>.</p>
</body></html>
"""


@login_required
@ensure_csrf_cookie
@require_GET
def app_shell(request, path=""):
    index = build_dir() / "index.html"
    if not index.is_file():
        return HttpResponse(_NOT_BUILT, status=503, content_type="text/html; charset=utf-8")
    response = FileResponse(open(index, "rb"), content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-store"
    if settings.STILLOPEN_APP_CSP:
        response["Content-Security-Policy"] = _policy(str(index), index.stat().st_mtime_ns)
    return response
