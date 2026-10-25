"""Adzuna's job search API (https://developer.adzuna.com): a free, keyed search over one country at a time.

Modelled on the Jooble connector: a *search*, so it is asked for one person's own target roles in one country (`token`: gb, de,
in...). Needs the site's free app id + key (Site configuration > Job search keys, or ADZUNA_APP_ID / ADZUNA_APP_KEY); without them
there is nothing to ask and the source is skipped silently. Aggregator: the employer varies per posting.

Adzuna's terms (developer.adzuna.com/docs/terms_of_service) allow personal job search and require each displayed advert to be
labelled "Adzuna" and linked to Adzuna's own site for that country. So: every posting keeps the `redirect_url` Adzuna returned,
unchanged; the app shows "Jobs by Adzuna" with a link wherever such a job appears; and these results are never shown on the
public board (Adzuna is not in `seed_sources.PUBLIC_OK_CONNECTORS`).

The key is part of the request address, so it is never put in an error message or a log line.
"""
import re

from tracker.services.netguard import FetchError, safe_get
from tracker.services.openboards import blurb, role_list

# Adzuna's documented countries: code -> (name, Adzuna's own site for that country, used for the attribution link).
COUNTRIES = {
    "gb": ("United Kingdom", "https://www.adzuna.co.uk"),
    "us": ("United States", "https://www.adzuna.com"),
    "at": ("Austria", "https://www.adzuna.at"),
    "au": ("Australia", "https://www.adzuna.com.au"),
    "be": ("Belgium", "https://www.adzuna.be"),
    "br": ("Brazil", "https://www.adzuna.com.br"),
    "ca": ("Canada", "https://www.adzuna.ca"),
    "ch": ("Switzerland", "https://www.adzuna.ch"),
    "de": ("Germany", "https://www.adzuna.de"),
    "es": ("Spain", "https://www.adzuna.es"),
    "fr": ("France", "https://www.adzuna.fr"),
    "in": ("India", "https://www.adzuna.in"),
    "it": ("Italy", "https://www.adzuna.it"),
    "mx": ("Mexico", "https://www.adzuna.com.mx"),
    "nl": ("Netherlands", "https://www.adzuna.nl"),
    "nz": ("New Zealand", "https://www.adzuna.co.nz"),
    "pl": ("Poland", "https://www.adzuna.pl"),
    "sg": ("Singapore", "https://www.adzuna.sg"),
    "za": ("South Africa", "https://www.adzuna.co.za"),
}
ROLES_PER_PLACE = 3
RESULTS_PER_PAGE = 50
API = "https://api.adzuna.com/v1/api/jobs"
_TAG = re.compile(r"<[^>]+>")
HOME = "https://www.adzuna.co.uk"


def attribution(code: str = "") -> dict:
    """Who to credit and where, for one country (Adzuna's own site there, or the UK one)."""
    return {"label": "Jobs by Adzuna", "url": COUNTRIES.get((code or "").lower(), ("", HOME))[1]}


def credit_for(posting) -> dict | None:
    """The "Jobs by Adzuna" credit for a posting that came from an Adzuna search (None for any other posting)."""
    if posting is None or posting.source.connector != "adzuna":
        return None
    return attribution(posting.source.board_token)


def _salary(job: dict) -> str:
    low, high = job.get("salary_min"), job.get("salary_max")
    if not low and not high:
        return ""
    low, high = int(low or high), int(high or low)
    amount = f"{low:,}" if low == high else f"{low:,} - {high:,}"
    return amount + (" (estimated by Adzuna)" if str(job.get("salary_is_predicted")) == "1" else "")


def fetch_adzuna(token: str, roles: list[str] | None = None, creds: tuple[str, str] = ("", "")) -> list[dict]:
    """One person's roles in one country. `creds` is (app_id, app_key); no credentials or no roles means nothing to ask."""
    code = (token or "").lower()
    if code not in COUNTRIES:
        raise FetchError("Unknown Adzuna country.")
    app_id, app_key = creds
    if not app_id or not app_key or not roles:
        return []
    out, seen = [], set()
    for role in role_list(roles, ROLES_PER_PLACE):
        url = (f"{API}/{code}/search/1?app_id={_q(app_id)}&app_key={_q(app_key)}&results_per_page={RESULTS_PER_PAGE}"
               f"&what={_q(role)}&max_days_old=30&sort_by=date&content-type=application/json")
        resp = safe_get(url, timeout=20, headers={"Accept": "application/json"})
        if resp.status_code in (401, 403):
            raise FetchError("Adzuna did not accept the keys. Check them in Site configuration.")
        if resp.status_code == 429:
            raise FetchError("Adzuna's free limit was reached; it is tried again on a later search.")
        if resp.status_code != 200:
            raise FetchError(f"HTTP {resp.status_code}")
        try:
            results = (resp.json() or {}).get("results", [])
        except ValueError as exc:
            raise FetchError("Adzuna sent something unexpected.") from exc
        for j in results:
            link = j.get("redirect_url") or ""  # the result's own address, exactly as Adzuna returned it
            if not link or link in seen:
                continue
            seen.add(link)
            where = ((j.get("location") or {}).get("display_name") or "").strip()
            name = COUNTRIES[code][0]
            if name.lower() not in where.lower():
                where = f"{where}, {name}" if where else name
            out.append({
                "title": _TAG.sub("", j.get("title", "")).strip(), "url": link, "location": where,
                "company": ((j.get("company") or {}).get("display_name") or "").strip(),
                "description": blurb(j.get("description", "")), "salary": _salary(j), "posted": (j.get("created") or "")[:10],
            })
    return out


def _q(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")
