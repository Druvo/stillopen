"""The web MCP endpoint (/mcp/). Tokens are made and revoked in the app (Profile > Connect an AI assistant) through the JSON API.

The endpoint speaks MCP's streamable HTTP in its simple stateless form (one JSON reply per POST) so it runs under the same
WSGI server as the rest of the site. A token belongs to one person: every tool then runs as that person and nobody else
(`mcp_tools.acting_as`). Rules this follows:
  * the token is a bearer secret shown once and stored only as a hash; it can be revoked, expires, and may be read-only;
  * no cookies are ever accepted here (so no CSRF exposure), and a browser's cross-site Origin is refused;
  * the tool list is the same small one as the local server: no delete tool, no settings, keys or file contents.
"""
import json
import logging
from urllib.parse import urlparse

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import mcp_tools
from .models import ApiToken, SiteConfig

log = logging.getLogger(__name__)

MAX_BODY = 1024 * 1024
_tool_list = None


def _tools():
    """The registered tools, listed once."""
    global _tool_list
    if _tool_list is None:
        from .mcp_registry import build_server

        server = build_server()
        _tool_list = (server, async_to_sync(server.list_tools)())
    return _tool_list


def _client_ip(request) -> str:
    try:
        from allauth.core.internal.httpkit import get_client_ip

        return get_client_ip(request) or "?"
    except Exception:  # noqa: BLE001 - fall back to the socket address
        return request.META.get("REMOTE_ADDR", "?")


def _bump(key: str, window: int) -> int:
    cache.add(key, 0, timeout=window)
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window)
        return 1


def _rpc_error(request_id, code: int, message: str, status: int = 200):
    return JsonResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}, status=status)


def _deny(status: int, message: str, challenge: bool = False):
    response = JsonResponse({"error": message}, status=status)
    if challenge:
        response["WWW-Authenticate"] = 'Bearer realm="StillOpen"'
    response["Cache-Control"] = "no-store"
    return response


def _handle(message, token: ApiToken):
    """One JSON-RPC message from an authenticated client. Returns a response dict, or None for a notification."""
    from mcp_types.version import LATEST_PROTOCOL_VERSION, SUPPORTED_PROTOCOL_VERSIONS

    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request."}}
    method, request_id, params = message.get("method"), message.get("id"), message.get("params") or {}
    is_notification = "id" not in message
    if not isinstance(method, str) or not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32600, "message": "Invalid request."}}

    def ok(result):
        return None if is_notification else {"jsonrpc": "2.0", "id": request_id, "result": result}

    def err(code, text):
        return None if is_notification else {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": text}}

    server, tools = _tools()
    if method == "initialize":
        wanted = params.get("protocolVersion")
        version = wanted if wanted in SUPPORTED_PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION
        from .mcp_registry import INSTRUCTIONS

        return ok({
            "protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "stillopen", "version": "1"}, "instructions": INSTRUCTIONS,
        })
    if method == "ping":
        return ok({})
    if method.startswith("notifications/"):
        return None
    allowed = [t for t in tools if token.can_write or (t.annotations and t.annotations.read_only_hint)]
    if method == "tools/list":
        return ok({"tools": [t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in allowed]})
    if method == "tools/call":
        name, arguments = params.get("name"), params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return err(-32602, "A tool name and an arguments object are required.")
        if name not in {t.name for t in allowed}:
            known = name in {t.name for t in tools}
            return err(-32602, "This token is read-only, so it cannot use that tool." if known else f"Unknown tool: {name}")
        try:
            with mcp_tools.acting_as(token.owner):
                result = async_to_sync(server.call_tool)(name, arguments)
            return ok(result.model_dump(mode="json", by_alias=True, exclude_none=True))
        except Exception as exc:  # noqa: BLE001 - a tool error is data for the model, not a server error
            from mcp.server.mcpserver.exceptions import ToolError

            if isinstance(exc, ToolError):
                text = str(exc)
            else:
                log.exception("MCP tool %s failed", name)
                text = "That tool failed. Try again, or use the website."
            return ok({"content": [{"type": "text", "text": text}], "isError": True})
    return err(-32601, f"Method not found: {method}")


@csrf_exempt
def mcp_endpoint(request):
    config = SiteConfig.load()
    if not config.mcp_remote_enabled:
        raise Http404("Not available.")
    if request.method != "POST":
        response = HttpResponse(status=405)
        response["Allow"] = "POST"
        return response
    origin = request.headers.get("Origin")
    if origin and urlparse(origin).netloc != request.get_host():
        return _deny(403, "Cross-site requests are not allowed here.")
    ip = _client_ip(request)
    if cache.get(f"mcp-bad:{ip}", 0) >= settings.STILLOPEN_MCP_BAD_TOKENS_PER_MINUTE:
        return _deny(429, "Too many failed attempts. Try again in a minute.")
    header = request.headers.get("Authorization", "")
    raw = header[7:].strip() if header[:7].lower() == "bearer " else ""
    token = ApiToken.lookup(raw)
    if token is None:
        _bump(f"mcp-bad:{ip}", 60)
        return _deny(401, "A valid token is required. Make one under Profile > Connect an AI assistant.", challenge=True)
    if _bump(f"mcp-calls:{token.pk}", 60) > settings.STILLOPEN_MCP_CALLS_PER_MINUTE:
        return _deny(429, "Too many requests from this token. Slow down for a minute.")
    now = timezone.now()
    if token.last_used_at is None or (now - token.last_used_at).total_seconds() > 60:
        ApiToken.objects.filter(pk=token.pk).update(last_used_at=now)
    if len(request.body) > MAX_BODY:
        return _deny(413, "Request too large.")
    try:
        payload = json.loads(request.body or b"null")
    except ValueError:
        return _rpc_error(None, -32700, "Parse error.", status=400)
    incoming = payload if isinstance(payload, list) else [payload]
    if not incoming or len(incoming) > 20:
        return _rpc_error(None, -32600, "Invalid request.", status=400)
    replies = [r for r in (_handle(m, token) for m in incoming) if r is not None]
    if not replies:
        return HttpResponse(status=202)
    response = JsonResponse(replies if isinstance(payload, list) else replies[0], safe=False)
    response["Cache-Control"] = "no-store"
    return response
