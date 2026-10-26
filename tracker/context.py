from django.conf import settings

from . import legal
from .models import JobSource, SiteConfig
from .services import integrations


def staff_flags(config) -> dict:
    """The warnings an admin sees: sign-up is open but email confirmation is off, the legal pages still have
    [blanks], or a Jooble source is enabled site-wide but sitting dormant for lack of a key."""
    return {
        # sign-up is open but /privacy/ or /terms/ still has [blanks] to fill in
        "legal_needs_attention": config.signup_open and (legal.has_placeholders(config.privacy_text) or legal.has_placeholders(config.terms_text)),
        # an admin should know when sign-ups are not email-verified because this install cannot send email
        "email_unverified_signups": config.signup_open and not integrations.require_email_confirmation(),
        # neither Jooble nor Adzuna has a key, so whole countries have no job search behind them
        "no_search_keys": not config.effective_jooble_key and not (config.effective_adzuna_id and config.effective_adzuna_key),
        # fetch_jooble() silently returns [] with no key -- a site-wide Jooble source otherwise just looks
        # permanently empty in the scan log, with nothing telling the admin why
        "jooble_sources_dormant": (
            not config.effective_jooble_key
            and JobSource.objects.filter(owner__isnull=True, connector="jooble", enabled=True).exists()
        ),
        # same for fetch_usajobs(), which needs both a key AND the registered email
        "usajobs_sources_dormant": (
            not (config.effective_usajobs_key and config.effective_usajobs_email)
            and JobSource.objects.filter(owner__isnull=True, connector="usajobs", enabled=True).exists()
        ),
    }


def site_config(request):
    config = SiteConfig.load()
    return {
        "site_config": config, "google_login_on": config.google_login_enabled,
        # providers the owner switched on; a button also needs the provider's app configured (the templates check both)
        "enabled_social": [p for p in ("google", "github", "facebook") if config.social_enabled(p)],
        # an admin should know when sign-ups are not email-verified because this install cannot send email
        "require_email_confirmation": integrations.require_email_confirmation(),
        **staff_flags(config),
    }
