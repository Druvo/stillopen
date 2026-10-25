"""Reading a company's own public careers page the way a search engine does.

Many career pages publish each opening as schema.org `JobPosting` structured data (JSON-LD in a `<script type="application/ld+json">` block)
because Google asks them to. This reader fetches a page the person named, reads those blocks, and returns the openings in the same shape
every other connector returns (title, url, location, company, description).

What it does and does not do:
- It sends a plain request that names StillOpen and a contact address, through `netguard.safe_get` only (public addresses only, every
  redirect checked, no private or credentialed addresses).
- It reads `/robots.txt` first and never reads a page it disallows, and never keeps a page that says `noindex` (meta tag or header).
- One request per second per host, at most `MAX_REQUESTS` requests per run, only links on the same host, at most `MAX_DETAIL_PAGES` opening pages.
- It never runs JavaScript, never signs in, and never opens a link that leaves the host.
Nothing here is shown on the public board; a page is read only for the person who added it.
"""
import json
import re
import time
from html import unescape
from html.parser import HTMLParser
from urllib import robotparser
from urllib.parse import urljoin, urlparse, urlunparse

from django.conf import settings

from tracker.services import blockedhosts, jobtext, netguard
from tracker.services.netguard import FetchError

MAX_REQUESTS = 30  # every request of one run, robots.txt included
MAX_DETAIL_PAGES = 25
MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_ROBOTS_BYTES = 500 * 1024
MAX_RUN_SECONDS = 120
MIN_GAP_SECONDS = 1.0  # per host
MAX_URL = 300
MAX_JSONLD_NODES = 5000
EXCERPT_CHARS = 2000

_LD = re.compile(r"<script\b[^>]*\btype\s*=\s*[\"']?application/ld\+json[\"']?[^>]*>(.*?)</script\s*>", re.I | re.S)
_META = re.compile(r"<meta\b[^>]*>", re.I)
_OPENING_PATH = re.compile(r"(?:^|[/_\-.])(jobs?|careers?|positions?|openings?|vacanc(?:y|ies)|requisitions?|apply|roles?|postings?)(?:$|[/_\-.\d])", re.I)
_FILE_EXT = re.compile(r"\.(?:pdf|docx?|png|jpe?g|gif|svg|webp|ico|css|js|xml|zip|mp4|mp3)$", re.I)


class CareerPageError(FetchError):
    """A refusal or failure in plain words for the person (the message is shown as it is)."""


def user_agent() -> str:
    from tracker.services import links

    contact = getattr(settings, "STILLOPEN_BOT_CONTACT", "") or links.base_url() or "no public address set"
    return f"StillOpen-CareersReader/1.0 (+{contact}; reads public JobPosting data, obeys robots.txt)"


def normalise_url(raw: str) -> str:
    """The stored form of a careers page address: https, lower-case host, no fragment. Raises ValueError with words for the person."""
    raw = (raw or "").strip()
    if not raw.lower().startswith("https://"):
        raise ValueError("Use the full address of the page, starting with https://")
    try:
        parts = urlparse(raw)
        host = parts.hostname
    except ValueError:
        raise ValueError("That does not look like a web address.") from None
    if parts.username or parts.password or "@" in parts.netloc:
        raise ValueError("A web address with a user name or password in it cannot be used.")
    if not host or "." not in host:
        raise ValueError("That does not look like a web address.")
    if parts.port not in (None, 443):
        raise ValueError("Use the normal address of the page, without a port number.")
    if blockedhosts.blocked_site(raw):
        raise ValueError(blockedhosts.blocked_reply(raw)["message"].split(", so we")[0] + ". Paste single job links into Add job instead.")
    url = urlunparse(("https", host.lower(), parts.path or "/", "", parts.query, ""))
    if len(url) > MAX_URL:
        raise ValueError(f"That address is too long ({MAX_URL} letters at most).")
    return url


# ---- reading one page ------------------------------------------------------------------------------------------------

class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href.strip())


def _noindex(html: str, headers) -> bool:
    if "noindex" in (headers.get("X-Robots-Tag") or "").lower():
        return True
    for tag in _META.findall(html[:200_000]):
        lowered = tag.lower()
        if re.search(r"name\s*=\s*[\"']?(?:robots|googlebot|stillopen[\w-]*)[\"']?", lowered) and "noindex" in lowered:
            return True
    return False


def _walk(node, out: list, budget: list, depth: int = 0):
    if budget[0] <= 0 or depth > 8:
        return
    budget[0] -= 1
    if isinstance(node, list):
        for item in node:
            _walk(item, out, budget, depth + 1)
    elif isinstance(node, dict):
        kinds = node.get("@type")
        kinds = [kinds] if isinstance(kinds, str) else (kinds if isinstance(kinds, list) else [])
        if "JobPosting" in kinds:
            out.append(node)
        for key in ("@graph", "itemListElement", "item", "mainEntity", "mainEntityOfPage", "hasPart", "about", "offers"):
            if key in node:
                _walk(node[key], out, budget, depth + 1)


def job_postings(html: str) -> list[dict]:
    """Every JobPosting object in the page's JSON-LD blocks, in any of the usual shapes (object, array, @graph, nested ItemList)."""
    found: list[dict] = []
    budget = [MAX_JSONLD_NODES]
    for block in _LD.findall(html):
        text = unescape(block).strip()
        text = re.sub(r"^\s*<!\[CDATA\[|\]\]>\s*$", "", text).strip()
        try:
            data = json.loads(text)
        except ValueError:
            continue
        _walk(data, found, budget)
    return found


def _s(value) -> str:
    return re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else ""


def _name(value) -> str:
    if isinstance(value, dict):
        return _s(value.get("name")) or _s(value.get("@id"))
    if isinstance(value, list):
        return ", ".join(x for x in (_name(v) for v in value) if x)
    return _s(value)


def _place(loc) -> str:
    if isinstance(loc, list):
        parts = [p for p in (_place(x) for x in loc[:5]) if p]
        return "; ".join(dict.fromkeys(parts))
    if not isinstance(loc, dict):
        return _s(loc)
    address = loc.get("address", loc)
    if isinstance(address, str):
        return _s(address)
    if not isinstance(address, dict):
        return _s(loc.get("name"))
    parts = [_s(address.get("addressLocality")), _s(address.get("addressRegion")), _name(address.get("addressCountry"))]
    return ", ".join(dict.fromkeys(p for p in parts if p)) or _s(loc.get("name"))


def _money(salary) -> str:
    if not isinstance(salary, dict):
        return ""
    currency = _s(salary.get("currency"))
    value = salary.get("value", salary)
    if not isinstance(value, dict):
        return " ".join(x for x in (currency, _s(str(value)) if value not in (None, "") else "") if x)
    low, high, one = value.get("minValue"), value.get("maxValue"), value.get("value")
    unit = _s(value.get("unitText")).lower()
    amount = f"{low} to {high}" if low not in (None, "") and high not in (None, "") else str(one if one not in (None, "") else (low if low not in (None, "") else high or ""))
    if not amount.strip():
        return ""
    return " ".join(x for x in (currency, amount, f"per {unit}" if unit else "") if x)[:120]


def _plain(value) -> str:
    text = unescape(value) if isinstance(value, str) else ""
    text = unescape(text) if "&lt;" in text else text
    return jobtext.html_to_text(text) if text else ""


def to_posting(node: dict, page_url: str, index: int, host: str) -> dict | None:
    """One JobPosting as the dict every connector returns, or None when it has no title."""
    title = _s(node.get("title")) or _s(node.get("name"))
    if not title:
        return None
    link = ""
    for key in ("url", "@id", "sameAs"):
        raw = node.get(key)
        if isinstance(raw, str):
            candidate = blockedhosts.clean_link(urljoin(page_url, raw.strip()))
            if candidate and not blockedhosts.blocked_site(candidate):
                link = candidate
                break
    if not link:
        link = f"{page_url.split('#')[0]}#opening-{index}" if index else page_url.split("#")[0]
    place = _place(node.get("jobLocation"))
    kind = node.get("jobLocationType")
    remote = "TELECOMMUTE" in (kind if isinstance(kind, str) else " ".join(map(str, kind or []))).upper()
    if remote:
        limits = _name(node.get("applicantLocationRequirements"))
        place = f"Remote ({limits})" if limits else (f"Remote, {place}" if place else "Remote")
    elif not place:
        place = ""
    kinds = node.get("employmentType")
    kinds = ", ".join(str(k).replace("_", " ").title() for k in ([kinds] if isinstance(kinds, str) else (kinds or [])))
    facts = []
    pay = _money(node.get("baseSalary"))
    if pay:
        facts.append(f"Pay: {pay}")
    if kinds:
        facts.append(f"Employment: {kinds}")
    posted, until = _s(node.get("datePosted"))[:10], _s(node.get("validThrough"))[:10]
    if posted:
        facts.append(f"Posted: {posted}")
    if until:
        facts.append(f"Apply by: {until}")
    body = _plain(node.get("description"))
    description = ("\n".join(facts) + ("\n\n" if facts and body else "") + body)[:EXCERPT_CHARS]
    return {
        "title": title[:300], "url": link, "location": place[:160],
        "company": _name(node.get("hiringOrganization"))[:160] or host, "description": description,
    }


def looks_like_opening(path: str) -> bool:
    return bool(_OPENING_PATH.search(path)) and not _FILE_EXT.search(path)


# ---- the run ------------------------------------------------------------------------------------------------------------

class _Run:
    def __init__(self, get, clock, sleep):
        self.get, self.clock, self.sleep = get, clock, sleep
        self.requests = 0
        self.last: dict[str, float] = {}
        self.robots: dict[str, robotparser.RobotFileParser | None] = {}
        self.started = clock()
        self.agent = user_agent()

    def _request(self, url: str):
        if self.requests >= MAX_REQUESTS:
            raise CareerPageError("That page links to more pages than we read in one go, so we stopped.")
        if self.clock() - self.started > MAX_RUN_SECONDS:
            raise CareerPageError("That site took too long to answer, so we stopped. It will be tried again at your next search.")
        host = (urlparse(url).hostname or "").lower()
        wait = self.last.get(host, -1e9) + MIN_GAP_SECONDS - self.clock()
        if wait > 0:
            self.sleep(wait)
        self.last[host] = self.clock()
        self.requests += 1
        try:
            return self.get(url, timeout=15, headers={"User-Agent": self.agent, "Accept": "text/html,application/xhtml+xml"})
        except CareerPageError:
            raise
        except FetchError as exc:
            raise CareerPageError(str(exc) if "public website" in str(exc) else "We could not read that page. Check the address, or paste single job links into Add job.") from None

    def allowed(self, url: str) -> bool:
        parts = urlparse(url)
        host = (parts.hostname or "").lower()
        if host not in self.robots:
            parser = robotparser.RobotFileParser()
            try:
                resp = self._request(f"https://{host}/robots.txt")
            except CareerPageError as exc:
                if "public website" in str(exc):
                    raise
                raise CareerPageError("We could not check what that site allows (its robots.txt did not answer), so we did not read it. Try again later.") from None
            if resp.status_code in (401, 403):
                parser.disallow_all = True
            elif resp.status_code == 200:
                parser.parse(resp.text[:MAX_ROBOTS_BYTES].splitlines())
            elif 500 <= resp.status_code < 600:
                raise CareerPageError("We could not check what that site allows (its robots.txt did not answer), so we did not read it. Try again later.")
            else:
                parser.allow_all = True
            self.robots[host] = parser
        return self.robots[host].can_fetch("StillOpen", url) and self.robots[host].can_fetch(self.agent, url)

    def page(self, url: str) -> tuple[str, str] | None:
        """(final url, html) of an allowed, indexable page, or None when it is disallowed, not a page, or says noindex."""
        if not self.allowed(url):
            return None
        resp = self._request(url)
        final = getattr(resp, "url", None) or url
        if resp.status_code != 200:
            return None
        if (urlparse(final).hostname or "").lower() != (urlparse(url).hostname or "").lower():
            if not self.allowed(final):  # a same-site redirect to another name (example.com -> www.example.com): that name's rules apply
                return None
        kind = (resp.headers.get("Content-Type") or "text/html").lower()
        if "html" not in kind and "xml" not in kind:
            return None
        raw = getattr(resp, "content", b"") or b""
        if len(raw) > MAX_PAGE_BYTES:
            return None
        html = resp.text
        if _noindex(html, resp.headers):
            return None
        return final, html


def read(url: str, get=None, clock=None, sleep=None) -> list[dict]:
    """The openings on a careers page. Raises `CareerPageError` (plain words) when the page may not or cannot be read. An empty list means no list was found."""
    run = _Run(get or netguard.safe_get, clock or time.monotonic, sleep or time.sleep)
    url = normalise_url(url)
    host = urlparse(url).hostname
    if not run.allowed(url):
        raise CareerPageError("That site asks programs not to read this page (its robots.txt says no), so we have not read it. Try another page, or paste single job links into Add job.")
    first = run.page(url)
    if first is None:
        raise CareerPageError("We could not read that page: it is closed to programs (it asks not to be indexed) or it did not answer. Try another page, or paste single job links into Add job.")
    final, html = first
    base_host = (urlparse(final).hostname or host).lower()
    found = job_postings(html)
    postings = [p for i, n in enumerate(found) if (p := to_posting(n, final, i if len(found) > 1 else 0, base_host))]
    if not postings:
        hrefs = _Links()
        try:
            hrefs.feed(html[:1_000_000])
        except Exception:  # noqa: BLE001 - a broken page just gives the links read so far
            pass
        seen, queue = {final.split("#")[0]}, []
        for href in hrefs.hrefs:
            link = blockedhosts.clean_link(urljoin(final, href)) if not href.lower().startswith(("javascript:", "mailto:", "tel:", "#")) else ""
            if not link:
                continue
            parts = urlparse(link)
            if (parts.hostname or "").lower() != base_host or not looks_like_opening(parts.path):
                continue
            key = link.split("#")[0]
            if key in seen:
                continue
            seen.add(key)
            queue.append(link)
            if len(queue) >= MAX_DETAIL_PAGES:
                break
        for link in queue:
            try:
                got = run.page(link)
            except CareerPageError:
                break  # out of requests or time: keep what was read
            if got is None:
                continue
            page_url, page_html = got
            nodes = job_postings(page_html)
            for i, node in enumerate(nodes):
                p = to_posting(node, page_url, i if len(nodes) > 1 else 0, base_host)
                if p:
                    postings.append(p)
    unique: dict[str, dict] = {}
    for p in postings:
        unique.setdefault(p["url"], p)
    return list(unique.values())


def fetch_careerpage(token: str) -> list[dict]:
    """The connector entry point `scan._fetch` calls: `token` is the stored page address."""
    return read(token)
