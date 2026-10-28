"""Draft ahead: after a scheduled search, prepare tailored CV drafts for the person's best new matches.

Opt-in at two levels (SiteConfig.draft_ahead_site_enabled, then UserProfile.draft_ahead_enabled). It reuses the normal
tailoring path (`cvgen.tailor`, fact check included), so a draft comes out exactly like a manual one: flagged when it
states something the person's own material does not support, never approved, never exported, nothing sent. The person
reviews it on the dashboard and approves or discards it. A job never gets a second draft."""
import logging

from django.conf import settings

from tracker.models import Application, CVVersion, ScoreBand, SiteConfig, UserProfile
from tracker.services import cvgen, notifications
from tracker.services.cvversions import CVError

log = logging.getLogger(__name__)

NEEDS_NO_KEY = ("claude_cli", "agent_sdk", "openai")  # a local model or the CLI's own login can work without a key


def skip_reason(site: SiteConfig, config: SiteConfig, profile: UserProfile) -> str:
    """Plain words for why nothing is prepared for this person right now, "off" when they never asked, or "" when drafts can be made."""
    if not site.draft_ahead_site_enabled or not profile.draft_ahead_enabled:
        return "off"
    if config.ai_provider == "none" or (config.ai_provider not in NEEDS_NO_KEY and not config.effective_ai_key):
        return "Draft ahead skipped: set up your AI under Profile > AI settings first."
    if not config.effective_profile_cv.strip():
        return "Draft ahead skipped: add your CV under Profile first."
    return ""


def candidates(owner, run, config: SiteConfig) -> list[Application]:
    """This run's new jobs in the top score band that have no tailored CV yet, best first."""
    band = ScoreBand.objects.first()  # ordered highest threshold first
    if band is None or not run.added_ids:
        return []
    apps = (
        Application.objects.filter(owner=owner, pk__in=run.added_ids)
        .exclude(cv_versions__kind="tailored")
        .order_by("-score", "pk")
    )
    return [a for a in apps if (a.match_percent(config.score_scale) or -1) >= band.min_percent]


def prepare(owner, run) -> int:
    """Make up to STILLOPEN_DRAFT_AHEAD_MAX drafts for the jobs `run` added. Returns how many were made. Never raises:
    one job failing does not stop the others, and why nothing was made is written on the run's note."""
    site = SiteConfig.load()
    profile = UserProfile.for_user(owner)
    config = SiteConfig.for_user(owner)
    reason = skip_reason(site, config, profile)
    if reason:
        if reason != "off":
            _note(run, reason)
        return 0
    cap = max(0, settings.STILLOPEN_DRAFT_AHEAD_MAX)
    try:
        todo = candidates(owner, run, config)[:cap]
    except Exception:  # noqa: BLE001 - the search itself already succeeded
        log.exception("draft ahead: could not pick jobs for %s", owner.pk)
        return 0
    made = failed = 0
    for app in todo:
        try:
            version = cvgen.tailor(app, config, "ai")
        except CVError as exc:
            failed += 1
            log.info("draft ahead: no draft for job %s: %s", app.pk, exc)
            continue
        except Exception:  # noqa: BLE001 - one job failing must not stop the rest
            failed += 1
            log.exception("draft ahead: job %s failed", app.pk)
            continue
        CVVersion.objects.filter(pk=version.pk).update(draft_ahead=True)
        made += 1
    if made or failed:
        text = f"Draft ahead: {made} CV draft{'s' if made != 1 else ''} ready for your review"
        text += f"; {failed} could not be made." if failed else "."
        _note(run, text)
    notifications.drafts_waiting(owner, made)
    return made


def _note(run, text: str) -> None:
    run.note = f"{run.note} {text}".strip()
    run.save(update_fields=["note"])


def waiting(owner):
    """Drafts the person has not approved or discarded yet (owner-only)."""
    return CVVersion.objects.filter(owner=owner, kind="tailored", draft_ahead=True, approved=False).select_related("application")


def digest_line(owner) -> str:
    count = waiting(owner).count()
    if not count:
        return ""
    return f"{count} draft{'s are' if count != 1 else ' is'} waiting for your review."
