"""Sites whose pages StillOpen never requests, and the one place that cleans a job link.

LinkedIn, Indeed and Glassdoor forbid automated reading and block bots, so a link to one of them is kept as text and never fetched: the
person pastes the posting text themselves. This module only parses text (no network). The list lives here and nowhere else.
"""
import re
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlunparse

# registrable names (the part before the public suffix); matched against the end of the host so country sites (indeed.co.uk, de.indeed.com) count
BLOCKED = {
    "linkedin": ("linkedin.com", "lnkd.in"),
    "indeed": ("indeed.com", "indeed.co.uk", "indeed.ca", "indeed.de", "indeed.fr", "indeed.in", "indeed.com.au", "indeed.com.sg", "indeed.ae", "indeed.com.my"),
    "glassdoor": ("glassdoor.com", "glassdoor.co.uk", "glassdoor.ca", "glassdoor.de", "glassdoor.in", "glassdoor.com.au", "glassdoor.sg"),
    "ziprecruiter": ("ziprecruiter.com",),
    "monster": ("monster.com",),
    "naukri": ("naukri.com",),
}
LABELS = {"linkedin": "LinkedIn", "indeed": "Indeed", "glassdoor": "Glassdoor", "ziprecruiter": "ZipRecruiter", "monster": "Monster", "naukri": "Naukri"}

TRACKING_PARAMS = {
    "trackingid", "refid", "midtoken", "midsig", "eid", "trk", "trkemail", "lipi", "otptoken", "gclid", "fbclid", "mc_cid", "mc_eid", "mkt_tok",
    "tracking", "trackid", "vjk", "jk_src", "fromage", "cmpid", "gdsid", "uido", "ctt", "alid", "feedtype", "rtid", "ref", "src", "campaign",
}
_TRACKING_PREFIXES = ("utm_", "mc_", "hsa_", "pk_", "ga_")
_LINKEDIN_ID = re.compile(r"/(?:comm/)?jobs/view/(?:[^/?#]*-)?(\d{5,})")
_JOB_ID_PARAM = ("currentjobid", "jobid", "job_id")


def host_of(url: str) -> str:
    try:
        return (urlparse(url.strip()).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def blocked_site(url: str) -> str:
    """The key of the blocked site this link points at ("linkedin", "indeed", ...), or "" for any other address."""
    host = host_of(url)
    if not host:
        return ""
    for key, domains in BLOCKED.items():
        if any(host == d or host.endswith("." + d) for d in domains):
            return key
    return ""


def linkedin_job_id(url: str) -> str:
    """The numeric job id in a LinkedIn job link of any common shape, or "". Never follows a link (lnkd.in short links give nothing)."""
    if blocked_site(url) != "linkedin" or host_of(url).endswith("lnkd.in"):
        return ""
    try:
        parts = urlparse(url.strip())
    except ValueError:
        return ""
    found = _LINKEDIN_ID.search(unquote(parts.path))
    if found:
        return found.group(1)
    for key, value in parse_qsl(parts.query):
        if key.lower() in _JOB_ID_PARAM and value.isdigit():
            return value
    return ""


def canonical_linkedin(url: str) -> str:
    job_id = linkedin_job_id(url)
    return f"https://www.linkedin.com/jobs/view/{job_id}/" if job_id else ""


def _is_tracking(name: str) -> bool:
    lowered = name.lower()
    return lowered in TRACKING_PARAMS or lowered.startswith(_TRACKING_PREFIXES)


_REDIRECT_PARAMS = ("url", "u", "q", "target", "dest", "destination", "redirect", "redirect_url", "redirecturl", "link", "to", "r", "continue")


def clean_link(url: str, depth: int = 0) -> str:
    """A tidy http(s) link, or "" when the text is not a safe web link.

    Unwraps a redirect wrapper whose real address is in a query parameter, drops tracking parameters and the fragment, turns a LinkedIn job
    link into https://www.linkedin.com/jobs/view/<id>/, and refuses every scheme except http and https (javascript:, data:, mailto: ...)."""
    url = (url or "").strip().strip("<>\"'")
    if not url or len(url) > 2000:
        return ""
    try:
        parts = urlparse(url)
    except ValueError:
        return ""
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        return ""
    if depth < 3:
        for key, value in parse_qsl(parts.query):
            if key.lower() in _REDIRECT_PARAMS and re.match(r"https?://", value, re.I) and host_of(value) != host_of(url):
                inner = clean_link(value, depth + 1)
                if inner:
                    return inner
    canonical = canonical_linkedin(url)
    if canonical:
        return canonical
    site = blocked_site(url)
    query = parse_qsl(parts.query, keep_blank_values=False)
    if site == "indeed":
        jk = next((v for k, v in query if k.lower() in ("jk", "vjk") and re.fullmatch(r"[0-9a-fA-F]{8,32}", v)), "")
        if jk:
            return f"https://{parts.netloc.lower()}/viewjob?jk={jk}"
    if site == "glassdoor":
        query = [(k, v) for k, v in query if k.lower() in ("jl", "joblistingid")]
        return urlunparse((parts.scheme.lower(), parts.netloc.lower(), parts.path, "", urlencode(query), ""))[:600]
    kept = [(k, v) for k, v in query if not _is_tracking(k)]
    cleaned = urlunparse((parts.scheme.lower(), parts.netloc.lower(), parts.path, "", urlencode(kept), ""))
    return cleaned if len(cleaned) <= 600 else ""


BLOCKED_MESSAGE = (
    "{site} does not let other apps read its pages, so we have kept the link and need the text from you: open the job on {site}, "
    "select the description, copy and paste it below."
)


def blocked_reply(url: str) -> dict | None:
    """For a link to a blocked site: {"blocked_host", "url", "message"} with the cleaned link, and nothing was requested. None for other links."""
    key = blocked_site(url)
    if not key:
        return None
    link = canonical_linkedin(url) or clean_link(url) or url.strip()[:600]
    if key == "linkedin" and not canonical_linkedin(url):
        link = clean_link(url) if not host_of(url).endswith("lnkd.in") else url.strip()[:600]
    return {"blocked_host": key, "url": link, "message": BLOCKED_MESSAGE.format(site=LABELS[key])}
