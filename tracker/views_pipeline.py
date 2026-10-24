"""What happens after you apply: interviews, the people who can help (contacts and referrals), and offers.

Every row belongs to one person. Lists, forms (their job and contact choices) and actions are all limited to the
signed-in owner, and a row that is not theirs is a 404. Nothing here contacts anyone or sends anything."""
from collections import defaultdict
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .forms import ContactForm, InterviewForm, OfferForm, ReferralForm
from .models import Contact, Event, Interview, Offer, Referral, SiteConfig


def _full(request, model) -> bool:
    if model.objects.filter(owner=request.user).count() >= settings.STILLOPEN_MAX_PIPELINE:
        messages.error(request, f"You have reached the limit of {settings.STILLOPEN_MAX_PIPELINE} saved items here. Delete some first.")
        return True
    return False


def upcoming_interviews(user, limit: int = 5):
    return list(
        Interview.objects.filter(owner=user, outcome="pending", scheduled_at__gte=timezone.now())
        .select_related("application").order_by("scheduled_at")[:limit]
    )


# --- interviews ---------------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def interviews(request):
    form = InterviewForm(request.POST or None, owner=request.user, initial={"application": request.GET.get("job")})
    if request.method == "POST" and form.is_valid() and not _full(request, Interview):
        item = form.save(commit=False)
        item.owner = request.user
        item.save()
        Event.objects.create(
            application=item.application, kind="interview",
            text=f"{item.get_kind_display()} scheduled for {timezone.localtime(item.scheduled_at):%d %b %Y %H:%M}",
        )
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
        outcome = request.POST.get("outcome", "")
        if outcome not in dict(Interview.OUTCOMES):
            messages.error(request, "Unknown outcome.")
        else:
            item.outcome = outcome
            item.save(update_fields=["outcome"])
            Event.objects.create(application=item.application, kind="interview", text=f"{item.get_kind_display()}: {item.get_outcome_display()}")
    else:
        return get_object_or_404(Interview, pk=0)
    return redirect("interviews")


# --- contacts and referrals ---------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def contacts(request):
    cform = ContactForm(owner=request.user)
    rform = ReferralForm(owner=request.user)
    if request.method == "POST":
        which = request.POST.get("which")
        if which == "contact":
            cform = ContactForm(request.POST, owner=request.user)
            if cform.is_valid() and not _full(request, Contact):
                item = cform.save(commit=False)
                item.owner = request.user
                item.save()
                messages.success(request, "Contact saved.")
                return redirect("contacts")
        elif which == "referral":
            rform = ReferralForm(request.POST, owner=request.user)
            if rform.is_valid() and not _full(request, Referral):
                item = rform.save(commit=False)
                item.owner = request.user
                item.save()
                Event.objects.create(
                    application=item.application, kind="note",
                    text=f"Referral with {item.contact.name}: {item.get_status_display()}",
                )
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
        status = request.POST.get("status", "")
        if status in dict(Referral.STATUSES):
            item.status = status
            item.save(update_fields=["status"])
            Event.objects.create(
                application=item.application, kind="note",
                text=f"Referral with {item.contact.name}: {item.get_status_display()}",
            )
    else:
        return get_object_or_404(Referral, pk=0)
    return redirect("contacts")


# --- offers -------------------------------------------------------------------------------------

def comparison(offers):
    """Offers grouped by currency (no exchange rates are guessed), best yearly total first, with the gap to the best."""
    groups = defaultdict(list)
    for offer in offers:
        if offer.status != "declined":
            groups[offer.currency].append(offer)
    out = []
    for currency in sorted(groups):
        rows = sorted(groups[currency], key=lambda o: o.yearly_total, reverse=True)
        best = rows[0].yearly_total
        out.append({
            "currency": currency,
            "rows": [{"offer": o, "behind": best - o.yearly_total if best > o.yearly_total else Decimal(0), "best": o is rows[0] and len(rows) > 1} for o in rows],
        })
    return out


@login_required
@require_http_methods(["GET", "POST"])
def offers(request):
    form = OfferForm(request.POST or None, owner=request.user, initial={"application": request.GET.get("job")})
    if request.method == "POST" and form.is_valid() and not _full(request, Offer):
        item = form.save(commit=False)
        item.owner = request.user
        item.save()
        Event.objects.create(application=item.application, kind="note", text="Offer recorded")
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
        status = request.POST.get("status", "")
        if status in dict(Offer.STATUSES):
            item.status = status
            item.save(update_fields=["status"])
            Event.objects.create(application=item.application, kind="note", text=f"Offer: {item.get_status_display()}")
    else:
        return get_object_or_404(Offer, pk=0)
    return redirect("offers")
