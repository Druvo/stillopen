"""Fetch the text of a job posting. Used when an application has a URL but no pasted description."""
import ipaddress
import re
import socket
import subprocess
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests

from tracker.services.liveness import USER_AGENT, normalize_url

MIN_USEFUL_CHARS = 200


class FetchError(Exception):
    pass


def check_public_url(url: str) -> None:
    """Refuse non-http(s) URLs and hosts that resolve to private or loopback addresses (SSRF guard)."""
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchError("Only http(s) URLs can be fetched.")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443)
    except socket.gaierror as exc:
        raise FetchError(f"Cannot resolve {parts.hostname}.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise FetchError("That address is not a public website.")


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in ("p", "br", "li", "div", "h1", "h2", "h3", "h4", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(parser.parts))
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _via_careerops(url: str, config) -> str:
    """career-ops' fetch-jd.mjs reads known ATS APIs (Greenhouse, Lever, Ashby, Workday) without a browser."""
    if not config.careerops_path:
        return ""
    try:
        r = subprocess.run(
            [config.node_command, "fetch-jd.mjs", url],
            cwd=config.careerops_path,
            capture_output=True,
            text=True,
            timeout=min(config.liveness_timeout, 60),
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def fetch_description(url: str, config) -> str:
    """Best-effort job text. Raises FetchError with a reason the admin can show."""
    url = normalize_url(url)
    check_public_url(url)
    text = _via_careerops(url, config)
    if len(text) >= MIN_USEFUL_CHARS:
        return text
    try:
        for _ in range(5):  # follow redirects by hand so every hop is checked
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30, allow_redirects=False)
            if resp.is_redirect and resp.headers.get("location"):
                url = requests.compat.urljoin(url, resp.headers["location"])
                check_public_url(url)
                continue
            break
        else:
            raise FetchError("Too many redirects.")
    except requests.RequestException as exc:
        raise FetchError(f"Request failed: {exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        raise FetchError(f"The site returned HTTP {resp.status_code}.")
    text = html_to_text(resp.text)
    if len(text) < MIN_USEFUL_CHARS:
        raise FetchError("The page has too little readable text (it probably needs JavaScript). Paste the description instead.")
    return text
