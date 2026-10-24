"""A person's own company job boards for the search.

What makes this safe to open to everyone: the person only ever supplies a connector from a fixed list of single-company
hiring systems and a short name; the app builds the real URL itself against that system's fixed host, so nobody can
point the server at an arbitrary address. The first fetch goes through the same guarded `safe_get` as every scan. A
person's board is searched only for them and is invisible to everyone else (`JobSource.for_user`)."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from .forms import OwnSourceForm
from .models import JobSource, SiteConfig
from .services import scan
from .services.netguard import FetchError
from .views import throttled


def _shared_sources():
    """The site-wide sources that really are searched: Jooble ones only count once the site has a Jooble key."""
    qs = JobSource.objects.filter(owner__isnull=True, enabled=True)
    return qs if SiteConfig.load().effective_jooble_key else qs.exclude(connector="jooble")


@login_required
@require_http_methods(["GET", "POST"])
def sources(request):
    form = OwnSourceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        added = _add(request, form.cleaned_data)
        if added:
            return redirect("sources")
    return render(request, "tracker/sources.html", {
        "config": SiteConfig.load(),
        "form": form,
        "shared": _shared_sources(),
        "mine": JobSource.objects.filter(owner=request.user),
        "limit": settings.STILLOPEN_MAX_OWN_SOURCES,
    })


def _add(request, data) -> bool:
    connector, token, name = data["connector"], data["board_token"], data["name"]
    if JobSource.objects.filter(owner=request.user).count() >= settings.STILLOPEN_MAX_OWN_SOURCES:
        messages.error(request, f"You can add up to {settings.STILLOPEN_MAX_OWN_SOURCES} boards. Remove one first.")
        return False
    if JobSource.objects.filter(owner__isnull=True, connector=connector, board_token=token).exists():
        messages.info(request, "That company is already part of every search, so there is nothing to add.")
        return False
    if JobSource.objects.filter(owner=request.user, connector=connector, board_token=token).exists():
        messages.info(request, "You already added that board.")
        return False
    if throttled(request.user, "source_add", settings.STILLOPEN_SOURCE_ADDS_PER_HOUR):
        messages.error(request, "You have added a lot of boards this hour. Try again later.")
        return False
    try:
        openings = scan._fetch(connector, token)  # the same guarded fetch a scan uses: fixed host, no redirects to private addresses
    except (FetchError, KeyError, ValueError):
        messages.error(request, "We could not read jobs from that board. Check the name against the company's careers page address and try again.")
        return False
    try:
        with transaction.atomic():
            JobSource.objects.create(owner=request.user, name=name[:120], connector=connector, board_token=token)
    except IntegrityError:
        messages.info(request, "You already added that board.")
        return False
    messages.success(request, f"Added {name}. It has {len(openings)} opening{'s' if len(openings) != 1 else ''} right now; your next search will include it.")
    return True


@login_required
@require_POST
def source_action(request, pk, action):
    source = get_object_or_404(JobSource, pk=pk, owner=request.user)  # site-wide boards are admin-only, so they 404 here too
    if action == "delete":
        source.delete()
        messages.success(request, "Removed.")
    elif action == "toggle":
        source.enabled = not source.enabled
        source.save(update_fields=["enabled"])
    else:
        return get_object_or_404(JobSource, pk=0)
    return redirect("sources")
