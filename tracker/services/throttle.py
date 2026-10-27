"""A small per-person (or per-IP, for pages nobody is signed in to use) rate limit shared by the JSON API,
the MCP endpoint and the public tools."""
from django.core.cache import cache


def _bump(key: str, limit: int, window: int) -> bool:
    cache.add(key, 0, timeout=window)
    try:
        return cache.incr(key) > limit
    except ValueError:
        cache.set(key, 1, timeout=window)
        return False


def throttled(user, action: str, limit: int, window: int = 3600) -> bool:
    """True when `user` has already done `action` `limit` times within `window` seconds (per server process)."""
    return _bump(f"throttle:{action}:{user.pk}", limit, window)


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
    return _bump(f"throttle:{action}:{client_ip(request)}", limit, window)
