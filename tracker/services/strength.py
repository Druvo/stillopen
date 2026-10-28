"""How much of what matching needs the person has told us: a percentage and the few most useful things still missing.

Counts only what changes a match (roles, where they live, a CV with enough in it, notes, where they would work, a pay floor); the
rest of the profile (alerts, display, account) does not count. Plain facts about the person's own rows, never a judgement of them."""
from tracker.models import KnowledgeSource, SiteConfig, UserProfile
from tracker.services import knowledge

CV_FULL = 800  # characters of CV text that make a CV worth matching against
CV_SOME = 150

# (key, label when missing, why it helps, where to add it, weight)
ITEMS = [
    ("roles", "Add the roles you want", "Searches and matches start from the roles you list.", "/profile", 25),
    ("cv", "Paste your CV", "Every match compares a job with what your CV says.", "/profile", 30),
    ("areas", "Add a place you would work", "We only show jobs where you would actually work.", "/profile#areas", 15),
    ("home_country", "Say which country you live in", "Remote jobs limited to one country only fit if it is yours.", "/profile", 10),
    ("notes", "Add a note about a project or skill", "Notes beyond your CV let more of a job's requirements be ticked.", "/knowledge", 10),
    ("salary", "Add your pay floor", "We can tell you when a job pays less than you want.", "/profile", 10),
]


def meter(user) -> dict:
    profile = UserProfile.for_user(user)
    config = SiteConfig.for_user(user)
    cv_len = len((config.effective_profile_cv or "").strip())
    notes = (
        KnowledgeSource.objects.filter(owner=user, enabled=True).exclude(key__in=["profile-cv", "careerops:cv.md"]).exclude(text="").exists()
    )
    got = {
        "roles": 1.0 if profile.target_roles.strip() else 0.0,
        "cv": 1.0 if cv_len >= CV_FULL else 0.5 if cv_len >= CV_SOME else 0.0,
        "areas": 1.0 if user.search_areas.exists() else 0.0,
        "home_country": 1.0 if profile.home_country else 0.0,
        "notes": 1.0 if notes else 0.0,
        "salary": 1.0 if profile.salary_floor.strip() else 0.0,
    }
    total = sum(w for *_, w in ITEMS)
    percent = round(sum(got[key] * w for key, _l, _y, _t, w in ITEMS) / total * 100)
    missing = []
    for key, label, why, to, weight in sorted(ITEMS, key=lambda i: -i[4]):
        if got[key] < 1.0:
            if key == "cv" and got[key] > 0:
                label, why = "Add more to your CV", "A short CV leaves most of a job's requirements unchecked."
            missing.append({"key": key, "label": label, "why": why, "to": to})
    return {"percent": percent, "missing": missing[:3], "complete": not missing}
