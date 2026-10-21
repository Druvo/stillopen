"""Places and posting details, with no external service.

resolve_place(text)  ->  set of ISO country codes, {"*"} for "anywhere", or None when the place is not recognised.
detect(title, text)  ->  guesses for a posting's location, work arrangement, sponsorship, relocation, type and seniority.

Coverage is a built-in table of the countries, regions and cities job seekers use most. An unrecognised place is
reported as such rather than guessed. Detection only suggests: the person can always correct it.
"""
import re

# ISO code: (name, aliases). Aliases listed in CASE_SENSITIVE only match in that exact case (US, UK, UAE).
COUNTRIES = {
    "BD": ("Bangladesh", []), "IN": ("India", []), "PK": ("Pakistan", []), "LK": ("Sri Lanka", []), "NP": ("Nepal", []),
    "MY": ("Malaysia", []), "SG": ("Singapore", []), "ID": ("Indonesia", []), "TH": ("Thailand", []),
    "VN": ("Vietnam", ["Viet Nam"]), "PH": ("Philippines", []), "JP": ("Japan", []),
    "KR": ("South Korea", ["Korea", "Republic of Korea"]), "CN": ("China", []), "HK": ("Hong Kong", []), "TW": ("Taiwan", []),
    "AU": ("Australia", []), "NZ": ("New Zealand", []),
    "AE": ("United Arab Emirates", ["UAE", "Emirates"]), "SA": ("Saudi Arabia", ["KSA"]), "QA": ("Qatar", []),
    "KW": ("Kuwait", []), "BH": ("Bahrain", []), "OM": ("Oman", []), "JO": ("Jordan", []), "LB": ("Lebanon", []),
    "IL": ("Israel", []), "TR": ("Turkey", ["Turkiye", "Türkiye"]), "EG": ("Egypt", []), "MA": ("Morocco", []),
    "TN": ("Tunisia", []), "NG": ("Nigeria", []), "GH": ("Ghana", []), "KE": ("Kenya", []), "ZA": ("South Africa", []),
    "ET": ("Ethiopia", []), "RW": ("Rwanda", []), "TZ": ("Tanzania", []), "UG": ("Uganda", []),
    "GB": ("United Kingdom", ["UK", "Great Britain", "Britain", "England", "Scotland", "Wales", "Northern Ireland"]),
    "IE": ("Ireland", []), "DE": ("Germany", []), "FR": ("France", []), "ES": ("Spain", []), "PT": ("Portugal", []),
    "IT": ("Italy", []), "NL": ("Netherlands", ["Holland"]), "BE": ("Belgium", []), "LU": ("Luxembourg", []),
    "CH": ("Switzerland", []), "AT": ("Austria", []), "SE": ("Sweden", []), "NO": ("Norway", []), "DK": ("Denmark", []),
    "FI": ("Finland", []), "IS": ("Iceland", []), "PL": ("Poland", []), "CZ": ("Czech Republic", ["Czechia"]),
    "SK": ("Slovakia", []), "HU": ("Hungary", []), "RO": ("Romania", []), "BG": ("Bulgaria", []), "GR": ("Greece", []),
    "HR": ("Croatia", []), "RS": ("Serbia", []), "SI": ("Slovenia", []), "EE": ("Estonia", []), "LV": ("Latvia", []),
    "LT": ("Lithuania", []), "UA": ("Ukraine", []), "CY": ("Cyprus", []), "MT": ("Malta", []),
    "US": ("United States", ["USA", "US", "U.S.", "U.S.A.", "America"]), "CA": ("Canada", []), "MX": ("Mexico", []),
    "BR": ("Brazil", []), "AR": ("Argentina", []), "CL": ("Chile", []), "CO": ("Colombia", []), "PE": ("Peru", []),
    "UY": ("Uruguay", []), "CR": ("Costa Rica", []), "PA": ("Panama", []), "RU": ("Russia", []),
}
CASE_SENSITIVE = {"UK", "US", "UAE", "USA", "KSA", "U.S.", "U.S.A."}

_GULF = {"AE", "SA", "QA", "KW", "BH", "OM"}
_MIDDLE_EAST = _GULF | {"JO", "LB", "IL", "TR", "EG"}
_EUROPE = {"GB", "IE", "DE", "FR", "ES", "PT", "IT", "NL", "BE", "LU", "CH", "AT", "SE", "NO", "DK", "FI", "IS", "PL", "CZ", "SK",
           "HU", "RO", "BG", "GR", "HR", "RS", "SI", "EE", "LV", "LT", "UA", "CY", "MT", "RU"}
_EU = _EUROPE - {"GB", "CH", "NO", "IS", "UA", "RS", "RU"}
_SEA = {"MY", "SG", "ID", "TH", "VN", "PH"}
_SOUTH_ASIA = {"BD", "IN", "PK", "LK", "NP"}
_EAST_ASIA = {"JP", "KR", "CN", "HK", "TW"}
_ASIA = _SEA | _SOUTH_ASIA | _EAST_ASIA
_AFRICA = {"EG", "MA", "TN", "NG", "GH", "KE", "ZA", "ET", "RW", "TZ", "UG"}
_LATAM = {"MX", "BR", "AR", "CL", "CO", "PE", "UY", "CR", "PA"}

REGIONS = {
    "gulf": _GULF, "gcc": _GULF, "middle east": _MIDDLE_EAST, "mena": _MIDDLE_EAST | {"MA", "TN"},
    "europe": _EUROPE, "eu": _EU, "european union": _EU, "asia": _ASIA, "southeast asia": _SEA, "south east asia": _SEA,
    "sea": _SEA, "south asia": _SOUTH_ASIA, "east asia": _EAST_ASIA, "apac": _ASIA | {"AU", "NZ"},
    "asia pacific": _ASIA | {"AU", "NZ"}, "africa": _AFRICA, "north america": {"US", "CA", "MX"},
    "latin america": _LATAM, "latam": _LATAM, "oceania": {"AU", "NZ"}, "emea": _EUROPE | _MIDDLE_EAST | _AFRICA,
}
ANYWHERE = {"anywhere", "worldwide", "world wide", "global", "globally", "everywhere", "any country", "anywhere in the world",
            "remote worldwide", "remote anywhere", "work from anywhere"}

CITIES = {
    "BD": ["Dhaka", "Chittagong", "Chattogram", "Sylhet", "Khulna", "Rajshahi", "Gazipur", "Narayanganj"],
    "MY": ["Kuala Lumpur", "Penang", "George Town", "Johor Bahru", "Cyberjaya", "Petaling Jaya", "Selangor", "Putrajaya", "Kota Kinabalu", "Kuching"],
    "SG": [], "AE": ["Dubai", "Abu Dhabi", "Sharjah", "Ajman", "Ras Al Khaimah"], "SA": ["Riyadh", "Jeddah", "Dammam", "Khobar", "Mecca"],
    "QA": ["Doha"], "KW": ["Kuwait City"], "BH": ["Manama"], "OM": ["Muscat"], "JO": ["Amman"], "LB": ["Beirut"],
    "IN": ["Bangalore", "Bengaluru", "Mumbai", "New Delhi", "Delhi", "Hyderabad", "Chennai", "Pune", "Gurgaon", "Gurugram", "Noida", "Kolkata", "Ahmedabad"],
    "PK": ["Karachi", "Lahore", "Islamabad", "Rawalpindi"], "LK": ["Colombo"], "NP": ["Kathmandu"],
    "ID": ["Jakarta", "Bali", "Surabaya", "Bandung"], "TH": ["Bangkok", "Chiang Mai", "Phuket"], "VN": ["Hanoi", "Ho Chi Minh City", "Ho Chi Minh", "Saigon", "Da Nang"],
    "PH": ["Manila", "Makati", "Cebu", "Taguig"], "JP": ["Tokyo", "Osaka", "Kyoto", "Yokohama"], "KR": ["Seoul", "Busan"],
    "CN": ["Shanghai", "Beijing", "Shenzhen", "Guangzhou", "Hangzhou"], "TW": ["Taipei"],
    "AU": ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Canberra"], "NZ": ["Auckland", "Wellington"],
    "GB": ["London", "Manchester", "Edinburgh", "Birmingham", "Bristol", "Glasgow", "Leeds", "Cambridge"], "IE": ["Dublin", "Cork"],
    "DE": ["Berlin", "Munich", "Hamburg", "Frankfurt", "Cologne"], "FR": ["Paris", "Lyon"], "ES": ["Madrid", "Barcelona", "Valencia"],
    "PT": ["Lisbon", "Porto"], "IT": ["Milan", "Rome"], "NL": ["Amsterdam", "Rotterdam", "Eindhoven", "The Hague"], "BE": ["Brussels"],
    "CH": ["Zurich", "Geneva", "Basel"], "AT": ["Vienna"], "SE": ["Stockholm", "Gothenburg"], "NO": ["Oslo"], "DK": ["Copenhagen"],
    "FI": ["Helsinki"], "PL": ["Warsaw", "Krakow", "Wroclaw", "Gdansk"], "CZ": ["Prague", "Brno"], "HU": ["Budapest"],
    "RO": ["Bucharest", "Cluj"], "BG": ["Sofia"], "GR": ["Athens"], "EE": ["Tallinn"], "LV": ["Riga"], "LT": ["Vilnius"],
    "UA": ["Kyiv", "Kiev"], "TR": ["Istanbul", "Ankara"], "EG": ["Cairo"], "MA": ["Casablanca"], "NG": ["Lagos"], "KE": ["Nairobi"],
    "ZA": ["Johannesburg", "Cape Town"], "GH": ["Accra"], "RW": ["Kigali"],
    "US": ["New York", "San Francisco", "Seattle", "Austin", "Boston", "Chicago", "Los Angeles", "Atlanta", "Denver", "Washington DC", "San Jose", "Palo Alto", "Mountain View", "Dallas", "Miami"],
    "CA": ["Toronto", "Vancouver", "Montreal", "Ottawa", "Calgary"], "MX": ["Mexico City"], "BR": ["Sao Paulo", "São Paulo", "Rio de Janeiro"],
    "AR": ["Buenos Aires"], "CL": ["Santiago"], "CO": ["Bogota", "Bogotá", "Medellin"], "PE": ["Lima"],
}


def _build():
    patterns = []
    for code, (name, aliases) in COUNTRIES.items():
        for alias in [name, *aliases]:
            patterns.append((alias, code, "country"))
    for code, cities in CITIES.items():
        for city in cities:
            patterns.append((city, code, "city"))
    compiled = []
    for text, code, kind in sorted(patterns, key=lambda p: -len(p[0])):  # longest first: "Kuala Lumpur" before "Lumpur"
        flags = 0 if text in CASE_SENSITIVE else re.IGNORECASE
        compiled.append((re.compile(r"(?<![A-Za-z])" + re.escape(text) + r"(?![A-Za-z])", flags), code, kind, text))
    return compiled


_PLACES = _build()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower().replace("-", " ")).strip(" .")


def resolve_place(text: str):
    """Country codes a place stands for. {"*"} = anywhere. None = not recognised."""
    cleaned = _norm(text or "")
    if not cleaned:
        return None
    if cleaned in ANYWHERE:
        return {"*"}
    if cleaned in REGIONS:
        return set(REGIONS[cleaned])
    # "City, Country": the last part is the most specific statement about the country
    for part in reversed([p for p in re.split(r"[,/|()]|\s-\s|–|—", text) if p.strip()]):
        key = _norm(part)
        if key in ANYWHERE:
            return {"*"}
        if key in REGIONS:
            return set(REGIONS[key])
        for pattern, code, _, _ in _PLACES:
            if pattern.fullmatch(part.strip()):
                return {code}
    hit = _first_place(text)
    return {hit[0]} if hit else None


def _first_place(text: str):
    """(code, matched text, start) of the earliest recognised country or city in `text`."""
    best = None
    for pattern, code, _, name in _PLACES:
        m = pattern.search(text)
        if m and (best is None or m.start() < best[2]):
            best = (code, m.group(0), m.start())
    return best


def country_name(code: str) -> str:
    return COUNTRIES.get((code or "").upper(), (code or "",))[0]


# --- detection from posting text ---------------------------------------------------------------------------------

_NEGATION = re.compile(r"(?:\bnot\b|\bno\b|\bnon\b|n't|\bwithout\b)[\s-]*(?:\w+\s+){0,2}$", re.I)


def _positive(pattern: str, text: str) -> bool:
    for m in re.finditer(pattern, text, re.I):
        if not _NEGATION.search(text[max(0, m.start() - 24) : m.start()]):
            return True
    return False


def _arrangement(text: str) -> str:
    hybrid = _positive(r"\bhybrid\b", text)
    remote = _positive(r"\b(?:fully[- ]|100%[- ]|remote[- ]first|work from home|work from anywhere|wfh|distributed team)|\bremote\b", text)
    onsite = _positive(r"\bon[- ]?site\b|\bin[- ]office\b|\boffice[- ]based\b|\bin[- ]person\b", text)
    if hybrid:
        return "hybrid"
    if remote and not onsite:
        return "remote"
    if onsite and not remote:
        return "onsite"
    return ""


def _location(text: str) -> tuple[str, str]:
    """(display text, country code). A 'Location:' line is trusted most; else the earliest place in the opening."""
    m = re.search(r"(?:^|\n)\s*(?:location|based in|office location|work location)\s*[:\-]\s*([^\n.;|]{2,80})", text, re.I)
    if m:
        place = m.group(1).strip().rstrip(".")
        codes = resolve_place(place)
        if codes and "*" not in codes and len(codes) == 1:
            return place, next(iter(codes))
        if codes and "*" in codes:
            return place, ""
    hit = _first_place(text[:2500])
    return (hit[1], hit[0]) if hit else ("", "")


_SENIORITY = [
    ("junior", r"\b(?:intern|junior|jr\.?|entry[- ]level|graduate|trainee)\b"),
    ("manager", r"\b(?:manager|head of|director|vp\b)"),
    ("principal", r"\b(?:principal|architect|distinguished)\b"),
    ("lead", r"\b(?:lead|staff|team lead|tech lead)\b"),
    ("senior", r"\b(?:senior|sr\.?)\b"),
    ("mid", r"\b(?:mid[- ]level|intermediate)\b"),
]


def detect(title: str, text: str) -> dict:
    """Best guesses; only fields that were actually found are returned."""
    text = text or ""
    title = title or ""
    whole = f"{title}\n{text}"
    found = {}
    arrangement = _arrangement(whole)
    if arrangement:
        found["arrangement"] = arrangement
    place, code = _location(whole)
    anywhere = arrangement == "remote" and _positive(r"\b(?:worldwide|anywhere in the world|work from anywhere|global(?:ly)?)\b", whole)
    if anywhere and not code:
        found["location_text"] = "Remote (worldwide)"
    elif place:
        found["location_text"] = place[:160]
    if code and not anywhere:
        found["country"] = code
    if re.search(r"\b(?:no (?:visa )?sponsorship|unable to sponsor|cannot sponsor|can't sponsor|not (?:able to )?sponsor|without (?:visa )?sponsorship|"
                 r"must (?:already )?(?:have|hold|possess) (?:the |valid )?(?:right|authori[sz]ation|work permit)|right to work in)\b", whole, re.I):
        found["sponsorship"] = "no"
    elif re.search(r"\b(?:visa sponsorship|sponsor(?:s|ship)? (?:your |a )?(?:work )?visa|we sponsor|work permit (?:is )?(?:provided|sponsored)|visa (?:support|assistance)|visa and relocation)\b", whole, re.I):
        found["sponsorship"] = "yes"
    if re.search(r"\b(?:no relocation|relocation (?:is )?not (?:provided|offered|available)|unable to (?:offer|provide) relocation)\b", whole, re.I):
        found["relocation"] = "no"
    elif re.search(r"\brelocation (?:package|assistance|support|bonus|allowance|help|provided|offered|available)\b|\b(?:help|assist)(?:ing)? (?:you )?(?:with )?relocat", whole, re.I):
        found["relocation"] = "yes"
    for kind, pattern in [("internship", r"\bintern(?:ship)?\b"), ("contract", r"\b(?:contract(?:or)?|fixed[- ]term)\b"),
                          ("part_time", r"\bpart[- ]time\b"), ("freelance", r"\bfreelance\b"), ("full_time", r"\b(?:full[- ]time|permanent)\b")]:
        if re.search(pattern, title, re.I) or (kind != "internship" and re.search(pattern, text[:3000], re.I)):
            found["employment_type"] = kind
            break
    for level, pattern in _SENIORITY:
        if re.search(pattern, title, re.I):
            found["seniority"] = level
            break
    return found


DETAIL_FIELDS = ("location_text", "country", "arrangement", "sponsorship", "relocation", "employment_type", "seniority")


def fill_details(app, overwrite: bool = False) -> list[str]:
    """Fill blank detail fields of `app` from its posting. Returns the names changed. Never touches fields the person set,
    unless `overwrite` is true and the details were detected rather than set by hand."""
    if not (app.description or app.role):
        return []
    if overwrite and app.details_source == "manual":
        return []
    found = detect(app.role, app.description)
    changed = []
    for name in DETAIL_FIELDS:
        if name in found and (overwrite or not getattr(app, name)) and getattr(app, name) != found[name]:
            setattr(app, name, found[name])
            changed.append(name)
    if changed:
        if app.details_source != "manual":
            app.details_source = "detected"
        app.save(update_fields=[*changed, "details_source"])
    return changed
