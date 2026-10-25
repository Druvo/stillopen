"""Why is my country empty? For each place a person searches, how many jobs the shared boards listed there lately, which
searches can see that place at all, and a plain next step when coverage is thin.

Read-only and owner-scoped: only sources the person's own searches use (`JobSource.for_user`) count, and the postings are the
shared facts about those boards (never anyone's tracked jobs). The counts are one grouped query, cached briefly.
"""
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count
from django.utils import timezone

from tracker.models import JobSource, Posting, UserProfile
from tracker.services import geo, scan

DAYS = 30
THIN_BELOW = 15  # fewer jobs than this in 30 days counts as thin
CACHE_SECONDS = 600
CONNECTOR_NAMES = {"jooble": "Jooble", "adzuna": "Adzuna", "jobtech": "JobTech", "getonbrd": "Get on Board"}


def _counts(user) -> dict:
    """{"by_country": {code: {"postings": n, "sources": {id,...}}}, "remote": {...}} for the last 30 days, cached for a few minutes."""
    key = f"coverage-counts:{user.pk}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    ids = list(JobSource.for_user(user, enabled=True).values_list("pk", flat=True))
    cutoff = timezone.now() - timedelta(days=DAYS)
    by_country: dict = {}
    remote = {"postings": 0, "sources": set()}
    base = Posting.objects.filter(source_id__in=ids, last_seen_at__gte=cutoff)
    for code, source_id, n in base.exclude(country="").values_list("country", "source_id").annotate(n=Count("id")):
        slot = by_country.setdefault(code, {"postings": 0, "sources": set()})
        slot["postings"] += n
        slot["sources"].add(source_id)
    for source_id, n in base.filter(remote=True).values_list("source_id").annotate(n=Count("id")):
        remote["postings"] += n
        remote["sources"].add(source_id)
    data = {"by_country": by_country, "remote": remote}
    cache.set(key, data, CACHE_SECONDS)
    return data


def _label(area, codes) -> str:
    if codes and "*" in codes:
        return "Anywhere (remote)"
    if codes and len(codes) == 1:
        return geo.country_name(next(iter(codes)))
    return area.place


def _join(names: list[str]) -> str:
    names = sorted(set(names))
    return " or ".join(names) if len(names) <= 2 else ", ".join(names[:-1]) + " or " + names[-1]


def tip_for(label: str, postings: int, searches: list[dict], is_staff: bool, has_roles: bool) -> str:
    """One plain sentence naming the next step, or "" when the place is well covered."""
    ready = [s for s in searches if s["ready"]]
    waiting = [s for s in searches if s["reason"] == "needs_key"]
    if postings >= THIN_BELOW:
        return ""
    lead = f"Nothing lists jobs in {label} yet." if postings == 0 else f"Only {postings} job{'s' if postings != 1 else ''} listed in {label} so far."
    if searches and not has_roles:
        return f"{lead} Add the roles you want in your profile, so the job searches that cover {label} know what to look for."
    if ready and postings == 0:
        return f"{lead} {_join([s['connector_label'] for s in ready])} covers {label} and runs with your next job search."
    extras = "add a company's careers page under Job sources, or paste a job link into Add job"
    if waiting:
        names = _join([s["connector_label"] for s in waiting])
        who = "Add a free key under Site configuration" if is_staff else "Ask the site owner to add a free key"
        return f"{lead} {names} covers {label} but needs a free key. {who}, {extras}."
    if is_staff:
        return f"{lead} No job site we can search covers {label} yet, so {extras}."
    return f"{lead} No job site we can search covers {label} yet. Ask the site owner to add an Adzuna or Jooble key, {extras}."


def for_user(user) -> dict:
    profile = UserProfile.for_user(user)
    has_roles = bool(profile.target_roles.strip())
    areas = list(user.search_areas.all())
    sources = list(JobSource.for_user(user, enabled=True))
    keys = scan.site_keys()
    counts = _counts(user)
    out = []
    for area in areas:
        codes = geo.resolve_place(area.place)
        label = _label(area, codes)
        if codes is None:  # a place we cannot resolve stays unknown: nothing to count, nothing to claim
            out.append({"id": area.pk, "place": area.place, "label": label, "known": False, "postings": 0, "boards": 0, "searches": [],
                        "level": "unknown", "tip": "", "searches_ready": 0, "searches_waiting": 0})
            continue
        if "*" in codes:
            postings, board_ids = counts["remote"]["postings"], set(counts["remote"]["sources"])
        else:
            postings, board_ids = 0, set()
            for code in codes:
                slot = counts["by_country"].get(code)
                if slot:
                    postings += slot["postings"]
                    board_ids |= slot["sources"]
        searches = []
        for s in sources:
            if s.connector not in scan.SEARCH_CONNECTORS:
                continue
            seen = scan.search_codes(s.connector, s.board_token)
            if not seen or "*" in codes or not (seen & codes):
                continue
            if not scan.key_ready(s.connector, keys):
                reason = "needs_key"
            elif not has_roles:
                reason = "needs_roles"
            else:
                reason = ""
            searches.append({"name": s.name, "connector": s.connector, "connector_label": CONNECTOR_NAMES.get(s.connector, s.connector),
                             "ready": reason == "", "reason": reason})
        level = "none" if postings == 0 else "thin" if postings < THIN_BELOW else "ok"
        out.append({
            "id": area.pk, "place": area.place, "label": label, "known": True, "postings": postings, "boards": len(board_ids),
            "searches": searches, "searches_ready": sum(1 for s in searches if s["ready"]),
            "searches_waiting": sum(1 for s in searches if s["reason"] == "needs_key"),
            "level": level, "tip": tip_for(label, postings, searches, user.is_staff, has_roles),
        })
    return {
        "days": DAYS, "areas": out, "has_areas": bool(areas),
        "empty_areas": sum(1 for a in out if a["level"] == "none"),
        "keys": {"jooble": bool(keys.get("jooble")), "adzuna": scan.key_ready("adzuna", keys)},
    }
