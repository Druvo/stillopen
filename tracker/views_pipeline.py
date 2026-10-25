"""What happens after you apply: interviews, the people who can help (contacts and referrals), and offers.

Every row belongs to one person. Lists, forms (their job and contact choices) and actions are all limited to the
signed-in owner, and a row that is not theirs is a 404. Nothing here contacts anyone or sends anything."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .forms import ContactForm, InterviewForm, OfferForm, ReferralForm
from .models import Contact, Interview, Offer, Referral, SiteConfig
from .services import pipeline
from .views_app import new_app_redirect


def _full(request, model) -> bool:
    if pipeline.at_limit(request.user, model):
        messages.error(request, pipeline.limit_message())
        return True
    return False


def _job_param(request) -> str:
    job = request.GET.get("job", "")
    return f"?job={job}" if job.isdigit() else ""


def upcoming_interviews(user, limit: int = 5):
    return list(
        Interview.objects.filter(owner=user, outcome="pending", scheduled_at__gte=timezone.now())
        .select_related("application").order_by("scheduled_at")[:limit]
    )


@login_required
def insights(request):
    if go := new_app_redirect(request, "/insights"):
        return go
    return render(request, "tracker/insights.html", {"config": SiteConfig.load(), "f": pipeline.funnel(request.user)})


# --- interviews ---------------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def interviews(request):
    if request.method == "GET" and (go := new_app_redirect(request, "/interviews" + _job_param(request))):
        return go
    form = InterviewForm(request.POST or None, owner=request.user, initial={"application": request.GET.get("job")})
    if request.method == "POST" and form.is_valid() and not _full(request, Interview):
        pipeline.save_interview(form, request.user)
        messages.success(request, "Interview saved.")
        return redirect("interviews")
    mine = Interview.objects.filter(owner=request.user).select_related("application")
    now = timezone.now()
    return render(request, "tracker/interviews.html", {
        "config": SiteConfig.load(), "form": form,
        "upcoming": [i for i in mine if i.outcome == "pending" and i.scheduled_at >= now],
        "past": [i for i in reversed(list(mine)) if not (i.outcome == "pending" and i.scheduled_at >= now)],
    })


@login_required
@require_POST
def interview_action(request, pk, action):
    item = get_object_or_404(Interview, pk=pk, owner=request.user)
    if action == "delete":
        item.delete()
        messages.success(request, "Deleted.")
    elif action == "outcome":
        if not pipeline.set_interview_outcome(item, request.POST.get("outcome", "")):
            messages.error(request, "Unknown outcome.")
    else:
        return get_object_or_404(Interview, pk=0)
    return redirect("interviews")


# --- contacts and referrals ---------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def contacts(request):
    if request.method == "GET" and (go := new_app_redirect(request, "/contacts")):
        return go
    cform = ContactForm(owner=request.user)
    rform = ReferralForm(owner=request.user)
    if request.method == "POST":
        which = request.POST.get("which")
        if which == "contact":
            cform = ContactForm(request.POST, owner=request.user)
            if cform.is_valid() and not _full(request, Contact):
                pipeline.save_contact(cform, request.user)
                messages.success(request, "Contact saved.")
                return redirect("contacts")
        elif which == "referral":
            rform = ReferralForm(request.POST, owner=request.user)
            if rform.is_valid() and not _full(request, Referral):
                pipeline.save_referral(rform, request.user)
                messages.success(request, "Referral saved.")
                return redirect("contacts")
    people = Contact.objects.filter(owner=request.user).prefetch_related("referrals__application")
    return render(request, "tracker/contacts.html", {
        "config": SiteConfig.load(), "cform": cform, "rform": rform, "people": people,
        "has_people": people.exists(),
    })


@login_required
@require_POST
def contact_delete(request, pk):
    get_object_or_404(Contact, pk=pk, owner=request.user).delete()
    messages.success(request, "Deleted.")
    return redirect("contacts")


@login_required
@require_POST
def referral_action(request, pk, action):
    item = get_object_or_404(Referral.objects.select_related("application", "contact"), pk=pk, owner=request.user)
    if action == "delete":
        item.delete()
    elif action == "status":
        pipeline.set_referral_status(item, request.POST.get("status", ""))
    else:
        return get_object_or_404(Referral, pk=0)
    return redirect("contacts")


# --- offers -------------------------------------------------------------------------------------

comparison = pipeline.comparison


@login_required
@require_http_methods(["GET", "POST"])
def offers(request):
    if request.method == "GET" and (go := new_app_redirect(request, "/offers" + _job_param(request))):
        return go
    form = OfferForm(request.POST or None, owner=request.user, initial={"application": request.GET.get("job")})
    if request.method == "POST" and form.is_valid() and not _full(request, Offer):
        pipeline.save_offer(form, request.user)
        messages.success(request, "Offer saved.")
        return redirect("offers")
    mine = list(Offer.objects.filter(owner=request.user).select_related("application"))
    return render(request, "tracker/offers.html", {
        "config": SiteConfig.load(), "form": form, "offers": mine, "groups": comparison(mine),
    })


@login_required
@require_POST
def offer_action(request, pk, action):
    item = get_object_or_404(Offer.objects.select_related("application"), pk=pk, owner=request.user)
    if action == "delete":
        item.delete()
        messages.success(request, "Deleted.")
    elif action == "status":
        pipeline.set_offer_status(item, request.POST.get("status", ""))
    else:
        return get_object_or_404(Offer, pk=0)
    return redirect("offers")
