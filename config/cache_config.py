"""Which cache Django uses, decided from the environment (a pure function, so it can be tested without Redis).

Per-person rate limits, the public-board refresh lock and the search source cache all live in Django's cache. The
default is each process's own memory, which is exactly right for one gunicorn worker and wrong for several (every
worker would count on its own). Setting REDIS_URL switches to Django's built-in Redis backend, which all workers share.
"""
from collections.abc import Mapping

LOCAL_MEMORY = "django.core.cache.backends.locmem.LocMemCache"
REDIS = "django.core.cache.backends.redis.RedisCache"


def build_caches(env: Mapping[str, str]) -> dict:
    """The CACHES setting for this environment: Redis when REDIS_URL is set, otherwise unchanged (local memory)."""
    url = (env.get("REDIS_URL") or "").strip()
    if not url:
        return {"default": {"BACKEND": LOCAL_MEMORY}}
    return {
        "default": {
            "BACKEND": REDIS,
            "LOCATION": url,
            "KEY_PREFIX": (env.get("STILLOPEN_CACHE_PREFIX") or "stillopen").strip() or "stillopen",
            "OPTIONS": {"socket_connect_timeout": 2, "socket_timeout": 2},
        }
    }
