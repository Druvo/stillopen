"""Fetch the text of a job posting. Used when an application has a URL but no pasted description."""
import re
import subprocess
from html.parser import HTMLParser

from tracker.services.liveness import normalize_url
from tracker.services.netguard import FetchError, check_public_url, safe_get  # noqa: F401  (re-exported)

MIN_USEFUL_CHARS = 200


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
    """career-ops' fetch-jd.mjs reads known ATS APIs (Greenhouse, Lever, Ashby, Workday) without a browser.
    Only for site admins: it runs a local command, so restricted users never reach it."""
    if not config.careerops_path or getattr(config, "restricted", False):
        return ""
    try:
        r = subprocess.run(
            [config.node_command, "fetch-jd.mjs", "--", url],
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
    """Best-effort job text. Raises FetchError with a reason the user can read."""
    url = normalize_url(url)
    check_public_url(url)
    text = _via_careerops(url, config)
    if len(text) >= MIN_USEFUL_CHARS:
        return text
    resp = safe_get(url)
    if resp.status_code >= 400:
        raise FetchError(f"The site returned HTTP {resp.status_code}.")
    text = html_to_text(resp.text[: 3 * 1024 * 1024])
    if len(text) < MIN_USEFUL_CHARS:
        raise FetchError("The page has too little readable text (it probably needs JavaScript). Paste the description instead.")
    return text
