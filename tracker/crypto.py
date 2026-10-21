"""Encrypt secrets stored in the database (AI API key). The key is derived from Django's SECRET_KEY."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(("stillopen-secret-v1:" + settings.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode() if text else ""


def decrypt(token: str) -> str:
    """Return the plain text, or "" if the token is empty or was written with a different SECRET_KEY."""
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ""
