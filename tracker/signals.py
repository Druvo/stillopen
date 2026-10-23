from allauth.account.signals import email_confirmed
from django.contrib.auth import get_user_model, login
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=get_user_model())
def on_user_created(sender, instance, created, raw=False, **kwargs):
    if not created or raw:
        return
    from .services import claim

    UserProfile.for_user(instance)
    # The first account on an install that predates accounts inherits the existing data.
    if get_user_model().objects.count() == 1 and claim.has_orphans():
        claim.claim_orphans(instance)


@receiver(email_confirmed)
def sign_in_after_first_confirmation(sender, request, email_address, **kwargs):
    """The confirmation link is the whole sign-up: the first time it is used it also signs the person in.

    Only for people who registered themselves, and only when this click is what verified the address; a second click
    finds it already verified and this signal never fires, so a mailed link cannot sign anyone in over and over."""
    if request is None or request.user.is_authenticated:
        return
    profile = UserProfile.objects.filter(user=email_address.user).first()
    if profile is None or not profile.self_registered or not email_address.user.is_active:
        return
    login(request, email_address.user, backend="allauth.account.auth_backends.AuthenticationBackend")
