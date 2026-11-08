"""Bearer-token auth for native clients (Android/iOS), reusing the same `ApiToken` the web MCP endpoint uses.

A mobile client signs in once with username/email + password (`POST /api/v1/auth/login`, the one public route in
this whole API) and gets back a bearer token; every other `/api/v1/...` call then sends
`Authorization: Bearer so_...` instead of a session cookie, so the client never has to handle CSRF. The web app's
session+CSRF auth keeps working unchanged -- `api.auth` in `routes.py` tries both, in order, same as django-ninja's
usual multi-auth pattern.

A token from here is a full personal access token, same as one made under Profile > Connect an AI assistant: it
also works against `/mcp/` and shows up on, and can be revoked from, that same list. There is deliberately no
separate "mobile token" concept."""
from functools import wraps

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError
from ninja.security import HttpBearer

from ..models import ApiToken
from ..services.throttle import throttled_ip

router = Router()


def _bearer_record(request):
    header = request.headers.get("Authorization", "")
    raw = header[7:].strip() if header[:7].lower() == "bearer " else ""
    return ApiToken.lookup(raw) if raw else None


def bearer_or_login_required(view):
    """Same as `@login_required`, but a valid `Authorization: Bearer so_...` also gets in -- for the handful of
    plain Django views a mobile client must reach directly (a CV download is a file, not JSON): `views_cv.py`'s
    `cv_download`/`cv_print` so far. A bad or missing bearer token falls through to the normal session check."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        header = request.headers.get("Authorization", "")
        if header:
            record = _bearer_record(request)
            if record is None:
                return HttpResponse("A valid token is required.", status=401)
            request.user = record.owner
            return view(request, *args, **kwargs)
        return login_required(view)(request, *args, **kwargs)

    return wrapper


class BearerAuth(HttpBearer):
    def authenticate(self, request, token):
        record = ApiToken.lookup(token)
        if record is None:
            return None
        if request.method not in ("GET", "HEAD") and not record.can_write:
            return None  # a read-only token may look but never change anything
        if record.last_used_at is None or (timezone.now() - record.last_used_at).total_seconds() > 60:
            ApiToken.objects.filter(pk=record.pk).update(last_used_at=timezone.now())
        request.api_token = record
        request.user = record.owner  # every route reads request.user directly, same as the session-auth path
        return record.owner


class LoginIn(Schema):
    username: str
    password: str


@router.post("/auth/login", auth=None, summary="Sign in from a mobile app; returns a bearer token")
def mobile_login(request, data: LoginIn):
    if throttled_ip(request, "mobile-login", settings.STILLOPEN_MOBILE_LOGIN_ATTEMPTS_PER_HOUR):
        raise HttpError(429, "Too many attempts from this address. Try again later.")
    user = authenticate(request, username=data.username.strip(), password=data.password)
    if user is None or not user.is_active:
        raise HttpError(401, "Wrong username/email or password.")
    record, raw = ApiToken.issue(user, "Mobile app", can_write=True, days=90)
    return {
        "token": raw,
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        "user": {"id": user.pk, "username": user.username, "email": user.email},
    }


@router.post("/auth/logout", summary="Revoke the token this request was authenticated with")
def mobile_logout(request):
    token = getattr(request, "api_token", None)
    if token is not None:
        ApiToken.objects.filter(pk=token.pk).update(revoked_at=timezone.now())
    return {"ok": True}
