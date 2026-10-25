"""Sign-up and sign-in abuse protection that needs no third-party service.

Three pieces, all switched and tuned from the admin (Site configuration > Registration):

* `ConfiguredRateLimits`: the numbers django-allauth's rate limiter uses (wrong passwords, sign-ups, password resets,
  confirmation emails), read from the Site configuration instead of fixed in settings. Environment variables still win for
  operators who set them.
* the sign-up form's two quiet traps (a hidden box and a minimum fill time), see `tracker/forms.py`.
* `signup_token_*`: the signed "form opened at" stamp the timing check relies on.

A real CAPTCHA would load another company's script, which this app never does.
"""
from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Mapping

from django.conf import settings
from django.core import signing
from django.core.cache import cache

SIGNUP_SALT = "tracker.signup-form"
_CACHE_SECONDS = 10
_cached: tuple[float, dict] | None = None


def _config():
    from ..models import SiteConfig

    try:
        return SiteConfig.load()
    except Exception:  # noqa: BLE001 - before the first migration there is no table yet: use the defaults
        return None


def _value(config, name: str, default: int) -> int:
    return int(getattr(config, name, default)) if config is not None else default


def build_rate_limits(config=None) -> dict:
    """allauth `ACCOUNT_RATE_LIMITS` for the given (or the current) Site configuration. An env var, when set, replaces its entry verbatim."""
    config = config if config is not None else _config()
    signup = _value(config, "signup_per_hour_per_ip", 5)
    ip = _value(config, "login_failures_per_ip", 10)
    key = _value(config, "login_failures_per_account", 5)
    reset = _value(config, "password_reset_per_hour", 5)
    resend = _value(config, "email_resend_seconds", 180)
    limits = {
        "signup": f"{signup}/h/ip",
        "login_failed": f"{ip}/10m/ip,{key}/5m/key",
        "reset_password": f"{reset}/h/ip,{reset}/h/key",
        "reset_password_from_key": "20/m/ip",
        "change_password": "5/m/user",
        "confirm_email": f"1/{resend}s/key" if resend else None,
    }
    if os.environ.get("STILLOPEN_SIGNUP_RATE"):
        limits["signup"] = os.environ["STILLOPEN_SIGNUP_RATE"]
    if os.environ.get("STILLOPEN_LOGIN_RATE"):  # allauth's own cap on sign-in attempts of any kind (default 30/m/ip); the browser tests sign in far more often
        limits["login"] = os.environ["STILLOPEN_LOGIN_RATE"]
    if os.environ.get("STILLOPEN_LOGIN_FAILED_RATE"):
        limits["login_failed"] = os.environ["STILLOPEN_LOGIN_FAILED_RATE"]
    return limits


def forget_cached_limits(*_args, **_kwargs) -> None:
    """Called when the Site configuration is saved, so a new number applies at once in this process."""
    global _cached
    _cached = None


class ConfiguredRateLimits(Mapping):
    """`settings.ACCOUNT_RATE_LIMITS`, but the numbers come from the admin. allauth reads the setting on every request and only
    needs a mapping, so a change in the admin applies within seconds, in every worker, with no restart."""

    def _limits(self) -> dict:
        global _cached
        now = time.monotonic()
        if _cached is None or now - _cached[0] > _CACHE_SECONDS or getattr(settings, "RUNNING_TESTS", False):
            _cached = (now, build_rate_limits())
        return _cached[1]

    def __getitem__(self, name):
        return self._limits()[name]

    def __iter__(self):
        return iter(self._limits())

    def __len__(self):
        return len(self._limits())


# ---- the sign-up form's timing token ---------------------------------------------------------------------------------

def signup_protection_on() -> bool:
    config = _config()
    return bool(config.signup_protection) if config is not None else True


def signup_min_seconds() -> int:
    """Seconds a sign-up form must have been open. The setting STILLOPEN_SIGNUP_MIN_SECONDS (env or tests) wins; otherwise the admin's number."""
    override = getattr(settings, "STILLOPEN_SIGNUP_MIN_SECONDS", None)
    if override is not None:
        return max(0, int(override))
    return max(0, _value(_config(), "signup_min_seconds", 2))


def signup_max_age() -> int:
    """How long a sign-up page stays valid, in seconds."""
    override = getattr(settings, "STILLOPEN_SIGNUP_MAX_AGE", None)
    if override is not None:
        return int(override)
    return max(1, _value(_config(), "signup_form_max_hours", 24)) * 3600


def make_signup_token() -> str:
    return signing.dumps(time.time(), salt=SIGNUP_SALT)


def read_signup_token(token: str) -> float | None:
    """When the form was opened (epoch seconds), or None when the token is missing, forged or older than the allowed age."""
    try:
        return float(signing.loads(token or "", salt=SIGNUP_SALT, max_age=signup_max_age()))
    except (signing.BadSignature, ValueError, TypeError):
        return None


def _token_key(token: str) -> str:
    return "signup-token:" + hashlib.sha256(token.encode()).hexdigest()[:32]


def token_already_used(token: str) -> bool:
    return bool(token) and cache.get(_token_key(token)) is not None


def mark_token_used(token: str) -> None:
    """A token that produced an account cannot produce a second one (a replayed page); it expires with the page itself."""
    if token:
        cache.set(_token_key(token), 1, timeout=signup_max_age())
