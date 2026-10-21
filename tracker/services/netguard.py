"""Outbound-request safety for a shared server: users supply URLs, the server fetches them.

Refuses non-http(s) schemes and any host that resolves to a private, loopback, link-local, reserved or multicast
address (this blocks cloud metadata endpoints and the server's own internal services). Redirects are followed by
hand so every hop is checked. DNS rebinding between the check and the request is not covered; for hostile
multi-tenant hosting also run the app in a network namespace or behind an egress proxy.
"""
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

USER_AGENT = "Mozilla/5.0 (compatible; stillopen/1.0)"
MAX_REDIRECTS = 5
MAX_BYTES = 3 * 1024 * 1024


class FetchError(Exception):
    pass


def check_public_url(url: str) -> None:
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchError("Only http(s) URLs can be fetched.")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise FetchError(f"Cannot resolve {parts.hostname}.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise FetchError("That address is not a public website.")


def safe_get(url: str, timeout: float = 30, headers: dict | None = None) -> requests.Response:
    """GET with the public-address check on the first URL and on every redirect. Raises FetchError."""
    headers = {"User-Agent": USER_AGENT, **(headers or {})}
    check_public_url(url)
    try:
        for _ in range(MAX_REDIRECTS + 1):
            resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=False)
            if resp.is_redirect and resp.headers.get("location"):
                url = urljoin(url, resp.headers["location"])
                check_public_url(url)
                continue
            return resp
    except requests.RequestException as exc:
        raise FetchError(f"Request failed: {exc.__class__.__name__}") from exc
    raise FetchError("Too many redirects.")
