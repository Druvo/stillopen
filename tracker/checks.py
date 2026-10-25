"""`manage.py check` warnings for deployment settings that quietly weaken the per-person and per-address limits."""
import os

from django.conf import settings
from django.core.checks import Warning, register


@register()
def deployment_settings(app_configs, **kwargs):
    problems = []
    behind = getattr(settings, "STILLOPEN_BEHIND_PROXY", False)
    trusted = getattr(settings, "ALLAUTH_TRUSTED_PROXY_COUNT", 0)
    if behind and trusted <= 0:
        problems.append(Warning(
            "DJANGO_BEHIND_PROXY=1 but ALLAUTH_TRUSTED_PROXY_COUNT is 0.",
            hint="Every visitor will look like the proxy, so the sign-up and wrong-password limits are shared by everyone. Set ALLAUTH_TRUSTED_PROXY_COUNT=1 (one proxy in front).",
            id="stillopen.W001",
        ))
    if trusted > 0 and not behind:
        problems.append(Warning(
            "ALLAUTH_TRUSTED_PROXY_COUNT is set but DJANGO_BEHIND_PROXY is not.",
            hint="If no proxy really sits in front, visitors can forge X-Forwarded-For and get around the per-address limits. Set both or neither.",
            id="stillopen.W002",
        ))
    workers = int(os.environ.get("STILLOPEN_WORKERS") or os.environ.get("WEB_CONCURRENCY") or "1")
    backend = settings.CACHES["default"]["BACKEND"]
    if workers > 1 and "locmem" in backend.lower():
        problems.append(Warning(
            f"{workers} workers are configured but the cache is per-process memory.",
            hint="Each worker would count rate limits on its own, so every limit is effectively multiplied by the number of workers. Set REDIS_URL (see docker-compose.redis.yml) or use one worker.",
            id="stillopen.W003",
        ))
    return problems
