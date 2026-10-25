"""The job card the dashboard shows: match percent, band, deadline flags, fit and the other facts one row needs."""
from . import fit as fit_service
from . import scan


def band_for(percent, bands):
    if percent is None:
        return None
    for band in bands:  # ordered highest threshold first
        if percent >= band.min_percent:
            return band
    return None


def card_for(app, config, bands, areas=None, profile=None, reposts=None, today=None):
    """`reposts` is the batch from `scan.repost_signals` (one lookup for the whole page); without it each card looks its own up."""
    percent = app.match_percent(config.score_scale)
    fit = fit_service.fit_flags(app, areas if areas is not None else [], profile)
    band = band_for(percent, bands)
    days = app.days_left(today)
    return {
        "app": app,
        "percent": percent,
        "band": band,
        "days_left": days,
        "urgent": days is not None and 0 <= days <= config.urgent_days,
        "overdue": days is not None and days < 0,
        "strengths": [i for i in app.insights.all() if i.kind == "strength"],
        "gaps": [i for i in app.insights.all() if i.kind == "gap"],
        "documents": list(app.documents.all()),
        "cv": next(iter(app.cv_versions.all()), None),
        "fit": fit,
        "fit_level": fit_service.summary_level(fit),
        "fit_text": " ".join(f["text"] for f in fit if f["level"] != "ok") or " ".join(f["text"] for f in fit),
        "repost": (reposts.get(app.posting_id) if reposts is not None else scan.repost_signal(app.posting)) if app.posting_id else None,
        "skill_matched": any(e.kind == "note" and "skill match" in e.text for e in app.events.all()),
    }
