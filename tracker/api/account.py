"""Account and profile for the new app: who the person is, what they are looking for, where they would work, the welcome questions
and deleting the account. The classic pages' own forms do the checking, so every rule (country names, CV size, search area limits) stays in one place.

A CV can arrive as a file: the profile and welcome saves accept JSON, or multipart when a `cv_file` is attached."""
import json

from django.conf import settings
from django.contrib.auth import logout
from django.db.models import Max
from django.urls import reverse
from ninja import Router
from ninja.errors import HttpError

from .. import forms
from ..models import Application, KnowledgeSource, SearchArea, SiteConfig, UserProfile
from ..services import account as account_service, links, tz
from .common import owned, validate_form

router = Router()

LIST_FIELDS = {"employment_types", "seniority_levels"}


def read_payload(request):
    """(data, files) from a JSON body, or from a multipart form when a file is attached."""
    if (request.content_type or "").startswith("multipart/form-data"):
        data = {key: (request.POST.getlist(key) if key in LIST_FIELDS else request.POST.get(key)) for key in request.POST}
        return data, request.FILES
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        raise HttpError(400, "We could not read what was sent. Please try again.") from None
    if not isinstance(data, dict):
        raise HttpError(400, "We could not read what was sent. Please try again.")
    return data, None


def merged(unbound_form, data: dict) -> dict:
    """What the form should see: the saved values, with what was sent laid over them (so a partial save never blanks the rest)."""
    return {**unbound_form.initial, **data}


def area_json(area: SearchArea) -> dict:
    return {
        "id": area.pk, "place": area.place, "city": area.city, "allow_remote": area.allow_remote, "allow_hybrid": area.allow_hybrid,
        "allow_onsite": area.allow_onsite, "needs_visa_sponsorship": area.needs_visa_sponsorship, "needs_relocation_support": area.needs_relocation_support,
        "min_salary": area.min_salary, "salary_currency": area.salary_currency, "salary_period": area.salary_period, "description": area.describe(),
    }


def _profile_json(user) -> dict:
    profile = UserProfile.for_user(user)
    initial = forms.ProfileForm(instance=profile).initial  # home_country as a name, like the classic page
    site = SiteConfig.load()
    documents = KnowledgeSource.objects.filter(owner=user).exclude(key__in=["profile-cv", "careerops:cv.md"]).count()
    areas = list(user.search_areas.all())
    return {
        "profile": {
            "target_roles": profile.target_roles, "home_country": initial.get("home_country", ""), "employment_types": profile.employment_types,
            "seniority_levels": profile.seniority_levels, "industries": profile.industries, "languages": profile.languages,
            "notice_period": profile.notice_period, "salary_floor": profile.salary_floor, "deal_breakers": profile.deal_breakers,
            "about": profile.about, "profile_cv": profile.profile_cv, "scan_digest_enabled": profile.scan_digest_enabled, "draft_ahead_enabled": profile.draft_ahead_enabled,
            "timezone": profile.timezone,
            "email_followups": profile.email_followups, "email_interviews": profile.email_interviews, "email_weekly": profile.email_weekly,
            "weekly_digest_enabled": profile.weekly_digest_enabled,
        },
        "choices": {
            "employment_types": [{"value": v, "label": label} for v, label in UserProfile.EMPLOYMENT],
            "seniority_levels": [{"value": v, "label": label} for v, label in UserProfile.SENIORITY],
            "salary_periods": [{"value": v, "label": label} for v, label in SearchArea.PERIODS],
            "timezones": tz.COMMON_ZONES,
        },
        "areas": [area_json(a) for a in areas],
        "max_areas": forms.MAX_AREAS,
        "site": {
            "scan_emails_enabled": site.scan_emails_enabled, "followup_emails_enabled": site.followup_emails_enabled,
            "weekly_emails_enabled": site.weekly_emails_enabled, "weekly_digest_site_enabled": site.weekly_digest_site_enabled, "draft_ahead_site_enabled": site.draft_ahead_site_enabled, "assistant_enabled": site.mcp_remote_enabled,
            "timezone": settings.TIME_ZONE,
        },
        "account": {
            "username": user.get_username(), "email": user.email, "email_verified": links.verified_address(user), "is_staff": user.is_staff, "can_delete": not user.is_staff,
            "google": user.socialaccount_set.filter(provider="google").exists(),
            "counts": {
                "jobs": Application.objects.filter(owner=user).count(), "cv_versions": user.cv_versions.count(),
                "documents": documents, "search_areas": len(areas),
            },
            "classic": {
                "email": reverse("account_email"), "password": reverse("account_change_password"), "two_step": reverse("mfa_index"),
                "connections": reverse("socialaccount_connections"), "export": reverse("export_data"), "privacy": reverse("privacy"),
            },
        },
    }


@router.get("/profile", summary="The person's profile, search areas and account")
def get_profile(request):
    return _profile_json(request.user)


def _save_profile(request):
    from ..services.account import save_cv_history

    data, files = read_payload(request)
    obj = UserProfile.for_user(request.user)
    form = forms.ProfileForm(merged(forms.ProfileForm(instance=obj), data), files, instance=obj)
    validate_form(form)
    form.save()
    save_cv_history(request.user, obj, form)
    return _profile_json(request.user)


@router.put("/profile", summary="Save the profile (JSON)")
def save_profile(request):
    return _save_profile(request)


@router.post("/profile", summary="Save the profile with a CV file attached (multipart; the text is read from the file, the file is not kept)")
def save_profile_with_file(request):
    return _save_profile(request)


# --- search areas ----------------------------------------------------------------------------------

def _save_area(request, form, area=None):
    validate_form(form)
    if area is None:
        area = form.save(commit=False)
        area.owner = request.user
        area.order = (request.user.search_areas.aggregate(top=Max("order"))["top"] or 0) + 1
        area.save()
    else:
        form.save()
    out = {"area": area_json(area)}
    if form.unrecognised:
        out["warning"] = f'"{area.place}" is not a place we recognise, so jobs are matched to it by name only.'
    return out


@router.post("/profile/areas", summary="Add a place the person would work")
def add_area(request):
    if request.user.search_areas.count() >= forms.MAX_AREAS:
        raise HttpError(400, f"You can have at most {forms.MAX_AREAS} search areas.")
    data, _ = read_payload(request)
    data.setdefault("salary_period", "month")
    return _save_area(request, forms.SearchAreaForm(data))


@router.patch("/profile/areas/{area_id}", summary="Change one search area")
def change_area(request, area_id: int):
    area = owned(SearchArea, request, area_id)
    data, _ = read_payload(request)
    return _save_area(request, forms.SearchAreaForm(merged(forms.SearchAreaForm(instance=area), data), instance=area), area)


@router.delete("/profile/areas/{area_id}", summary="Remove one search area")
def delete_area(request, area_id: int):
    owned(SearchArea, request, area_id).delete()
    return {"ok": True}


# --- the welcome questions -------------------------------------------------------------------------

@router.get("/welcome", summary="The three first questions and what is already answered")
def get_welcome(request):
    profile = UserProfile.for_user(request.user)
    initial = forms.ProfileForm(instance=profile).initial
    return {
        "done": profile.onboarding_done,
        "target_roles": profile.target_roles, "home_country": initial.get("home_country", ""), "profile_cv": profile.profile_cv,
        "open_remote": True, "other_places": "",
    }


@router.post("/welcome", summary="Save the welcome answers")
def save_welcome(request):
    from ..services.account import save_cv_history

    data, files = read_payload(request)
    obj = UserProfile.for_user(request.user)
    data.setdefault("open_remote", True)
    form = forms.WelcomeForm(merged(forms.WelcomeForm(instance=obj), data), files, instance=obj)
    validate_form(form)
    form.save()
    save_cv_history(request.user, obj, form)
    forms.create_default_areas(request.user, obj.home_country, form.cleaned_data.get("open_remote", False), form.cleaned_data.get("other_places", ""))
    obj.onboarding_done = True
    obj.save(update_fields=["onboarding_done"])
    return {"ok": True}


@router.post("/welcome/skip", summary="Skip the welcome questions")
def skip_welcome(request):
    obj = UserProfile.for_user(request.user)
    obj.onboarding_done = True
    obj.save(update_fields=["onboarding_done"])
    return {"ok": True}


# --- delete the account ----------------------------------------------------------------------------

@router.post("/account/delete", summary="Delete the account and everything in it (type the username to confirm)")
def delete_account(request):
    user = request.user
    if user.is_staff:
        raise HttpError(400, "Site admin accounts cannot be deleted here. Ask another admin.")
    data, _ = read_payload(request)
    if str(data.get("confirm", "")).strip() != user.get_username():
        raise HttpError(400, "Type your username exactly to confirm.")
    account_service.delete_stored_files(user)
    logout(request)
    user.delete()  # cascades to profile, applications, knowledge, events, runs
    return {"ok": True}
