"""Give data created before accounts existed (a single-user install) to its first user."""
from tracker.models import Application, KnowledgeSource, LivenessRun, PER_USER_FIELDS, SiteConfig, UserProfile


def has_orphans() -> bool:
    return (
        Application.objects.filter(owner__isnull=True).exists()
        or KnowledgeSource.objects.filter(owner__isnull=True).exists()
    )


def claim_orphans(user) -> dict:
    """Assign every ownerless row to `user` and seed their profile from the legacy site-wide settings."""
    counts = {
        "applications": Application.objects.filter(owner__isnull=True).update(owner=user),
        "knowledge": KnowledgeSource.objects.filter(owner__isnull=True).update(owner=user),
        "runs": LivenessRun.objects.filter(owner__isnull=True).update(owner=user),
        "profile_seeded": False,
    }
    profile = UserProfile.for_user(user)
    if not profile.profile_cv.strip() and not profile.about.strip():
        config = SiteConfig.load()
        for name in PER_USER_FIELDS:
            setattr(profile, name, getattr(config, name))
        profile.about = config.profile_preferences
        profile.save()
        counts["profile_seeded"] = True
    return counts
