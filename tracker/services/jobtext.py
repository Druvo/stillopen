"""Fetch the text of a job posting. Used when an application has a URL but no pasted description."""
import html
import re
import subprocess
from html.parser import HTMLParser

from tracker.services import blockedhosts
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


def _refuse_blocked(url: str) -> None:
    """LinkedIn, Indeed, Glassdoor and the like forbid automated reading: no request (not even through career-ops) is made for their links."""
    reply = blockedhosts.blocked_reply(url)
    if reply:
        raise FetchError(reply["message"])


def fetch_description(url: str, config) -> str:
    """Best-effort job text. Raises FetchError with a reason the user can read."""
    url = normalize_url(url)
    _refuse_blocked(url)
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


def _extract_title(raw_html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
    if not m:
        return ""
    return html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()


_TITLE_SPLIT_PATTERNS = (
    re.compile(r"^(?P<role>.+?)\s+\bat\b\s+(?P<company>.+)$", re.IGNORECASE),
    re.compile(r"^(?P<role>.+?)\s*[|–—-]\s*(?P<company>.+)$"),
)


def guess_role_company(title: str) -> tuple[str, str]:
    """Best-effort split of a page <title> into (role, company) for the quick-add bar to prefill --
    a convenience guess the person reviews and edits before anything is saved, never auto-trusted."""
    title = title.strip()
    for pattern in _TITLE_SPLIT_PATTERNS:
        m = pattern.match(title)
        if m:
            role, company = m.group("role").strip(), m.group("company").strip()
            if role and company:
                return role[:200], company[:160]
    return title[:200], ""


def fetch_posting(url: str, config) -> dict:
    """Best-effort (title, description) guess for the quick-add bar. Raises FetchError like fetch_description.
    career-ops' fetch-jd.mjs only returns plain text, no title, so a posting fetched that way comes back with
    an empty title -- the person fills in company/role by hand on the review page, same as today."""
    url = normalize_url(url)
    _refuse_blocked(url)
    check_public_url(url)
    co_text = _via_careerops(url, config)
    if len(co_text) >= MIN_USEFUL_CHARS:
        return {"description": co_text, "title": ""}
    resp = safe_get(url)
    if resp.status_code >= 400:
        raise FetchError(f"The site returned HTTP {resp.status_code}.")
    raw_html = resp.text[: 3 * 1024 * 1024]
    text = html_to_text(raw_html)
    if len(text) < MIN_USEFUL_CHARS:
        raise FetchError("The page has too little readable text (it probably needs JavaScript). Paste the description instead.")
    return {"description": text, "title": _extract_title(raw_html)}
