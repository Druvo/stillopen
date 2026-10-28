"""The opt-in Google connection: OAuth (authorization code + PKCE), stored tokens, and the one HTTP door to Google.

A person connects their OWN Google account so the app can, when they press a button, send an application from their Gmail,
read the replies in that one conversation, and keep their Calendar in step. Rules that must hold:

- the connection is a separate incremental-scope client (SiteConfig.google_connect_*), never the sign-in client;
- the OAuth `state` is random, bound to the session and single use; the PKCE verifier never leaves the session;
- tokens are encrypted at rest (crypto.py), never returned by any API, never logged, never put in an error message;
- Google is only ever called on its fixed hosts, with no redirects followed and a timeout;
- nothing in this module sends mail: sending lives in `gmail.send_message`, which only the confirm endpoint calls.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import logging
import secrets
from urllib.parse import urlencode, urlparse

import requests
from django.utils import timezone

from tracker.models import GoogleConnection, SiteConfig
from tracker.services import links

log = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
ALLOWED_HOSTS = {"accounts.google.com", "oauth2.googleapis.com", "gmail.googleapis.com", "www.googleapis.com"}

SCOPE_SEND = "https://www.googleapis.com/auth/gmail.send"
SCOPE_READ = "https://www.googleapis.com/auth/gmail.readonly"
SCOPE_EVENTS = "https://www.googleapis.com/auth/calendar.events"
SCOPE_BUSY = "https://www.googleapis.com/auth/calendar.freebusy"
SCOPES = [SCOPE_SEND, SCOPE_READ, SCOPE_EVENTS, SCOPE_BUSY]

SESSION_KEY = "google_oauth_pending"
PENDING_SECONDS = 600
TIMEOUT = 20
CALLBACK_PATH = "/google/callback/"


class GoogleError(Exception):
    """Always carries a message that is safe to show to the person (no tokens, no raw Google payloads)."""

    def __init__(self, message: str, reconnect: bool = False, status: int = 0):
        super().__init__(message)
        self.reconnect = reconnect
        self.status = status


def client_credentials() -> tuple[str, str] | None:
    return SiteConfig.load().effective_google_connect


def available() -> bool:
    return client_credentials() is not None


def redirect_uri(request) -> str:
    base = links.base_url()
    return f"{base}{CALLBACK_PATH}" if base else request.build_absolute_uri(CALLBACK_PATH)


# --- the one door to Google -------------------------------------------------------------------------

def _plain_error(response) -> str:
    code = response.status_code
    if code in (401, 403):
        return "Google refused the request. Reconnect your Google account on the Account page and try again."
    if code == 404:
        return "Google could not find that."
    if code == 429:
        return "Google says there have been too many requests. Wait a little and try again."
    if code >= 500:
        return "Google is having a problem right now. Try again in a few minutes."
    return "Google could not do that. Check what you entered and try again."


def http(method: str, url: str, *, token: str | None = None, **kwargs) -> requests.Response:
    """A request to one of Google's own hosts. Anything else is refused; redirects are never followed; failures become GoogleError."""
    parts = urlparse(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
        raise GoogleError("That address is not one of Google's.")
    headers = dict(kwargs.pop("headers", {}) or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        return requests.request(method, url, headers=headers, timeout=TIMEOUT, allow_redirects=False, **kwargs)
    except requests.RequestException:
        raise GoogleError("Could not reach Google. Check your connection and try again.") from None


def api(connection: GoogleConnection, method: str, url: str, ok: tuple = (200, 204), **kwargs) -> dict:
    """An authorised call: a fresh access token, JSON back, and a plain-words GoogleError on any trouble."""
    token = access_token(connection)
    response = http(method, url, token=token, **kwargs)
    if response.status_code == 401:  # the stored token went stale early: renew once and retry
        token = access_token(connection, force=True)
        response = http(method, url, token=token, **kwargs)
    if response.status_code not in ok:
        raise GoogleError(_plain_error(response), reconnect=response.status_code in (401, 403), status=response.status_code)
    if response.status_code == 204 or not response.content:
        return {}
    try:
        data = response.json()
    except ValueError:
        raise GoogleError("Google sent something we could not read. Try again.") from None
    return data if isinstance(data, dict) else {}


# --- connect / callback -------------------------------------------------------------------------------

def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def begin(request) -> str:
    """Start the connect flow: remember a random state and PKCE verifier in the session and return the Google address to send the person to."""
    creds = client_credentials()
    if not creds:
        raise GoogleError("The Google connection is not set up on this site. Ask the site's admin.")
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    uri = redirect_uri(request)
    request.session[SESSION_KEY] = {"state": state, "verifier": verifier, "redirect": uri, "at": timezone.now().timestamp()}
    query = urlencode({
        "client_id": creds[0], "redirect_uri": uri, "response_type": "code", "scope": " ".join(SCOPES), "state": state,
        "code_challenge": _challenge(verifier), "code_challenge_method": "S256",
        "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true",
    })
    return f"{AUTH_URL}?{query}"


def _expiry(data: dict) -> dt.datetime:
    return timezone.now() + dt.timedelta(seconds=max(60, int(data.get("expires_in") or 3600)) - 60)


def finish(request, state: str, code: str) -> GoogleConnection:
    """Complete the connect flow. The state must be the one this session was given (compared in constant time, single use, fresh)."""
    pending = request.session.pop(SESSION_KEY, None)
    if not pending or not state or not hmac.compare_digest(str(pending.get("state", "")), str(state)):
        raise GoogleError("That sign-in did not start here, so it was ignored. Press Connect again.")
    if timezone.now().timestamp() - float(pending.get("at", 0)) > PENDING_SECONDS:
        raise GoogleError("That took too long. Press Connect again.")
    creds = client_credentials()
    if not creds or not code:
        raise GoogleError("The Google connection could not be finished. Press Connect again.")
    response = http("POST", TOKEN_URL, data={
        "grant_type": "authorization_code", "code": code, "client_id": creds[0], "client_secret": creds[1],
        "redirect_uri": pending["redirect"], "code_verifier": pending["verifier"],
    })
    if response.status_code != 200:
        raise GoogleError("Google would not finish the connection. Press Connect again.")
    try:
        data = response.json()
    except ValueError:
        raise GoogleError("Google sent something we could not read. Press Connect again.") from None
    granted = str(data.get("scope", "")).split()
    missing = [s for s in SCOPES if s not in granted]
    if missing or not data.get("access_token"):
        raise GoogleError("Not everything was allowed on Google's screen. Press Connect again and leave all the boxes ticked.")
    owner = request.user
    connection = GoogleConnection.objects.filter(owner=owner).first() or GoogleConnection(owner=owner)
    refresh = data.get("refresh_token") or (connection.refresh_token if connection.pk else "")
    if not refresh:
        raise GoogleError("Google did not give a lasting permission. Remove StillOpen under your Google account's third-party access, then connect again.")
    connection.set_tokens(data["access_token"], _expiry(data), refresh)
    connection.scopes = granted
    connection.connected_at = timezone.now()
    connection.last_error = ""
    connection.save()
    try:  # which account it is, so the person can see it: the Gmail profile needs no extra permission
        profile = api(connection, "GET", "https://gmail.googleapis.com/gmail/v1/users/me/profile")
        connection.email = str(profile.get("emailAddress", ""))[:254]
        connection.save(update_fields=["email"])
    except GoogleError:
        pass
    return connection


# --- tokens -----------------------------------------------------------------------------------------

def access_token(connection: GoogleConnection, force: bool = False) -> str:
    """A usable access token, renewed when it has expired. A refusal from Google means the person must reconnect."""
    if not force and connection.access_expires_at and connection.access_expires_at > timezone.now() and connection.access_token:
        return connection.access_token
    creds = client_credentials()
    refresh = connection.refresh_token
    if not creds or not refresh:
        raise GoogleError("Your Google connection needs to be set up again. Reconnect it on the Account page.", reconnect=True)
    response = http("POST", TOKEN_URL, data={
        "grant_type": "refresh_token", "refresh_token": refresh, "client_id": creds[0], "client_secret": creds[1],
    })
    if response.status_code != 200:
        gone = response.status_code in (400, 401)
        message = ("Google no longer lets this app in. Reconnect your Google account on the Account page." if gone
                   else "Could not renew the Google connection just now. Try again in a few minutes.")
        connection.last_error = message[:300]
        connection.save(update_fields=["last_error"])
        raise GoogleError(message, reconnect=gone)
    try:
        data = response.json()
        token = data["access_token"]
    except (ValueError, KeyError):
        raise GoogleError("Google sent something we could not read. Try again.") from None
    connection.set_tokens(token, _expiry(data))
    connection.last_error = ""
    connection.save(update_fields=["access_token_encrypted", "access_expires_at", "last_error"])
    return token


def disconnect(owner) -> bool:
    """Revoke the person's permission at Google (best effort) and delete every stored token. Returns True if anything was connected."""
    connection = GoogleConnection.objects.filter(owner=owner).first()
    if connection is None:
        return False
    token = connection.refresh_token or connection.access_token
    if token:
        try:
            http("POST", REVOKE_URL, data={"token": token})
        except GoogleError:
            log.info("Google revoke could not be reached for user %s", owner.pk)  # the tokens are deleted below either way
    connection.delete()
    return True


def for_user(owner) -> GoogleConnection | None:
    return GoogleConnection.objects.filter(owner=owner).first()


def require(owner, scope: str | None = None) -> GoogleConnection:
    connection = for_user(owner)
    if connection is None:
        raise GoogleError("Connect your Google account first (Account > Connections).")
    if scope and scope not in (connection.scopes or []):
        raise GoogleError("This permission was not given. Reconnect your Google account and leave all the boxes ticked.", reconnect=True)
    return connection
