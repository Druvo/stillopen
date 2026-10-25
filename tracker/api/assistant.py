"""Assistant tokens for the new app. The raw token comes back exactly once, from the create call (never stored readable, never listed);
the list shows only the first characters. Same rules as `views_mcp.py`: switched off by the admin means 404, a token is revoked rather than deleted."""
from django.conf import settings
from django.http import Http404, JsonResponse
from ninja import Router
from ninja.errors import HttpError

from ..models import ApiToken, SiteConfig
from ..services import assistant as tokens
from ..views import throttled
from .account import read_payload
from .common import owned

router = Router()


def _enabled() -> SiteConfig:
    config = SiteConfig.load()
    if not config.mcp_remote_enabled:
        raise Http404("Not available.")
    return config


def _token(token: ApiToken) -> dict:
    return {
        "id": token.pk, "name": token.name, "hint": token.hint, "can_write": token.can_write, "state": token.state,
        "created_at": token.created_at.isoformat(), "last_used_at": token.last_used_at.isoformat() if token.last_used_at else None,
        "expires_at": token.expires_at.isoformat() if token.expires_at else None, "revoked": token.revoked_at is not None,
    }


def _endpoint(request) -> str:
    return request.build_absolute_uri("/mcp/")


@router.get("/assistant", summary="The person's assistant tokens (never the token itself)")
def list_tokens(request):
    _enabled()
    return {
        "tokens": [_token(t) for t in request.user.api_tokens.all()], "endpoint": _endpoint(request), "limit": settings.STILLOPEN_MAX_API_TOKENS,
        "expiry_choices": [{"days": days, "label": label} for days, label in ApiToken.EXPIRY_CHOICES], "active": tokens.active_count(request.user),
    }


@router.post("/assistant/tokens", summary="Make a token; the raw token is in this reply only")
def create_token(request):
    _enabled()
    data, _ = read_payload(request)
    try:
        tokens.check_room(request.user)
    except tokens.TokenRefused as refused:
        raise HttpError(refused.status, str(refused)) from None
    if throttled(request.user, "token", settings.STILLOPEN_TOKEN_ISSUES_PER_HOUR):
        raise HttpError(429, "You have made a lot of tokens in the last hour. Try again later.")
    record, raw = ApiToken.issue(request.user, str(data.get("name", "")), can_write=data.get("access") == "write", days=tokens.parse_days(data.get("expires", 90)))
    response = JsonResponse({"token": raw, "record": _token(record), "endpoint": _endpoint(request)}, status=200)
    response["Cache-Control"] = "no-store"  # shown here once and kept nowhere readable
    return response


@router.post("/assistant/tokens/{token_id}/revoke", summary="Revoke a token; it stops working straight away")
def revoke_token(request, token_id: int):
    _enabled()
    token = owned(ApiToken, request, token_id)
    tokens.revoke(token)
    return {"token": _token(token)}
