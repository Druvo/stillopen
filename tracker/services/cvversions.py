"""CV version history: record, edit, restore, approve. Versions are immutable; every change is a new row."""
from django.conf import settings
from django.utils import timezone

from tracker.models import CVVersion, KnowledgeSource, SiteConfig, UserProfile
from tracker.services.factcheck import fact_check

MAX_CONTENT = 30000


class CVError(Exception):
    pass


def source_texts(owner, config: SiteConfig) -> list[str]:
    """Everything the person has written about themselves: what a tailored CV may draw on."""
    texts = [config.effective_profile_cv]
    texts += list(KnowledgeSource.objects.filter(owner=owner, enabled=True).values_list("text", flat=True))
    return [t for t in texts if t and t.strip()]


def check_quota(owner) -> None:
    if CVVersion.objects.filter(owner=owner).count() >= settings.STILLOPEN_MAX_CV_VERSIONS:
        raise CVError(f"You have reached the limit of {settings.STILLOPEN_MAX_CV_VERSIONS} CV versions. Delete old tailored ones first.")


def clean_content(content: str) -> str:
    content = (content or "").replace("\x00", "").strip()
    if not content:
        raise CVError("The CV is empty.")
    if len(content) > MAX_CONTENT:
        raise CVError("That CV is longer than 30,000 characters.")
    return content


def latest_master(owner) -> CVVersion | None:
    return CVVersion.objects.filter(owner=owner, kind="master").first()


def record_master(owner, text: str, label: str = "", source: str = "manual") -> CVVersion:
    """Add a master version unless the text equals the latest one (no duplicate history entries)."""
    text = clean_content(text)
    current = latest_master(owner)
    if current and current.content.strip() == text:
        return current
    check_quota(owner)
    return CVVersion.objects.create(
        owner=owner, kind="master", source=source, parent=current, content=text,
        label=label or ("Initial CV" if current is None else "Edited CV"), approved=True,
    )


def ensure_master(owner, config: SiteConfig) -> CVVersion:
    """The version a tailored CV is based on; created from the profile CV the first time."""
    current = latest_master(owner)
    text = config.effective_profile_cv
    if current is None or (text.strip() and current.content.strip() != text.strip()):
        if not text.strip():
            raise CVError("Add your CV in Profile first.")
        return record_master(owner, text)
    return current


def new_version_from_edit(version: CVVersion, content: str, config: SiteConfig, label: str = "") -> CVVersion:
    """Save an edit as a new version. A tailored edit is fact-checked again and needs approval if anything is flagged."""
    content = clean_content(content)
    if content == version.content.strip():
        return version
    check_quota(version.owner)
    if version.kind == "master":
        created = CVVersion.objects.create(
            owner=version.owner, kind="master", source="manual", parent=version, content=content,
            label=label or "Edited CV", approved=True,
        )
        UserProfile.objects.filter(user=version.owner).update(profile_cv=content)
        return created
    findings = fact_check(content, source_texts(version.owner, config), version.job_snapshot)
    return CVVersion.objects.create(
        owner=version.owner, application=version.application, parent=version, kind="tailored", source="manual",
        content=content, job_snapshot=version.job_snapshot, check_report=findings,
        label=label or f"{version.label} (edited)"[:140],
    )


def restore(version: CVVersion) -> CVVersion:
    """Make an earlier master version the current CV again. History is kept: this adds a new version."""
    if version.kind != "master":
        raise CVError("Only master CV versions can be restored. Open a tailored version and use it, or edit it.")
    check_quota(version.owner)
    created = CVVersion.objects.create(
        owner=version.owner, kind="master", source="restored", parent=latest_master(version.owner),
        content=version.content, label=f"Restored: {version.label}"[:140], approved=True,
    )
    UserProfile.objects.filter(user=version.owner).update(profile_cv=version.content)
    return created


def approve(version: CVVersion) -> CVVersion:
    version.approved = True
    version.approved_at = timezone.now()
    version.save(update_fields=["approved", "approved_at"])
    return version
