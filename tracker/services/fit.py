"""Does a job fit what the person said they want? Returns warnings and notes. Never hides or removes a job.

Each message is {"level": "ok" | "warn" | "info", "text": ...}. A job is compared with the person's search areas
(place, arrangements, sponsorship, relocation, salary) and with their preferred employment types and seniority.
Anything the posting does not state is reported as unknown, not assumed.
"""
import re

from tracker.models import Application, SearchArea, UserProfile
from tracker.services import geo

_ARRANGEMENT_FLAG = {"remote": "allow_remote", "hybrid": "allow_hybrid", "onsite": "allow_onsite"}
_ARRANGEMENT_LABEL = {"remote": "remote", "hybrid": "hybrid", "onsite": "on-site"}

_SYMBOLS = {"RM": "MYR", "$": "USD", "€": "EUR", "£": "GBP", "৳": "BDT", "₹": "INR"}
_AMOUNT = re.compile(
    r"(?P<cur>[A-Za-z]{3}|RM|[$€£৳₹])\s?(?P<a>\d[\d,]*(?:\.\d+)?)\s?(?P<ka>[kK])?"
    r"(?:\s?(?:-|–|to)\s?(?:[A-Za-z]{3}|RM|[$€£৳₹])?\s?(?P<b>\d[\d,]*(?:\.\d+)?)\s?(?P<kb>[kK])?)?"
)
_KNOWN_CURRENCIES = {"USD", "EUR", "GBP", "BDT", "MYR", "INR", "AED", "SAR", "QAR", "KWD", "SGD", "CAD", "AUD", "JPY", "PKR", "LKR", "IDR", "THB", "PHP"}


def parse_pay(text: str) -> dict | None:
    """The highest figure in an advertised pay string, with currency and period, or None if it cannot be read safely."""
    if not text:
        return None
    for m in _AMOUNT.finditer(text):
        cur = m.group("cur")
        cur = _SYMBOLS.get(cur) or _SYMBOLS.get(cur.upper()) or cur.upper()
        if cur not in _KNOWN_CURRENCIES:
            continue

        def number(value, k):
            if not value:
                return None
            n = float(value.replace(",", ""))
            return n * 1000 if k else n

        low, high = number(m.group("a"), m.group("ka")), number(m.group("b"), m.group("kb"))
        top = max(x for x in (low, high) if x is not None)
        tail = text[m.end(): m.end() + 24].lower()
        period = ("month" if re.search(r"month|/mo\b|monthly", tail) else "year" if re.search(r"year|annum|annual|/yr|p\.a\.", tail)
                  else "hour" if re.search(r"hour|/hr", tail) else "")
        return {"amount": top, "currency": cur, "period": period}
    return None


def _convert_to_period(amount: float, src: str, dst: str) -> float | None:
    if src == dst:
        return amount
    if (src, dst) == ("month", "year"):
        return amount * 12
    if (src, dst) == ("year", "month"):
        return amount / 12
    return None


def _job_is_global(app: Application) -> bool:
    return app.arrangement == "remote" and bool(re.search(r"worldwide|anywhere|global", app.location_text or "", re.I))


def _remote_restricted(app: Application) -> bool:
    """A remote job that says people must be based in one particular country."""
    return app.arrangement == "remote" and bool(app.country) and not _job_is_global(app)


def _place_match(area: SearchArea, app: Application, home: str = "") -> str:
    codes = geo.resolve_place(area.place)
    if codes is None:  # a place we cannot recognise: compare the name with what the posting says
        if not app.location_text:
            return "maybe"
        return "yes" if area.place.lower() in app.location_text.lower() else "no"
    country = (app.country or "").upper()
    if _remote_restricted(app):
        if home and country == home.upper():
            return "yes"  # the person lives where the job must be done from
        return "yes" if "*" not in codes and country in codes else "no"
    if "*" in codes or _job_is_global(app):
        return "yes"  # "Anywhere" never excludes a job; a worldwide-remote job is open to every area
    if country:
        return "yes" if country in codes else "no"
    return "maybe"


def _arrangement_match(area: SearchArea, app: Application) -> str:
    if not app.arrangement:
        return "maybe"
    return "yes" if getattr(area, _ARRANGEMENT_FLAG[app.arrangement]) else "no"


def _area_status(area: SearchArea, app: Application, home: str = "") -> str:
    """'yes', 'no' or 'maybe': can this job be done under this area?"""
    checks = {_place_match(area, app, home), _arrangement_match(area, app)}
    if "no" in checks:
        return "no"
    return "maybe" if "maybe" in checks else "yes"


def _needs(area: SearchArea) -> int:
    return int(area.needs_visa_sponsorship) + int(area.needs_relocation_support) + int(bool(area.min_salary))


def _specificity(area: SearchArea, app: Application) -> int:
    """Which of several areas that all fit a job to name: the one that describes it best. A worldwide remote job is best
    described by "Anywhere"; a job in one country by that country (then a region, then "Anywhere"). Lower is better."""
    codes = geo.resolve_place(area.place)
    anywhere = bool(codes) and "*" in codes
    if _job_is_global(app):
        return 0 if anywhere else 1
    if anywhere:
        return 3
    if codes is None:
        return 1
    return 0 if len(codes) == 1 else 2


def area_status(app: Application, areas: list, profile: UserProfile | None = None) -> str:
    """The best any of the person's search areas can say about this posting: "yes" (it clearly fits one), "maybe" (the
    posting does not say enough, or the person has no areas) or "no" (it is stated to be outside every area)."""
    if not areas or not (app.country or app.arrangement or app.location_text):
        return "maybe"
    home = profile.home_country if profile else ""
    statuses = {_area_status(area, app, home) for area in areas}
    return "yes" if "yes" in statuses else "maybe" if "maybe" in statuses else "no"


def region_outside(place_codes: set[str], areas: list, profile: UserProfile | None = None) -> bool:
    """A posting whose location names several countries ("Hong Kong; Singapore", "Remote - European Union", "United States
    and Canada") fits only if the person lives in one of them or one of their own search areas names one. "Anywhere" does
    not count: it means any remote job, not that every region will take you. No places or no named countries: never excluded."""
    if len(place_codes) < 2 or not areas:
        return False
    if profile and profile.home_country and profile.home_country.upper() in place_codes:
        return False
    for area in areas:
        codes = geo.resolve_place(area.place)
        if codes and "*" not in codes and place_codes & set(codes):
            return False
        if codes is None and any(area.place.lower() == geo.country_name(c).lower() for c in place_codes):
            return False
    return True


def clearly_outside(app: Application, areas: list, profile: UserProfile | None = None) -> bool:
    """True only when the posting states enough about where it is that no search area can take it. A job with
    no stated place, or one that might fit, is never excluded: the search leaves out clear mismatches, not unknowns."""
    return bool(areas) and area_status(app, areas, profile) == "no"


def fit_flags(app: Application, areas: list | None = None, profile: UserProfile | None = None) -> list[dict]:
    """All fit messages for `app` against its owner's profile. Pass `areas` and `profile` to avoid a query per job."""
    flags: list[dict] = []
    if app.owner_id is None:
        return flags
    if areas is None:
        areas = list(SearchArea.objects.filter(owner_id=app.owner_id))
    if profile is None:
        profile = UserProfile.objects.filter(user_id=app.owner_id).first()

    if not areas:
        flags.append({"level": "info", "text": "Add the places you would work in your profile and each job can be checked against them."})
    elif not (app.country or app.arrangement or app.location_text):
        flags.append({"level": "info", "text": "This job has no location or work arrangement yet, so it cannot be checked against your search areas. Add it on the job's details page."})
    else:
        home = profile.home_country if profile else ""
        statuses = [(area, _area_status(area, app, home)) for area in areas]
        fits = sorted((a for a, s in statuses if s == "yes"), key=lambda a: (_needs(a), _specificity(a, app)))
        maybes = [a for a, s in statuses if s == "maybe"]
        where = app.location_text or geo.country_name(app.country) or "an unknown place"
        what = _ARRANGEMENT_LABEL.get(app.arrangement, "work arrangement not stated")
        if fits:
            area = fits[0]
            flags.append({"level": "ok", "text": f"{where} ({what}) fits your search area: {area.place}{', ' + area.city if area.city else ''}."})
            flags += _terms_flags(app, area)
        elif maybes:
            flags.append({"level": "info", "text": f"{where} ({what}) might fit your search area {maybes[0].place}, but the posting does not say enough to be sure."})
        else:
            names = "; ".join(f"{a.place} ({'/'.join(a.arrangements) or 'none'})" for a in areas)
            hint = ""
            if _remote_restricted(app) and not home:
                hint = " If you live in " + geo.country_name(app.country) + ", set your home country in Profile."
            flags.append({"level": "warn", "text": f"{where} ({what}) is outside your search areas: {names}.{hint}"})

    if profile:
        if profile.employment_types and app.employment_type and app.employment_type not in profile.employment_types:
            wanted = ", ".join(dict(UserProfile.EMPLOYMENT).get(k, k) for k in profile.employment_types)
            flags.append({"level": "warn", "text": f"This looks like a {app.get_employment_type_display().lower()} role; you want: {wanted}."})
        if profile.seniority_levels and app.seniority and app.seniority not in profile.seniority_levels:
            wanted = ", ".join(dict(UserProfile.SENIORITY).get(k, k) for k in profile.seniority_levels)
            flags.append({"level": "warn", "text": f"This looks {app.get_seniority_display().lower()}; you want: {wanted}."})
    return flags


def _terms_flags(app: Application, area: SearchArea) -> list[dict]:
    flags = []
    place = area.place
    if area.needs_visa_sponsorship and app.arrangement != "remote":
        if app.sponsorship == "no":
            flags.append({"level": "warn", "text": f"The posting says no visa sponsorship, and you need it in {place}."})
        elif app.sponsorship == "yes":
            flags.append({"level": "ok", "text": "The posting offers visa sponsorship, which you need."})
        else:
            flags.append({"level": "info", "text": f"The posting does not mention visa sponsorship, which you need in {place}."})
    if area.needs_relocation_support and app.arrangement != "remote":
        if app.relocation == "no":
            flags.append({"level": "warn", "text": f"The posting offers no relocation support, and you need it for {place}."})
        elif app.relocation == "yes":
            flags.append({"level": "ok", "text": "The posting offers relocation support, which you need."})
        else:
            flags.append({"level": "info", "text": f"The posting does not mention relocation support, which you need for {place}."})
    if area.min_salary and area.salary_currency:
        pay = parse_pay(app.advertised_pay)
        if pay and pay["currency"] == area.salary_currency.upper() and pay["period"]:
            comparable = _convert_to_period(pay["amount"], pay["period"], area.salary_period)
            if comparable is not None:
                if comparable < area.min_salary:
                    flags.append({"level": "warn", "text": f"Advertised pay (up to {pay['amount']:,.0f} {pay['currency']} per {pay['period']}) is below your minimum for {place}."})
                else:
                    flags.append({"level": "ok", "text": "Advertised pay meets your minimum."})
    return flags


def summary_level(flags: list[dict]) -> str:
    """One word for the dashboard pill: warn, ok or unknown."""
    levels = {f["level"] for f in flags}
    if "warn" in levels:
        return "warn"
    return "ok" if "ok" in levels else "unknown"
