"""Sign-in through Clerk (clerk.com): the one place that talks to it.

The browser signs in with Clerk's own forms and hands us Clerk's short-lived session token. We check its signature against the
public keys of the person's Clerk address (the host is read out of the publishable key, never from the request), ask Clerk's
server for the person's email and whether Clerk verified it, and only then sign them in here with the usual Django session.
Everything after that (the API, the admin-set limits, per-person isolation) is unchanged. Secrets never leave this module's callers.
"""
import base64
import re
import threading
import time

import jwt
import requests
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from ..models import SiteConfig, UserProfile

API = "https://api.clerk.com/v1"
TIMEOUT = 8
_HOST = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$")
_KEYS_TTL = 3600
_lock = threading.Lock()
_keys: dict[str, tuple[float, dict]] = {}


class ClerkError(Exception):
    """The token or the person could not be accepted; the message is safe to show."""


def keys():
    return SiteConfig.load().effective_clerk


def enabled() -> bool:
    return keys() is not None


def frontend_host(publishable: str) -> str:
    """`pk_test_<base64 of "host$">` -> host. Raises ClerkError for anything that is not a Clerk publishable key."""
    try:
        encoded = publishable.split("_", 2)[2]
        host = base64.b64decode(encoded + "=" * (-len(encoded) % 4)).decode("ascii").rstrip("$")
    except Exception as exc:  # noqa: BLE001 - any malformed key is the same answer
        raise ClerkError("The Clerk publishable key is not valid.") from exc
    if not _HOST.match(host) or "." not in host:
        raise ClerkError("The Clerk publishable key is not valid.")
    return host


def _signing_keys(host: str, force: bool = False) -> dict:
    with _lock:
        cached = _keys.get(host)
        if cached and not force and time.monotonic() - cached[0] < _KEYS_TTL:
            return cached[1]
    response = requests.get(f"https://{host}/.well-known/jwks.json", timeout=TIMEOUT, allow_redirects=False)
    response.raise_for_status()
    found = {k["kid"]: jwt.PyJWK(k).key for k in response.json().get("keys", []) if k.get("kid") and k.get("kty") == "RSA"}
    with _lock:
        _keys[host] = (time.monotonic(), found)
    return found


def verify_token(token: str, origin: str = "") -> dict:
    """The claims of a genuine, unexpired Clerk session token for this install's Clerk address, else ClerkError."""
    configured = keys()
    if not configured:
        raise ClerkError("Clerk sign-in is not turned on.")
    host = frontend_host(configured[0])
    try:
        kid = jwt.get_unverified_header(token).get("kid")
        found = _signing_keys(host)
        if kid not in found:
            found = _signing_keys(host, force=True)  # Clerk rotated its keys
        if kid not in found:
            raise ClerkError("That sign-in could not be checked. Please try again.")
        claims = jwt.decode(token, found[kid], algorithms=["RS256"], issuer=f"https://{host}", options={"require": ["exp", "iat", "sub"]}, leeway=10)
    except ClerkError:
        raise
    except (jwt.PyJWTError, requests.RequestException, ValueError, KeyError) as exc:
        raise ClerkError("That sign-in could not be checked. Please try again.") from exc
    if claims.get("azp") and origin and claims["azp"].rstrip("/") != origin.rstrip("/"):
        raise ClerkError("That sign-in was made for another site.")
    return claims


def fetch_person(clerk_id: str) -> dict:
    """{'email', 'verified', 'first_name', 'last_name'} for the person, as Clerk's server states it."""
    configured = keys()
    if not configured:
        raise ClerkError("Clerk sign-in is not turned on.")
    try:
        response = requests.get(f"{API}/users/{clerk_id}", headers={"Authorization": f"Bearer {configured[1]}"}, timeout=TIMEOUT, allow_redirects=False)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ClerkError("Clerk could not be reached. Please try again.") from exc
    primary = next((e for e in data.get("email_addresses", []) if e.get("id") == data.get("primary_email_address_id")), None)
    verified = bool(primary and (primary.get("verification") or {}).get("status") == "verified")
    return {
        "email": (primary or {}).get("email_address", "").strip().lower(),
        "verified": verified,
        "first_name": (data.get("first_name") or "")[:150],
        "last_name": (data.get("last_name") or "")[:150],
    }


def _username(email: str) -> str:
    User = get_user_model()
    base = (re.sub(r"[^A-Za-z0-9_.-]", "", email.split("@")[0]) or "person")[:30]
    name, n = base, 1
    while User.objects.filter(username__iexact=name).exists():
        n += 1
        name = f"{base}{n}"
    return name


def sign_in_user(clerk_id: str, person: dict):
    """The user for this Clerk id, made on first sign-in if sign-up is open (or the email is on the allow-list).

    Never matched to an older account by email: a Clerk person is a new person here. Returns (user, created) or raises ClerkError."""
    if not person["email"] or not person["verified"]:
        raise ClerkError("Please verify your email address with Clerk first.")
    profile = UserProfile.objects.select_related("user").filter(clerk_user_id=clerk_id).first()
    if profile:
        if not profile.user.is_active:
            raise ClerkError("This account is turned off.")
        return profile.user, False
    config = SiteConfig.load()
    if not (config.signup_open or config.google_email_allowed(person["email"])):
        raise ClerkError("Registration is closed.")
    User = get_user_model()
    try:
        with transaction.atomic():
            user = User.objects.create(username=_username(person["email"]), email=person["email"], first_name=person["first_name"], last_name=person["last_name"])
            user.set_unusable_password()  # a Clerk person never has a password here; the admin site stays for staff
            user.save(update_fields=["password"])
            UserProfile.objects.update_or_create(user=user, defaults={"clerk_user_id": clerk_id, "self_registered": True})
            _record_verified_email(user, person["email"])
    except IntegrityError as exc:  # two sign-ins at once, or the same email twice
        raise ClerkError("That sign-in could not be completed. Please try again.") from exc
    return user, True


def _record_verified_email(user, email: str) -> None:
    """Clerk verified it, so the features that need a verified address (digests, Gmail) can rely on it, unless another account already holds it."""
    from allauth.account.models import EmailAddress

    if not EmailAddress.objects.filter(email__iexact=email).exists():
        EmailAddress.objects.create(user=user, email=email, primary=True, verified=True)
