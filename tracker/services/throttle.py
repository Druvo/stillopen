"""A small per-person (or per-IP, for pages nobody is signed in to use) rate limit shared by the JSON API, the MCP endpoint
and the public tools.

Counters live in Django's cache: each process's own memory by default, or Redis (shared by every worker) when REDIS_URL
is set -- see config/cache_config.py. The counting is written so it stays correct on Redis with several workers.
"""
from django.core.cache import cache


def bump(key: str, window: int) -> int:
    """Add one to the counter `key` (which lives `window` seconds from its first hit) and return the new count.

    Increment first, create second: on Redis `incr` is one atomic command that keeps the key's expiry, and `add` is
    `SET NX EX`, so two workers racing to create the counter cannot overwrite each other (the loser just increments).
    The old add-then-incr order left a window in which a just-created zero could be replaced by `set(1)`."""
    try:
        return cache.incr(key)
    except ValueError:  # no such counter yet (or it just expired)
        pass
    if cache.add(key, 1, timeout=window):
        return 1
    try:
        return cache.incr(key)  # another worker created it a moment ago
    except ValueError:  # it expired between the two calls; start a fresh window
        cache.set(key, 1, timeout=window)
        return 1


def throttled(user, action: str, limit: int, window: int = 3600) -> bool:
    """True when `user` has already done `action` `limit` times within `window` seconds (shared by all workers when Redis is on)."""
    return bump(f"throttle:{action}:{user.pk}", window) > limit


def client_ip(request) -> str:
    """Honours ALLAUTH_TRUSTED_PROXY_COUNT, same as allauth's own rate limits -- put a reverse proxy count there
    first, or every visitor behind it shares one address and one limit."""
    try:
        from allauth.core.internal.httpkit import get_client_ip

        return get_client_ip(request) or "?"
    except Exception:  # noqa: BLE001 - fall back to the socket address
        return request.META.get("REMOTE_ADDR", "?")


def throttled_ip(request, action: str, limit: int, window: int = 3600) -> bool:
    """Same as `throttled`, keyed by the visitor's address -- for a page nobody needs to sign in to use."""
    return bump(f"throttle:{action}:{client_ip(request)}", window) > limit
