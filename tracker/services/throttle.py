"""A small per-person rate limit shared by the JSON API and the MCP endpoint."""
from django.core.cache import cache


def throttled(user, action: str, limit: int, window: int = 3600) -> bool:
    """True when `user` has already done `action` `limit` times within `window` seconds (per server process)."""
    key = f"throttle:{action}:{user.pk}"
    cache.add(key, 0, timeout=window)
    try:
        return cache.incr(key) > limit
    except ValueError:
        cache.set(key, 1, timeout=window)
        return False
