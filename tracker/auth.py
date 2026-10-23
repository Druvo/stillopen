"""django-allauth adapters: sign-up follows the admin switch; Google sign-in needs a verified email."""
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.account.utils import has_verified_email
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

from .models import SiteConfig, UserProfile


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return SiteConfig.load().signup_open

    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit)
        if commit:
            UserProfile.objects.update_or_create(user=user, defaults={"self_registered": True})
        return user

    def _home(self, request):
        """A person who has not yet seen the welcome questions starts there; everyone else goes to the dashboard."""
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            profile = UserProfile.objects.filter(user=user).first()
            if profile is not None and not profile.onboarding_done:
                return reverse("welcome")
        return None

    def get_login_redirect_url(self, request):
        return self._home(request) or super().get_login_redirect_url(request)

    def pre_login(self, request, user, **kwargs):
        """People who registered themselves must confirm their email before they get in.

        Accounts made in the admin or with createsuperuser are not self-registered and are never blocked."""
        blocked = super().pre_login(request, user, **kwargs)
        if blocked:
            return blocked
        profile = UserProfile.objects.filter(user=user).first()
        if profile and profile.self_registered and not has_verified_email(user, kwargs.get("email")):
            address = EmailAddress.objects.filter(user=user, verified=False).order_by("-primary", "-pk").first()
            if address:  # we stop the login here, so allauth's own "send at login" stage never runs
                address.send_confirmation(request, signup=bool(kwargs.get("signup")))
            return self.respond_email_verification_sent(request, user)
        return None


def _verified_emails(sociallogin) -> list[str]:
    return [a.email for a in sociallogin.email_addresses if a.verified and a.email]


def _may_register(config: SiteConfig, sociallogin) -> bool:
    """Open sign-up admits any verified Google email; closed sign-up needs the allowlist."""
    emails = _verified_emails(sociallogin)
    if not emails:
        return False
    return config.signup_open or any(config.google_email_allowed(e) for e in emails)


class SocialAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        config = SiteConfig.load()
        if not config.google_login_enabled:
            messages.error(request, "Google sign-in is turned off.")
            raise ImmediateHttpResponse(redirect("account_login"))
        if sociallogin.is_existing:
            return
        if not _may_register(config, sociallogin):
            messages.error(request, "Registration is closed, or that Google account has no verified email.")
            raise ImmediateHttpResponse(redirect("account_login"))

    def is_open_for_signup(self, request, sociallogin):
        config = SiteConfig.load()
        return config.google_login_enabled and _may_register(config, sociallogin)

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        user.is_staff = False  # Google users get the dashboard, never the admin
        user.is_superuser = False
        return user
