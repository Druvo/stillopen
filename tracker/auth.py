"""django-allauth adapters: no self-registration, Google sign-in gated by the admin allowlist."""
from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.shortcuts import redirect

from .models import SiteConfig


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return False


def _verified_emails(sociallogin) -> list[str]:
    return [a.email for a in sociallogin.email_addresses if a.verified and a.email]


class SocialAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        config = SiteConfig.load()
        if not config.google_login_enabled:
            messages.error(request, "Google sign-in is turned off.")
            raise ImmediateHttpResponse(redirect("account_login"))
        if sociallogin.is_existing:
            return
        if not any(config.google_email_allowed(e) for e in _verified_emails(sociallogin)):
            messages.error(request, "That Google account is not on the allowed list.")
            raise ImmediateHttpResponse(redirect("account_login"))

    def is_open_for_signup(self, request, sociallogin):
        config = SiteConfig.load()
        return config.google_login_enabled and any(
            config.google_email_allowed(e) for e in _verified_emails(sociallogin)
        )

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        user.is_staff = False  # Google users get the dashboard, never the admin
        user.is_superuser = False
        return user
