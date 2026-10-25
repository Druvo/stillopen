"""Small request and response helpers: JSON API compression and cheap "nothing changed" answers, each person's time zone, and a reverse-proxy sanity watch."""
import logging

from django.middleware.gzip import GZipMiddleware
from django.utils.cache import patch_cache_control
from django.middleware.http import ConditionalGetMiddleware

API_PREFIX = "/api/v1/"


class ApiGZipMiddleware(GZipMiddleware):
    """Compress JSON answers of the API only.

    Pages are left alone on purpose: HTML that carries a CSRF token and compresses next to attacker-influenced text is the
    classic BREACH setup. API answers hold no token and nothing a third party can steer, and they are the big ones (a person's
    whole job list is over 100 kB of plain text and shrinks to about a tenth)."""

    def process_response(self, request, response):
        if not request.path.startswith(API_PREFIX):
            return response
        return super().process_response(request, response)


class ApiConditionalGetMiddleware(ConditionalGetMiddleware):
    """Give API GET answers an ETag and answer 304 when the browser already has exactly this body.

    The answer is still worked out (that is what makes the tag correct: it follows the real content), but an unchanged
    list costs a few hundred bytes on the wire instead of the whole thing. `private, no-cache` makes the browser ask every
    time, so a person never sees stale data, and never lets a shared cache keep it."""

    def process_response(self, request, response):
        if not request.path.startswith(API_PREFIX) or request.method != "GET" or response.status_code != 200:
            return response
        patch_cache_control(response, private=True, no_cache=True)
        return super().process_response(request, response)


# ---- per-person time zone ---------------------------------------------------------------------------------------------
TZ_CACHE_SECONDS = 600


def tz_cache_key(user_id: int) -> str:
    return f"usertz:{user_id}"


def forget_person_timezone(user_id: int) -> None:
    from django.core.cache import cache

    cache.delete(tz_cache_key(user_id))


class PersonTimezoneMiddleware:
    """Run each signed-in request in that person's own time zone (`UserProfile.timezone`; blank means the site's TIME_ZONE).

    With the zone active, `timezone.localdate()`, `localtime()`, form dates and the interview times people type all mean *their*
    clock. The zone name is remembered in the cache for ten minutes and forgotten when the profile is saved, so this costs no
    query on most requests."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.core.cache import cache
        from django.utils import timezone

        from .services import tz

        user = getattr(request, "user", None)
        zone = None
        if user is not None and user.is_authenticated:
            name = cache.get(tz_cache_key(user.pk))
            if name is None:
                name = tz._name_for(user.pk)
                cache.set(tz_cache_key(user.pk), name, TZ_CACHE_SECONDS)
            if name:
                zone = tz.zone_from_name(name)
        try:
            if zone is not None:
                timezone.activate(zone)
            else:
                timezone.deactivate()
            return self.get_response(request)
        finally:
            timezone.deactivate()


# ---- reverse-proxy sanity ---------------------------------------------------------------------------------------------
LOOPBACK = ("127.0.0.1", "::1")


def proxy_problem(request, behind_proxy: bool, trusted_count: int) -> str | None:
    """What is wrong with the reverse-proxy settings, judged from one request; None when it looks right.

    Every per-address limit (sign-up, wrong passwords, MCP tokens) needs the visitor's address. Behind a proxy that comes from the
    X-Forwarded-For header, and ALLAUTH_TRUSTED_PROXY_COUNT says how many proxies add to it. Get it wrong and every visitor shares the
    proxy's address (one person's wrong passwords then lock everyone out), or the header can be forged."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    peer = request.META.get("REMOTE_ADDR", "")
    if not behind_proxy:
        if trusted_count > 0 and forwarded:
            return "ALLAUTH_TRUSTED_PROXY_COUNT is set but DJANGO_BEHIND_PROXY is not: if nothing trusted sits in front, visitors can forge X-Forwarded-For and dodge the limits."
        return None
    if peer in LOOPBACK and not forwarded:
        return None  # the container's own health check, or a local test
    if trusted_count <= 0:
        return "DJANGO_BEHIND_PROXY=1 but ALLAUTH_TRUSTED_PROXY_COUNT is 0: every visitor looks like the proxy, so per-address limits are shared by everyone. Set ALLAUTH_TRUSTED_PROXY_COUNT=1 (one proxy in front)."
    if not forwarded:
        return "DJANGO_BEHIND_PROXY=1 but this request has no X-Forwarded-For header: the proxy is not passing the visitor's address on (proxy_set_header X-Forwarded-For $remote_addr in nginx; Caddy does it by itself)."
    if len([p for p in forwarded.split(",") if p.strip()]) < trusted_count:
        return f"ALLAUTH_TRUSTED_PROXY_COUNT={trusted_count} but X-Forwarded-For has fewer addresses than that: sign-in will fail. Lower the number to the proxies that really sit in front."
    return None


class ProxyWatchMiddleware:
    """Say so in the log (at most once an hour per problem) when the reverse-proxy settings do not match what arrives."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings

        if getattr(settings, "STILLOPEN_BEHIND_PROXY", False) or getattr(settings, "ALLAUTH_TRUSTED_PROXY_COUNT", 0):
            problem = proxy_problem(request, getattr(settings, "STILLOPEN_BEHIND_PROXY", False), getattr(settings, "ALLAUTH_TRUSTED_PROXY_COUNT", 0))
            if problem:
                from django.core.cache import cache

                if cache.add("proxy-watch:" + str(hash(problem)), 1, 3600):
                    logging.getLogger("tracker.proxy").warning(problem)
        return self.get_response(request)
