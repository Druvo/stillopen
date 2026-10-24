"""Email sending and social sign-in as the owner set them up: environment variables first, then the admin's Site configuration.

Read at the moment of use (never at start-up), so saving the admin form takes effect straight away and a restart is not needed.
Passwords and secrets are stored encrypted (`tracker.crypto`) and are never shown again, in the admin or anywhere else.
"""
import os
from dataclasses import dataclass

from django.conf import settings

PROVIDERS = ("google", "github", "facebook")


@dataclass(frozen=True)
class EmailSettings:
    host: str
    port: int
    username: str
    password: str
    use_tls: bool
    from_email: str
    source: str  # "environment" or "admin"


def _config():
    from tracker.models import SiteConfig

    return SiteConfig.load()


def email_settings():
    """How to send email, or None when nothing is set up (messages then only print to the server's console)."""
    if settings.EMAIL_CONFIGURED:
        return EmailSettings(settings.EMAIL_HOST, int(settings.EMAIL_PORT), settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD,
                             bool(settings.EMAIL_USE_TLS), settings.DEFAULT_FROM_EMAIL, "environment")
    config = _config()
    if config.email_host.strip():
        return EmailSettings(config.email_host.strip(), config.email_port or 587, config.email_username, config.email_password,
                             config.email_use_tls, from_email(config), "admin")
    return None


def from_email(config=None) -> str:
    """The sender shown on every email: the admin's address when set, else the environment's default."""
    if os.environ.get("DEFAULT_FROM_EMAIL"):
        return settings.DEFAULT_FROM_EMAIL
    config = config or _config()
    if config.email_from.strip():
        return config.email_from.strip()
    return settings.DEFAULT_FROM_EMAIL


def email_configured() -> bool:
    return email_settings() is not None


def require_email_confirmation() -> bool:
    """People who sign up themselves must click an emailed link first, but only where that email can really be sent."""
    explicit = settings.STILLOPEN_REQUIRE_EMAIL_CONFIRMATION
    if explicit is not None:
        return bool(explicit)
    return email_configured()


def social_credentials(provider: str):
    """(client id, secret) for a sign-in provider, or None if neither the environment nor the admin has both."""
    prefix = provider.upper()
    client_id, secret = os.environ.get(f"{prefix}_CLIENT_ID", "").strip(), os.environ.get(f"{prefix}_CLIENT_SECRET", "").strip()
    if client_id and secret:
        return client_id, secret
    config = _config()
    client_id, secret = getattr(config, f"{provider}_client_id").strip(), config.social_secret(provider)
    return (client_id, secret) if client_id and secret else None
