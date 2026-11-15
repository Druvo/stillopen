"""Sign in to the phone app through the website's own sign-in page (Google, GitHub, Facebook, Clerk, or a password).

The app never sees the person's provider password or a provider token. It opens `/auth/mobile/start/` in the phone's browser with the SHA-256 of a
secret it keeps (the "challenge"); the person signs in on the normal page; `/auth/mobile/finish/` hands the app a one-time code through the
`stillopen://auth` link; the app trades that code plus its secret (the "verifier") for a normal access token at `/auth/mobile/exchange/`.
A code that leaks (another app can see a custom link) is useless without the verifier, works once, and lives five minutes.
"""
import hashlib
import hmac
import json
import re
import secrets

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import ApiToken, SiteConfig
from .services.throttle import throttled_ip

CHALLENGE = re.compile(r"^[0-9a-f]{64}$")
SESSION_KEY = "mobile_signin_challenge"
CODE_SECONDS = 300
APP_LINK = "stillopen://auth"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@require_GET
@never_cache
def start(request):
    if throttled_ip(request, "mobile-signin-start", settings.STILLOPEN_MOBILE_LOGIN_ATTEMPTS_PER_HOUR * 3):
        return HttpResponse("Too many tries from this address. Please wait a while.", status=429)
    challenge = request.GET.get("challenge", "")
    if not CHALLENGE.match(challenge):
        return HttpResponse("This link is not valid. Open StillOpen on your phone and try again.", status=400)
    request.session[SESSION_KEY] = challenge
    return redirect("/auth/mobile/finish/" if request.user.is_authenticated else "/accounts/login/?next=/auth/mobile/finish/")


@login_required
@require_GET
@never_cache
def finish(request):
    challenge = request.session.pop(SESSION_KEY, "")
    if not CHALLENGE.match(challenge):
        return render(request, "tracker/mobile_signin_done.html", {"config": SiteConfig.load(), "link": ""}, status=400)
    code = secrets.token_urlsafe(32)
    cache.set(f"mobile-signin:{_digest(code)}", {"user": request.user.pk, "challenge": challenge}, CODE_SECONDS)
    return render(request, "tracker/mobile_signin_done.html", {"config": SiteConfig.load(), "link": f"{APP_LINK}?code={code}"})


@csrf_exempt  # called by the app with no cookie; the one-time code and the verifier are the proof
@require_POST
def exchange(request):
    if throttled_ip(request, "mobile-signin-exchange", settings.STILLOPEN_MOBILE_LOGIN_ATTEMPTS_PER_HOUR):
        return JsonResponse({"error": "Too many attempts from this address. Try again later."}, status=429)
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        body = {}
    code, verifier = (body.get("code"), body.get("verifier")) if isinstance(body, dict) else (None, None)
    if not isinstance(code, str) or not isinstance(verifier, str) or not code or not verifier:
        return JsonResponse({"error": "That sign-in could not be completed."}, status=400)
    key = f"mobile-signin:{_digest(code)}"
    record = cache.get(key)
    cache.delete(key)  # one use, whatever happens next
    if not record or not hmac.compare_digest(_digest(verifier), record["challenge"]):
        return JsonResponse({"error": "That sign-in expired or does not match. Please try again from the app."}, status=400)
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(pk=record["user"], is_active=True).first()
    if user is None:
        return JsonResponse({"error": "That sign-in could not be completed."}, status=400)
    token, raw = ApiToken.issue(user, "Mobile app", can_write=True, days=90)
    return JsonResponse({
        "token": raw,
        "expires_at": token.expires_at.isoformat() if token.expires_at else None,
        "user": {"id": user.pk, "username": user.username, "email": user.email},
    })
