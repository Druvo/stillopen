"""Free tools nobody needs an account for: a job-fit check, a posting liveness check, and an offer comparison.
Each one reuses the exact same free, zero-token logic the signed-in app uses -- no AI, nothing saved, nothing
sent anywhere beyond the one page the person is asking about (the liveness check fetches that one URL; the
other two never make an outbound request at all). Rate-limited per IP since nobody is signed in here."""
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .forms import JobFitToolForm, LivenessToolForm, OfferToolForm
from .models import SiteConfig
from .services import liveness
from .services.ai import AIError, keyword_match
from .services.pipeline import comparison
from .services.throttle import throttled_ip
from .views_public import public_cache


def _too_many(request) -> HttpResponse:
    return render(request, "tracker/tools_too_many.html", {"config": SiteConfig.load()}, status=429)


@require_http_methods(["GET", "POST"])
def job_fit(request):
    result = error = None
    if request.method == "POST":
        if throttled_ip(request, "tool-job-fit", settings.STILLOPEN_PUBLIC_TOOL_RATE_PER_HOUR):
            return _too_many(request)
        form = JobFitToolForm(request.POST)
        if form.is_valid():
            try:
                result = keyword_match(form.cleaned_data["description"], form.cleaned_data["cv"])
            except AIError as exc:
                error = str(exc)
    else:
        form = JobFitToolForm()
    return render(request, "tracker/tools_job_fit.html", {"config": SiteConfig.load(), "form": form, "result": result, "error": error})


@require_http_methods(["GET", "POST"])
def liveness_check(request):
    result = None
    if request.method == "POST":
        if throttled_ip(request, "tool-liveness", settings.STILLOPEN_PUBLIC_TOOL_RATE_PER_HOUR):
            return _too_many(request)
        form = LivenessToolForm(request.POST)
        if form.is_valid():
            state, detail = liveness.check_url(form.cleaned_data["url"], SiteConfig.load())
            result = {"state": state, "detail": detail}
    else:
        form = LivenessToolForm()
    return render(request, "tracker/tools_liveness.html", {"config": SiteConfig.load(), "form": form, "result": result})


@require_http_methods(["GET", "POST"])
def offer_compare(request):
    groups = None
    if request.method == "POST":
        if throttled_ip(request, "tool-offer-compare", settings.STILLOPEN_PUBLIC_TOOL_RATE_PER_HOUR):
            return _too_many(request)
        form = OfferToolForm(request.POST)
        if form.is_valid():
            groups = comparison(form.offers())
    else:
        form = OfferToolForm()
    return render(request, "tracker/tools_offer_compare.html", {"config": SiteConfig.load(), "form": form, "groups": groups})


@public_cache
def tools_index(request):
    return render(request, "tracker/tools_index.html", {"config": SiteConfig.load()})
