"""How a person likes the app laid out, saved on their profile so it follows them to every device.

Nothing here is a secret and nothing changes what the app does for them: it is the dashboard view (list or board), the stage tab,
sort and filters, whether the sidebar is collapsed, the theme, and two accessibility options (text size, density). The stored
value is whatever the person last saved; reading always returns a complete, valid object, so old or damaged data can never break
a page, and writing validates every value, so nothing odd is ever stored."""
from ..models import Bucket, SiteConfig

DEFAULTS = {
    "view": "list",
    "tab": "all",
    "sort": "best",
    "filters_open": False,
    "tz_prompt_dismissed": False,  # the person said "not now" to the suggestion to use this device's time zone
    "ai_prompt_dismissed": False,  # the person said "not now" to the card asking for a Google AI Studio key
    "checklist_dismissed": False,  # the person closed the "Getting started" checklist on the dashboard
    "hide_weak": False,  # leave out jobs whose match is under 40% (a job with no match yet is always shown)
    "filters": {"fit": "", "match": "", "work": "", "country": "", "posting": "", "found": ""},
    "sidebar": "expanded",
    "theme": "light",
    "text_size": "normal",
    "density": "comfortable",
    "cover_tone": "warm",  # how the next cover letter should sound
    "quiet_days": 10,  # "Worth a look next": an application with no reply for this many days counts as quiet (3 to 30)
    "goal_daily": 0,  # applications a day the person wants to send; 0 is off (goals are opt-in)
    "goal_weekly": 0,  # applications over any 7 days; 0 is off
    "insights_period": "90",  # the funnel's period tab on Insights: "30", "90" or "all"
}

# Whole-number settings: (lowest, highest).
INTEGERS = {"quiet_days": (3, 30), "goal_daily": (0, 50), "goal_weekly": (0, 200)}

CHOICES = {
    "view": ("list", "board"),
    "sort": ("best", "newest", "oldest", "company", "deadline"),
    "sidebar": ("expanded", "collapsed"),
    "theme": ("light", "dark"),
    "text_size": ("normal", "large", "larger"),
    "density": ("comfortable", "compact"),
    "cover_tone": ("warm", "direct", "formal"),
    "insights_period": ("30", "90", "all"),
}
BOOLEANS = ("filters_open", "ai_prompt_dismissed", "tz_prompt_dismissed", "checklist_dismissed", "hide_weak")
FILTER_KEYS = tuple(DEFAULTS["filters"])
FILTER_MAX = 60


class PreferenceError(Exception):
    """`fields` maps a preference name to what is wrong with it, in plain words."""

    def __init__(self, fields: dict[str, list[str]]):
        self.fields = fields
        super().__init__(next(iter(next(iter(fields.values())))))


def _filters(value) -> dict:
    given = value if isinstance(value, dict) else {}
    return {key: (given.get(key) if isinstance(given.get(key), str) else "")[:FILTER_MAX] for key in FILTER_KEYS}


def normalize(stored, default_theme: str | None = None) -> dict:
    """A complete, valid preferences object from whatever is stored (anything unknown or invalid falls back to the
    default). `default_theme` is the site's own default (Site configuration > Appearance) for a person who has
    never chosen for themselves -- once they do, their own choice always wins over it."""
    stored = stored if isinstance(stored, dict) else {}
    out = {}
    for key, options in CHOICES.items():
        fallback = default_theme if key == "theme" and default_theme in CHOICES["theme"] else DEFAULTS[key]
        out[key] = stored.get(key) if stored.get(key) in options else fallback
    for key in BOOLEANS:
        out[key] = stored[key] if isinstance(stored.get(key), bool) else DEFAULTS[key]
    for key, (low, high) in INTEGERS.items():
        value = stored.get(key)
        out[key] = value if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high else DEFAULTS[key]
    out["filters"] = _filters(stored.get("filters"))
    tab = stored.get("tab")
    out["tab"] = tab if isinstance(tab, str) and (tab == "all" or Bucket.objects.filter(key=tab).exists()) else "all"
    return out


def read(profile) -> dict:
    return normalize(profile.ui_preferences, default_theme=SiteConfig.load().default_theme)


def update(profile, patch: dict) -> dict:
    """Validate `patch` (any subset of the keys) and save it on top of what is stored; returns the full object."""
    problems: dict[str, list[str]] = {}
    unknown = sorted(set(patch) - set(DEFAULTS))
    for key in unknown:
        problems[key] = ["That is not a setting we keep."]
    for key, options in CHOICES.items():
        if key in patch and patch[key] not in options:
            problems[key] = [f"Choose one of: {', '.join(options)}."]
    for key, (low, high) in INTEGERS.items():
        if key in patch and not (isinstance(patch[key], int) and not isinstance(patch[key], bool) and low <= patch[key] <= high):
            problems[key] = [f"Choose a whole number from {low} to {high}."]
    for key in BOOLEANS:
        if key in patch and not isinstance(patch[key], bool):
            problems[key] = ["This must be true or false."]
    if "filters" in patch:
        value = patch["filters"]
        if not isinstance(value, dict) or set(value) - set(FILTER_KEYS) or any(not isinstance(v, str) or len(v) > FILTER_MAX for v in value.values()):
            problems["filters"] = ["Filters must be a few short words each, for the filters we have."]
    if "tab" in patch:
        tab = patch["tab"]
        if not isinstance(tab, str) or not (tab == "all" or Bucket.objects.filter(key=tab).exists()):
            problems["tab"] = ["That stage does not exist."]
    if problems:
        raise PreferenceError(problems)
    merged = {**read(profile), **{k: v for k, v in patch.items() if k != "filters"}}
    if "filters" in patch:
        merged["filters"] = _filters(patch["filters"])
    profile.ui_preferences = merged
    profile.save(update_fields=["ui_preferences"])
    return normalize(merged)
