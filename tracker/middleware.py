"""Small response helpers for the JSON API: compression, and cheap "nothing changed" answers."""
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
