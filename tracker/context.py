from django.conf import settings

from . import legal
from .models import SiteConfig
from .services import integrations


def site_config(request):
    config = SiteConfig.load()
    return {
        "site_config": config, "google_login_on": config.google_login_enabled,
        # providers the owner switched on; a button also needs the provider's app configured (the templates check both)
        "enabled_social": [p for p in ("google", "github", "facebook") if config.social_enabled(p)],
        # an admin should know when sign-ups are not email-verified because this install cannot send email
        "require_email_confirmation": integrations.require_email_confirmation(),
        # sign-up is open but /privacy/ or /terms/ still has [blanks] to fill in
        "legal_needs_attention": config.signup_open and (legal.has_placeholders(config.privacy_text) or legal.has_placeholders(config.terms_text)),
        "email_unverified_signups": config.signup_open and not integrations.require_email_confirmation(),
    }
