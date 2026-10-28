"""Putting a "My data" export file back into the SAME account: profile answers, the CV history, cover letters and job notes.

A merge, never a replace. Nothing that is already there is changed or removed:
- a profile answer is filled in only where the account's own is still empty (a different one is kept and listed);
- a master CV is added only when no CV version with the same text exists, and it is dated as in the file, so an older CV never becomes the
  current one;
- a cover letter is added (unapproved, fact check re-run) only for a job with the same company and role that has no letter with that text;
- a job note is filled in only where the job's own note is empty.

The file is untrusted: it must be one of our exports, from this account, under the size cap; every value is type-checked, cleaned and
clamped; unknown keys are ignored; it holds no paths or secrets, and none is ever read from it. `read(..., preview=True)` says what would
happen and writes nothing; the real pass uses the same rules, so the preview is what the import does."""
import json
from datetime import datetime
from datetime import timezone as dt_timezone

from django.conf import settings
from django.db import transaction
from django.utils.dateparse import parse_datetime

from tracker.models import Application, CoverLetter, CVVersion, SiteConfig, UserProfile
from tracker.services import coverletter, cvversions, dataexport, tz
from tracker.services.cvversions import CVError

MAX_BYTES = 8 * 1024 * 1024
MAX_ITEMS = 500  # per section; the rest is counted as "left out"
PROFILE_TEXT = {"target_roles": 4000, "industries": 2000, "languages": 2000, "notice_period": 60, "salary_floor": 60, "deal_breakers": 4000, "about": 6000}
LABELS = {
    "target_roles": "roles you want", "industries": "industries", "languages": "languages", "notice_period": "notice period", "salary_floor": "minimum pay",
    "deal_breakers": "deal breakers", "about": "about you", "home_country": "home country", "timezone": "time zone", "employment_types": "kinds of employment",
    "seniority_levels": "seniority",
}


class ImportProblem(Exception):
    """The whole file is unusable; the message says why in plain words."""


def parse(raw: bytes, user) -> dict:
    """The file as a dict, or ImportProblem. Refuses anything that is not one of our exports from this account."""
    if len(raw) > MAX_BYTES:
        raise ImportProblem("That file is bigger than 8 MB, so it is not one of our exports. Choose the file you downloaded from \"Export my data\".")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise ImportProblem("We could not read that file. Choose the .json file you downloaded from \"Export my data\".") from None
    if not isinstance(data, dict) or data.get("format") != dataexport.FORMAT:
        raise ImportProblem("That is not a StillOpen export. Choose the .json file you downloaded from \"Export my data\" (files made before this feature cannot be imported).")
    version = data.get("format_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1 or version > dataexport.VERSION:
        raise ImportProblem("That export was made by a newer version of StillOpen. Update the app, or export again.")
    account = data.get("account")
    name = account.get("username") if isinstance(account, dict) else None
    if not isinstance(name, str) or name != user.get_username():
        raise ImportProblem("This file was exported from a different account. For safety it can only be added back to the account it came from.")
    return data


def _text(value, limit: int) -> str:
    return value.replace("\x00", "").strip()[:limit] if isinstance(value, str) else ""


def _items(value) -> tuple[list[dict], int]:
    """(the first MAX_ITEMS dicts of a list, how many more were left out)."""
    if not isinstance(value, list):
        return [], 0
    return [x for x in value[:MAX_ITEMS] if isinstance(x, dict)], max(0, len(value) - MAX_ITEMS)


def _when(value) -> datetime | None:
    try:
        moment = parse_datetime(value) if isinstance(value, str) and len(value) < 40 else None
    except ValueError:
        return None
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=dt_timezone.utc)


def _key(company_role: str) -> str:
    return " ".join(company_role.lower().split())


def _fill(profile, field: str, incoming, changes: dict, report: dict) -> None:
    if not incoming:
        return
    current = getattr(profile, field)
    if not current:
        changes[field] = incoming
    elif current != incoming:
        report["profile"]["kept"].append(LABELS[field])


def _profile(profile: UserProfile, section: dict, report: dict, apply: bool) -> None:
    changes: dict = {}
    for field, limit in PROFILE_TEXT.items():
        _fill(profile, field, _text(section.get(field), limit), changes, report)
    code = _text(section.get("home_country"), 8).upper()
    _fill(profile, "home_country", code if len(code) == 2 and code.isalpha() else "", changes, report)
    zone = _text(section.get("timezone"), 64)
    _fill(profile, "timezone", zone if zone and tz.is_valid(zone) else "", changes, report)
    for field, choices in (("employment_types", UserProfile.EMPLOYMENT), ("seniority_levels", UserProfile.SENIORITY)):
        allowed = {c[0] for c in choices}
        picked = section.get(field)
        picked = [x for x in picked if isinstance(x, str) and x in allowed] if isinstance(picked, list) else []
        _fill(profile, field, sorted(set(picked)), changes, report)
    report["profile"]["filled"] = [LABELS[f] for f in changes]
    if apply and changes:
        for field, value in changes.items():
            setattr(profile, field, value)
        profile.save(update_fields=list(changes))


def _cvs(user, data: dict, report: dict, preview: bool) -> None:
    """Master versions only: a tailored one belongs to a job and its fact-check, so it is not brought back."""
    versions, extra = _items(data.get("cv_versions"))
    report["left_out"] += extra
    have = {v.strip() for v in CVVersion.objects.filter(owner=user).values_list("content", flat=True)}
    count = CVVersion.objects.filter(owner=user).count()
    wanted = []
    for index, item in enumerate(versions):
        if item.get("kind") != "master":
            continue
        try:
            content = cvversions.clean_content(item.get("content") if isinstance(item.get("content"), str) else "")
        except CVError:
            report["cvs"]["left_out"] += 1
            continue
        if content in have:
            report["cvs"]["have"] += 1
            continue
        have.add(content)
        wanted.append((_when(item.get("created")), -index, _text(item.get("label"), 100), content))  # our export lists newest first, so a tie keeps that order
    wanted.sort(key=lambda w: (w[0] or datetime.min.replace(tzinfo=dt_timezone.utc), w[1]))
    for created, _, label, content in wanted:
        if count >= settings.STILLOPEN_MAX_CV_VERSIONS:
            report["cvs"]["stopped"] = f"You have reached the limit of {settings.STILLOPEN_MAX_CV_VERSIONS} CV versions, so the rest were left out."
            break
        count += 1
        report["cvs"]["add"] += 1
        if not preview:
            made = CVVersion.objects.create(owner=user, kind="master", source="restored", content=content, label=f"{label or 'CV'} (from your export)"[:140], approved=True)
            if created:
                CVVersion.objects.filter(pk=made.pk).update(created_at=created)  # keeps the history in order; an older CV never becomes the current one


def _letters_and_notes(user, config, data: dict, report: dict, preview: bool) -> None:
    mine: dict[str, list[Application]] = {}
    for app in Application.objects.filter(owner=user):
        mine.setdefault(_key(f"{app.company} - {app.role}"), []).append(app)
    letters, extra = _items(data.get("cover_letters"))
    report["left_out"] += extra
    covers = CoverLetter.objects.filter(owner=user)
    have = {(c.application_id, c.content.strip()) for c in covers}
    total = covers.count()
    for item in letters:
        apps = mine.get(_key(_text(item.get("for_job"), 300)), [])
        content = _text(item.get("content"), 20000)
        if not content:
            continue
        if len(apps) != 1:
            report["covers"]["no_job"] += 1
            continue
        app = apps[0]
        if (app.pk, content) in have:
            report["covers"]["have"] += 1
            continue
        if total >= settings.STILLOPEN_MAX_CV_VERSIONS:
            report["covers"]["stopped"] = "You have reached the limit of saved cover letters, so the rest were left out."
            break
        have.add((app.pk, content))
        total += 1
        report["covers"]["add"] += 1
        if not preview:  # unapproved, with the fact check run again on the person's own material
            CoverLetter.objects.create(owner=user, application=app, content=content, source="manual", check_report=coverletter._check(user, config, app, content))
    applications, extra = _items(data.get("applications"))
    report["left_out"] += extra
    for item in applications:
        note = _text(item.get("notes"), 5000)
        if not note:
            continue
        apps = mine.get(_key(f"{_text(item.get('company'), 200)} - {_text(item.get('role'), 200)}"), [])
        if len(apps) != 1:
            report["notes"]["no_job"] += 1
        elif not apps[0].notes.strip():
            report["notes"]["add"] += 1
            if not preview:
                Application.objects.filter(pk=apps[0].pk).update(notes=note)
            apps[0].notes = note  # a second entry for the same job in one file must not be counted or written twice
        elif apps[0].notes.strip() == note:
            report["notes"]["have"] += 1
        else:
            report["notes"]["kept"] += 1


def read(user, raw: bytes, preview: bool = True) -> dict:
    """What the file would add (preview) or what it added. Counts and short lists of names only."""
    data = parse(raw, user)
    report = {
        "preview": preview, "profile": {"filled": [], "kept": []},
        "cvs": {"add": 0, "have": 0, "left_out": 0, "stopped": ""}, "covers": {"add": 0, "have": 0, "no_job": 0, "stopped": ""},
        "notes": {"add": 0, "have": 0, "kept": 0, "no_job": 0}, "left_out": 0,
    }
    with transaction.atomic():
        if isinstance(data.get("profile"), dict):
            _profile(UserProfile.for_user(user), data["profile"], report, apply=not preview)
        _cvs(user, data, report, preview)
        _letters_and_notes(user, SiteConfig.for_user(user), data, report, preview)
    report["nothing"] = not (report["profile"]["filled"] or report["cvs"]["add"] or report["covers"]["add"] or report["notes"]["add"])
    return report
