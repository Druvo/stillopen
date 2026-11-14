"""Sign-in and sign-up pages that hand over to Clerk when it is turned on, and the one call that trades Clerk's session token for a Django session.

With Clerk off (no keys) these pages are exactly the built-in allauth ones. The admin site keeps its own password login."""
import json

from allauth.account import views as allauth_views
from django.contrib.auth import login, logout
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .models import UserProfile
from .services import clerkauth, throttle
from .services.clerkauth import ClerkError

# Pinned, at least two weeks old; the script comes from the person's own Clerk address.
CLERK_JS = "@clerk/clerk-js@6.40.1/dist/clerk.browser.js"
EXCHANGES_PER_HOUR = 60


def _safe_next(request, value) -> str:
    if isinstance(value, str) and value and url_has_allowed_host_and_scheme(value, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return value
    return ""


def _page(request, signup: bool):
    configured = clerkauth.keys()
    if configured is None:
        return (allauth_views.signup if signup else allauth_views.login)(request)
    if request.user.is_authenticated:
        return redirect("/app/")
    try:
        host = clerkauth.frontend_host(configured[0])
    except ClerkError as exc:
        return render(request, "account/clerk.html", {"signup": signup, "error": str(exc)}, status=503)
    return render(request, "account/clerk.html", {
        "signup": signup, "publishable_key": configured[0], "script_url": f"https://{host}/npm/{CLERK_JS}",
        "next": _safe_next(request, request.GET.get("next", "")), "signed_out": request.GET.get("signed_out") == "1",
    })


@ensure_csrf_cookie
def login_page(request):
    return _page(request, signup=False)


@ensure_csrf_cookie
def signup_page(request):
    return _page(request, signup=True)


@require_POST
def clerk_session(request):
    if throttle.throttled_ip(request, "clerk-exchange", EXCHANGES_PER_HOUR):
        return JsonResponse({"error": "Too many tries. Please wait a while and try again."}, status=429)
    if not clerkauth.enabled():
        return JsonResponse({"error": "Clerk sign-in is not turned on."}, status=404)
    try:
        body = json.loads(request.body or b"{}")
        if not isinstance(body, dict):
            body = {}
        token = body.get("token")
        if not isinstance(token, str) or not token:
            raise ClerkError("That sign-in could not be checked. Please try again.")
        claims = clerkauth.verify_token(token, request.headers.get("Origin", ""))
        user, _ = clerkauth.sign_in_user(claims["sub"], clerkauth.fetch_person(claims["sub"]))
    except json.JSONDecodeError:
        return JsonResponse({"error": "That sign-in could not be checked. Please try again."}, status=400)
    except ClerkError as exc:
        return JsonResponse({"error": str(exc)}, status=403)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    profile = UserProfile.objects.filter(user=user).first()
    wanted = _safe_next(request, body.get("next", ""))
    return JsonResponse({"next": wanted or ("/app/welcome" if profile and not profile.onboarding_done else "/app/")})


def logout_view(request):
    """With Clerk on, sign out here and send the person to a sign-in page that also ends their Clerk session, so it does not sign them straight back in."""
    if not clerkauth.enabled():
        return allauth_views.logout(request)
    if request.method == "POST":
        logout(request)
        return redirect("/accounts/login/?signed_out=1")
    return redirect("/accounts/login/")
