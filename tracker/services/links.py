"""Addresses for the emails: a link back into the app, built from what the site owner has set up.

Order of trust: the admin's `SiteConfig.public_base_url` (https only), then the current `django.contrib.sites` domain (https unless DEBUG,
and never the untouched `example.com` that Django ships with), then nothing. With nothing, `app_url` returns "" and `link_line` says in
words where to go in the app, so an email never carries a broken or half-made link."""
from django.conf import settings

APP_PREFIX = "/app"
PLACEHOLDER_DOMAINS = {"example.com", "www.example.com", ""}
CHANGE_LINE = "To change which emails you get, open Profile > Emails in the app."


def base_url() -> str:
    """The site's public address without a trailing slash, or "" when nobody has said what it is."""
    from tracker.models import SiteConfig

    configured = (SiteConfig.load().public_base_url or "").strip().rstrip("/")
    if configured.lower().startswith("https://"):
        return configured
    try:
        from django.contrib.sites.models import Site

        domain = Site.objects.get_current().domain.strip().strip("/").lower()
    except Exception:  # no sites table yet, or no row: fall through to "no link"
        return ""
    if domain in PLACEHOLDER_DOMAINS or " " in domain or "/" in domain:
        return ""
    return f"{'http' if settings.DEBUG else 'https'}://{domain}"


def app_url(path: str = "/") -> str:
    """The full address of a screen of the app (`/` is the dashboard, `/jobs/5/apply` a job's apply screen), or "" without a known base."""
    base = base_url()
    if not base:
        return ""
    path = "/" + (path or "").lstrip("/")
    return f"{base}{APP_PREFIX}{path}" if path != "/" else f"{base}{APP_PREFIX}/"


def link_line(label: str, path: str, where: str) -> str:
    """`label: <link>` when the address is known, else a plain sentence naming where to go (`where`, e.g. "your dashboard")."""
    url = app_url(path)
    return f"{label}: {url}" if url else f"{label}: open StillOpen and go to {where}."


def job_link(job_id: int, screen: str = "apply") -> str:
    """The address of one job's screen, or "" (callers then print no link for that job)."""
    return app_url(f"/jobs/{job_id}/{screen}")


def verified_address(owner) -> bool:
    """True when this person's current email address is one they have confirmed. Nothing is ever sent to any other."""
    from allauth.account.models import EmailAddress

    return bool(owner.email) and EmailAddress.objects.filter(user=owner, email=owner.email, verified=True).exists()
