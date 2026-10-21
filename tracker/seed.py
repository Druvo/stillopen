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

SCORE_BANDS = [("Strong", 80, "#3ecf8e"), ("Fair", 70, "#f5b642"), ("Weak", 0, "#f16565")]

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
