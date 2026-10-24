from django.conf import settings

from . import legal
from .models import SiteConfig


def site_config(request):
    config = SiteConfig.load()
    return {
        "site_config": config, "google_login_on": config.google_login_enabled,
        # an admin should know when sign-ups are not email-verified because this install cannot send email
        "require_email_confirmation": settings.STILLOPEN_REQUIRE_EMAIL_CONFIRMATION,
        # sign-up is open but /privacy/ or /terms/ still has [blanks] to fill in
        "legal_needs_attention": config.signup_open and (legal.has_placeholders(config.privacy_text) or legal.has_placeholders(config.terms_text)),
        "email_unverified_signups": config.signup_open and not settings.STILLOPEN_REQUIRE_EMAIL_CONFIRMATION,
    }
