"""Check whether a job posting is still open."""
import re
import subprocess
import threading
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
from django.db import connections
from django.utils import timezone

from tracker.models import Application, ExpiredPhrase, LivenessRun, SiteConfig

USER_AGENT = "Mozilla/5.0 (compatible; stillopen-liveness/1.0)"
STALE_AFTER = timedelta(minutes=20)


def normalize_url(url: str) -> str:
    """bdjobs detail pages only render with ?ln=1."""
    p = urlparse(url)
    if p.hostname and p.hostname.endswith("bdjobs.com") and "/h/details/" in p.path:
        q = dict(parse_qsl(p.query))
        q.setdefault("ln", "1")
        return urlunparse(p._replace(query=urlencode(q)))
    return url


def parse_checker_output(stdout: str) -> tuple[str, str] | None:
    lines = stdout.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^\S+\s+(active|expired|uncertain)\b.*?(https?://\S+)\s*$", line)
        if m:
            detail = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if re.match(r"^(✅|❌|⚠️|❓)", detail):
                detail = ""
            return m.group(1), detail
    return None


def check_node(url: str, config: SiteConfig) -> tuple[str, str]:
    if not config.careerops_path:
        return "uncertain", "career-ops folder is not configured"
    try:
        r = subprocess.run(
            [config.node_command, "check-liveness.mjs", "--no-fallback", url],
            cwd=config.careerops_path,
            capture_output=True,
            text=True,
            timeout=config.liveness_timeout,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "uncertain", f"checker failed: {exc}"[:300]
    parsed = parse_checker_output(r.stdout)
    return parsed if parsed else ("uncertain", "checker returned no result")


def check_http(url: str, config: SiteConfig) -> tuple[str, str]:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=config.liveness_timeout, allow_redirects=True)
    except requests.RequestException as exc:
        return "uncertain", f"request failed: {exc.__class__.__name__}"
    if resp.status_code in (404, 410):
        return "expired", f"HTTP {resp.status_code}"
    if resp.status_code >= 400:
        return "uncertain", f"HTTP {resp.status_code}"
    text = resp.text.lower()
    for ph in ExpiredPhrase.objects.all():
        if ph.phrase.lower() in text:
            return "expired", f'page says "{ph.phrase}"'
    if "apply" in text:
        return "active", "page loads with an apply control"
    return "uncertain", "page loads but no apply control or expiry text found"


def check_url(url: str, config: SiteConfig) -> tuple[str, str]:
    url = normalize_url(url)
    return check_node(url, config) if config.liveness_mode == "node" else check_http(url, config)


def _targets():
    return Application.objects.filter(status__is_terminal=False).exclude(url="")


def _worker(run_id: int):
    try:
        config = SiteConfig.load()
        run = LivenessRun.objects.get(pk=run_id)
        for app in _targets():
            state, detail = check_url(app.url, config)
            Application.objects.filter(pk=app.pk).update(
                live_state=state, live_detail=detail[:300], live_checked_at=timezone.now()
            )
            run.done += 1
            run.save(update_fields=["done"])
    except Exception as exc:  # noqa: BLE001 - recorded on the run
        LivenessRun.objects.filter(pk=run_id).update(error=str(exc)[:500])
    finally:
        LivenessRun.objects.filter(pk=run_id).update(running=False, finished_at=timezone.now())
        connections.close_all()


def current_run() -> LivenessRun | None:
    run = LivenessRun.objects.first()
    if run and run.running and timezone.now() - run.started_at > STALE_AFTER:
        run.running = False
        run.error = run.error or "timed out"
        run.finished_at = timezone.now()
        run.save()
    return run


def start_run(background: bool = True) -> LivenessRun:
    existing = current_run()
    if existing and existing.running:
        return existing
    run = LivenessRun.objects.create(total=_targets().count())
    if background:
        threading.Thread(target=_worker, args=(run.pk,), daemon=True).start()
    else:
        _worker(run.pk)
        run.refresh_from_db()
    return run
