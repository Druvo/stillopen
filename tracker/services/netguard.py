"""Outbound-request safety for a shared server: users supply URLs, the server fetches them.

Refuses non-http(s) schemes and any host that resolves to a private, loopback, link-local, shared (CGNAT), reserved or
multicast address (this blocks cloud metadata endpoints and the server's own internal services). Redirects are followed by
hand so every hop is checked.

DNS rebinding is closed by pinning: a name is resolved ONCE per hop, every address it returned must be public, and the
connection is then made to one of those exact addresses (`PinnedAdapter`) while the URL's own host name is kept for the Host
header, the TLS server name (SNI) and certificate verification. An attacker's DNS can no longer answer "public" to the check
and "private" to the connection, because there is no second lookup.

Limit: when a proxy is configured in the environment (HTTP(S)_PROXY) the proxy does the lookup, so the address cannot be
pinned from here; that case keeps the old check-then-fetch behaviour. For hostile multi-tenant hosting also run the app in a
network namespace or behind an egress proxy.
"""
from __future__ import annotations

import ipaddress
import socket
from socket import timeout as SocketTimeout
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import ConnectTimeoutError, NewConnectionError
from urllib3.util import connection as _urllib3_connection

from tracker.services import blockedhosts

USER_AGENT = "Mozilla/5.0 (compatible; stillopen/1.0)"
MAX_REDIRECTS = 5
MAX_BYTES = 3 * 1024 * 1024


class FetchError(Exception):
    pass


def is_public_address(value: str) -> bool:
    """True only for an address on the public internet."""
    try:
        ip = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped  # ::ffff:127.0.0.1 is 127.0.0.1
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        return False
    return ip.is_global  # also rules out 100.64.0.0/10 and other not-globally-routable ranges


def _resolve(host: str, port: int) -> list[str]:
    """Every address `host` resolves to, in the order the resolver gave them (the one place a lookup happens, so tests can replace it)."""
    literal = host.strip("[]")
    try:
        ipaddress.ip_address(literal.split("%", 1)[0])
        return [literal]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, port)
    except socket.gaierror as exc:
        raise FetchError(f"Cannot resolve {host}.") from exc
    seen: list[str] = []
    for info in infos:
        address = info[4][0]
        if address not in seen:
            seen.append(address)
    if not seen:
        raise FetchError(f"Cannot resolve {host}.")
    return seen


def resolve_public(url: str) -> tuple[str, int, list[str]]:
    """(host, port, addresses) for a URL after the one lookup; raises FetchError unless the scheme is http(s) and EVERY address is public."""
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchError("Only http(s) URLs can be fetched.")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise FetchError("That web address has an invalid port.") from exc
    addresses = _resolve(parts.hostname, port)
    for address in addresses:
        if not is_public_address(address):
            raise FetchError("That address is not a public website.")
    return parts.hostname, port, addresses


def check_public_url(url: str) -> None:
    """Refuse a URL that is not a public website. (A pure check: `safe_get` does its own lookup and pins it.)"""
    resolve_public(url)


# ---- pinning ----------------------------------------------------------------------------------------------------------

def _pinned(connection_cls, ip: str):
    """A connection class that opens its socket to `ip` and leaves everything else (Host header, SNI, certificate name) on the URL's host."""

    class Pinned(connection_cls):
        def _new_conn(self):
            try:
                return _urllib3_connection.create_connection(
                    (ip, self.port), self.timeout, source_address=self.source_address, socket_options=self.socket_options,
                )
            except SocketTimeout as exc:
                raise ConnectTimeoutError(self, f"Connection to {self.host} timed out. (connect timeout={self.timeout})") from exc
            except OSError as exc:
                raise NewConnectionError(self, f"Failed to establish a new connection: {exc}") from exc

    return Pinned


class PinnedAdapter(HTTPAdapter):
    """A requests adapter whose connections all go to one already-validated IP address, whatever the URL's host name resolves to now."""

    def __init__(self, ip: str, **kwargs):
        self.pinned_ip = ip  # set before the parent builds the pool manager
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        ip = self.pinned_ip

        class Pool(HTTPConnectionPool):
            ConnectionCls = _pinned(HTTPConnection, ip)

        class SecurePool(HTTPSConnectionPool):
            ConnectionCls = _pinned(HTTPSConnection, ip)

        self.poolmanager.pool_classes_by_scheme = {"http": Pool, "https": SecurePool}


def _connect_failed(exc: requests.RequestException) -> bool:
    """True when the request never reached the server (so trying the host's next address is safe)."""
    if isinstance(exc, requests.ConnectTimeout):
        return True
    return isinstance(exc, requests.ConnectionError) and ("NewConnectionError" in repr(exc) or "Failed to establish" in str(exc))


def _proxied(url: str) -> bool:
    return bool(requests.utils.select_proxy(url, requests.utils.get_environ_proxies(url)))


def _get_pinned(url: str, addresses: list[str], timeout: float, headers: dict, verify) -> requests.Response:
    """One GET, connecting to the first of `addresses` that answers (a host with a dead IPv6 address still works through its IPv4 one)."""
    if _proxied(url):  # the proxy resolves the name, so there is nothing to pin (see the module note)
        return requests.get(url, headers=headers, timeout=timeout, allow_redirects=False, verify=verify)
    last: requests.RequestException | None = None
    for ip in addresses:
        session = requests.Session()
        session.trust_env = False  # no environment proxies or .netrc here: the connection must go to `ip` itself
        adapter = PinnedAdapter(ip, max_retries=0)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        try:
            return session.get(url, headers=headers, timeout=timeout, allow_redirects=False, verify=verify)
        except requests.RequestException as exc:
            if not _connect_failed(exc):
                raise
            last = exc
        finally:
            session.close()
    assert last is not None
    raise last


def safe_get(url: str, timeout: float = 30, headers: dict | None = None, verify=True) -> requests.Response:
    """GET with the public-address check on the first URL and on every redirect, connecting to the exact address that was checked.

    Raises FetchError. `verify` is passed to requests (a CA file path is useful in tests); certificates are always verified against
    the URL's host name, never against the IP address."""
    headers = {"User-Agent": USER_AGENT, **(headers or {})}
    try:
        for _ in range(MAX_REDIRECTS + 1):
            if blockedhosts.blocked_site(url):  # LinkedIn, Indeed, Glassdoor...: their terms forbid automated reading, so no request is ever made
                raise FetchError(blockedhosts.blocked_reply(url)["message"])
            _host, _port, addresses = resolve_public(url)
            resp = _get_pinned(url, addresses, timeout, headers, verify)
            if resp.is_redirect and resp.headers.get("location"):
                url = urljoin(url, resp.headers["location"])
                continue
            return resp
    except requests.RequestException as exc:
        raise FetchError(f"Request failed: {exc.__class__.__name__}") from exc
    raise FetchError("Too many redirects.")
