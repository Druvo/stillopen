from django.conf import settings

from .models import SiteConfig


def site_config(request):
    config = SiteConfig.load()
    return {
        "site_config": config, "google_login_on": config.google_login_enabled,
        # an admin should know when sign-ups are not email-verified because this install cannot send email
        "require_email_confirmation": settings.STILLOPEN_REQUIRE_EMAIL_CONFIRMATION,
        "email_unverified_signups": config.signup_open and not settings.STILLOPEN_REQUIRE_EMAIL_CONFIRMATION,
    }
