"""Which version is running, and (only if an admin ticked "Check GitHub for a newer release") whether a newer one exists.

Off by default and never automatic: with the switch off no request is made at all. With it on, one plain GET of GitHub's public releases
API (a fixed address, through netguard.safe_get), at most once every six hours; the request carries nothing about any person or this install
(only the generic User-Agent every outgoing fetch uses). Any failure is silent: no notice, no error."""
import re
from pathlib import Path

from django.conf import settings
from django.core.cache import cache

from . import netguard

RELEASES_API = "https://api.github.com/repos/Druvo/stillopen/releases/latest"
RELEASE_PAGE_PREFIX = "https://github.com/Druvo/stillopen/"
CACHE_KEY = "update-check:latest"
OK_SECONDS = 6 * 60 * 60
FAIL_SECONDS = 60 * 60  # a failed try is not repeated for an hour, so a blocked network is not asked on every dashboard load
TIMEOUT = 5


def running_version() -> str:
    try:
        text = (Path(settings.BASE_DIR) / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return text if re.fullmatch(r"[0-9A-Za-z.+-]{1,30}", text) else ""


def parse(version: str) -> tuple[int, ...] | None:
    """"v1.2.3" or "1.2" as numbers, or None when it is not a plain release number (a pre-release tag is never offered)."""
    m = re.fullmatch(r"v?(\d+(?:\.\d+){0,3})", (version or "").strip())
    return tuple(int(p) for p in m.group(1).split(".")) if m else None


def is_newer(latest: str, current: str) -> bool:
    a, b = parse(latest), parse(current)
    if a is None or b is None:
        return False
    size = max(len(a), len(b))
    return a + (0,) * (size - len(a)) > b + (0,) * (size - len(b))


def _fetch() -> dict | None:
    try:
        resp = netguard.safe_get(RELEASES_API, timeout=TIMEOUT, headers={"Accept": "application/vnd.github+json"})
        if resp.status_code != 200:
            return None
        data = resp.json()
        tag, url = str(data.get("tag_name", "")), str(data.get("html_url", ""))
    except Exception:  # noqa: BLE001 - failures are silent by design
        return None
    if data.get("prerelease") or data.get("draft") or parse(tag) is None or not url.startswith(RELEASE_PAGE_PREFIX):
        return None
    return {"version": tag.lstrip("v"), "url": url}


def status(site) -> dict:
    """What the dashboard notice needs. With the check off this makes no request and touches no cache."""
    current = running_version()
    out = {"enabled": bool(site.update_check_enabled), "current": current, "available": False, "latest": "", "url": ""}
    if not out["enabled"]:
        return out
    found = cache.get(CACHE_KEY)
    if found is None:
        found = _fetch()
        cache.set(CACHE_KEY, found or {}, OK_SECONDS if found else FAIL_SECONDS)
    if found and is_newer(found["version"], current):
        out.update(available=True, latest=found["version"], url=found["url"])
    return out
