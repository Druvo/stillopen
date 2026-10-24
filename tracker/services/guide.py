"""What to say to a person on the dashboard: a greeting, and the one thing worth doing next.

Plain language, no scores or jargon. Nothing here changes data."""
import re

from django.urls import reverse


def first_name(user) -> str:
    name = (user.first_name or "").strip()
    if not name:
        local = re.split(r"[^A-Za-z]+", (user.email or user.get_username() or "").split("@")[0])[0]
        name = local or user.get_username() or ""
    return name[:1].upper() + name[1:] if name else ""


def greeting(user, now) -> str:
    hour = now.hour
    part = "Good morning" if 5 <= hour < 12 else "Good afternoon" if 12 <= hour < 18 else "Good evening"
    name = first_name(user)
    return f"{part}, {name}" if name else part


def next_step(profile, cards, has_areas: bool = True, searching: bool = False) -> dict | None:
    """The single most useful next move, as {headline, body, label, url}; None when there is nothing to suggest."""
    if not profile.is_complete:
        missing = " and ".join(profile.missing_fields)
        return {
            "headline": "Finish your profile so matches mean something",
            "body": f"We still need {missing}. It takes a minute, and every job you add is judged against it.",
            "label": "Tell us about you", "url": reverse("profile") + "?welcome=1",
        }
    if searching and not cards:
        return {
            "headline": "We are searching for jobs that fit you",
            "body": "It reads about a hundred job sources, so it takes a minute or two. Jobs will appear below; you do not need to do anything.",
            "label": "", "url": "",
        }
    if not has_areas:
        return {
            "headline": "Tell us where you would work",
            "body": "Until we know, you will see jobs from everywhere, including places you would not move to. A minute in your profile fixes that.",
            "label": "Add places", "url": reverse("profile") + "#areas",
        }
    live = [c for c in cards if not c["app"].status.is_terminal and c["app"].live_state != "expired"]
    if not cards:
        return {
            "headline": "Add the first job you are curious about",
            "body": "Paste a link below, or press Add job. We will tell you how well it fits you, and whether it is still open.",
            "label": "Add a job", "url": reverse("add_job"),
        }
    unchecked = [c for c in live if c["percent"] is None and (c["app"].description or c["app"].url)]
    if unchecked:
        c = unchecked[0]
        return {
            "headline": f"See how well {c['app'].company} fits you",
            "body": "Press Check my fit on that card. It takes a few seconds, and it works even before you connect an AI.",
            "label": "Take me there", "url": f"#job-{c['app'].pk}",
        }
    promising = sorted(
        (c for c in live if (c["percent"] or 0) >= 50 and not c["cv"] and not c["app"].applied_date),
        key=lambda c: -c["percent"],
    )
    if promising:
        c = promising[0]
        return {
            "headline": f"{c['app'].company} looks like a good fit. Tailor your CV for it?",
            "body": "We reshape your own CV toward the posting. Nothing is invented, and you review it before it counts.",
            "label": "Take me there", "url": f"#job-{c['app'].pk}",
        }
    return None
