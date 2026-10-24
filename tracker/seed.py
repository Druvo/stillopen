"""Default configuration, applied by a data migration and reused by tests. All of it is editable in the admin."""

BUCKETS = [
    ("apply", "To apply", 1, False, "Evaluated roles you have not submitted yet"),
    ("pending", "Applied & pending", 2, False, "Submitted, waiting for a reply or in a process"),
    ("closed", "Closed & skipped", 3, True, "Expired, rejected or discarded"),
]

# name, bucket, order, colour, counts_as_applied, is_terminal
STATUSES = [
    ("Evaluated", "apply", 1, "#8b93a7", False, False),
    ("Applied", "pending", 2, "#5b9dff", True, False),
    ("Responded", "pending", 3, "#3ecf8e", True, False),
    ("Interview", "pending", 4, "#3ecf8e", True, False),
    ("Offer", "pending", 5, "#3ecf8e", True, False),
    ("Hired", "pending", 6, "#3ecf8e", True, True),
    ("Rejected", "closed", 7, "#f16565", True, True),
    ("Discarded", "closed", 8, "#8b93a7", False, True),
    ("SKIP", "closed", 9, "#8b93a7", False, True),
]

SCORE_BANDS = [("Strong", 80, "#3ecf8e"), ("Fair", 70, "#f5b642"), ("A stretch", 0, "#e8935a")]

DOCUMENT_KINDS = [
    ("CV", "cv,resume", "CV", "CV / Resume", 1),
    ("Cover letter", "cover", "Cover letter", "Cover letter", 2),
    ("Report", "", "Job evaluation", "Evaluation report", 3),
    ("Other", "", "", "", 4),
]

SOURCES = [
    ("LinkedIn", "linkedin.com"),
    ("bdjobs", "bdjobs.com"),
    ("Company site", "careers."),
    ("JobStreet", "jobstreet."),
    ("Indeed", "indeed."),
    ("Bayt", "bayt.com"),
]

EXPIRED_PHRASES = [
    ("no longer accepting applications", "LinkedIn"),
    ("this position has been filled", "SuccessFactors / careers sites"),
    ("this job is no longer available", ""),
    ("job has expired", ""),
    ("posting has expired", ""),
    ("position is closed", ""),
    ("application deadline has passed", ""),
    ("no longer open", ""),
    ("job is closed", ""),
    ("vacancy has been filled", ""),
]


def ensure_default_sources(job_source_model) -> int:
    """Add every default job source that is missing (matched on connector + token among the site-wide ones). Returns how
    many were added. Existing rows are left exactly as they are, so an admin's pause or rename survives."""
    from tracker.seed_sources import DEFAULT_SOURCES, PUBLIC_OK_CONNECTORS

    # Old migrations call this with the model as it was then, before the public-board switch existed; migration 0040 sets it for them.
    has_public_switch = any(f.name == "show_publicly" for f in job_source_model._meta.get_fields())
    added = 0
    for name, connector, token in DEFAULT_SOURCES:
        defaults = {"name": name, "enabled": True}
        if has_public_switch:
            defaults["show_publicly"] = connector in PUBLIC_OK_CONNECTORS
        _, created = job_source_model.objects.get_or_create(owner=None, connector=connector, board_token=token, defaults=defaults)
        added += int(created)
    return added
