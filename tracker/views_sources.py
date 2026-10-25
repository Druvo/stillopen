"""A person's own company job boards for the search.

What makes this safe to open to everyone: the person only ever supplies a connector from a fixed list of single-company
hiring systems and a short name; the app builds the real URL itself against that system's fixed host, so nobody can
point the server at an arbitrary address. The first fetch goes through the same guarded `safe_get` as every scan. A
person's board is searched only for them and is invisible to everyone else (`JobSource.for_user`)."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from .forms import OwnSourceForm
from .models import JobSource, SiteConfig
from .services import ownsources
from .views import throttled
from .views_app import new_app_redirect


def _shared_sources():
    """The site-wide sources that really are searched: Jooble ones only count once the site has a Jooble key."""
    qs = JobSource.objects.filter(owner__isnull=True, enabled=True)
    return qs if SiteConfig.load().effective_jooble_key else qs.exclude(connector="jooble")


@login_required
@require_http_methods(["GET", "POST"])
def sources(request):
    if request.method == "GET" and (go := new_app_redirect(request, "/sources")):
        return go
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
    try:
        _, count = ownsources.add_own_source(
            request.user, connector, token, name, lambda: throttled(request.user, "source_add", settings.STILLOPEN_SOURCE_ADDS_PER_HOUR),
        )
    except ownsources.SourceRefused as refused:
        (messages.info if refused.info else messages.error)(request, str(refused))
        return False
    messages.success(request, f"Added {name}. It has {count} opening{'s' if count != 1 else ''} right now; your next search will include it.")
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
