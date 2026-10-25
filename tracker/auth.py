"""django-allauth adapters: sign-up follows the admin switch; Google and GitHub sign-in need a verified email, Facebook's is confirmed by link."""
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.account.utils import has_verified_email
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect

from .models import SiteConfig, UserProfile
from .services import integrations


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return SiteConfig.load().signup_open

    def get_from_email(self):
        return integrations.from_email()

    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit)
        if commit:
            UserProfile.objects.update_or_create(user=user, defaults={"self_registered": True})
        return user

    def _home(self, request):
        """A person who has not yet seen the welcome questions starts there; everyone else goes to the app."""
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            profile = UserProfile.objects.filter(user=user).first()
            if profile is not None and not profile.onboarding_done:
                return "/app/welcome"
        return None

    def get_login_redirect_url(self, request):
        return self._home(request) or super().get_login_redirect_url(request)

    def get_signup_redirect_url(self, request):
        """Straight in after sign-up (no email step): a person who has not answered the welcome questions starts there."""
        return self._home(request) or super().get_signup_redirect_url(request)

    def pre_login(self, request, user, **kwargs):
        """People who registered themselves must confirm their email before they get in.

        Accounts made in the admin or with createsuperuser are not self-registered and are never blocked."""
        blocked = super().pre_login(request, user, **kwargs)
        if blocked:
            return blocked
        profile = UserProfile.objects.filter(user=user).first()
        if (integrations.require_email_confirmation() and profile and profile.self_registered
                and not has_verified_email(user, kwargs.get("email"))):
            address = EmailAddress.objects.filter(user=user, verified=False).order_by("-primary", "-pk").first()
            if address:  # we stop the login here, so allauth's own "send at login" stage never runs
                address.send_confirmation(request, signup=bool(kwargs.get("signup")))
            return self.respond_email_verification_sent(request, user)
        return None


# Facebook does not vouch for an address the way Google and GitHub do, so a new Facebook person is let in on the usual email
# confirmation instead (AccountAdapter.pre_login), and the address is never used to attach to an existing account.
UNVERIFIED_OK = {"facebook"}


def _verified_emails(sociallogin) -> list[str]:
    return [a.email for a in sociallogin.email_addresses if a.verified and a.email]


def _may_register(config: SiteConfig, sociallogin) -> bool:
    """Open sign-up admits anyone with a usable email; closed sign-up needs the allowlist."""
    emails = _verified_emails(sociallogin)
    if not emails and sociallogin.account.provider in UNVERIFIED_OK:
        emails = [a.email for a in sociallogin.email_addresses if a.email]
    if not emails:
        return False
    return config.signup_open or any(config.google_email_allowed(e) for e in emails)


class SocialAdapter(DefaultSocialAccountAdapter):
    def list_apps(self, request, provider=None, client_id=None):
        """Apps from the environment or from the admin's Site configuration first; apps added the old way (Social applications) still work."""
        from allauth.socialaccount.models import SocialApp

        apps = []
        for pid in integrations.PROVIDERS:
            if provider and provider != pid:
                continue
            credentials = integrations.social_credentials(pid)
            if credentials and (not client_id or client_id == credentials[0]):
                apps.append(SocialApp(provider=pid, name=pid.title(), client_id=credentials[0], secret=credentials[1]))
        seen = {a.provider for a in apps}
        apps.extend(a for a in super().list_apps(request, provider=provider, client_id=client_id) if a.provider not in seen)
        return apps

    def pre_social_login(self, request, sociallogin):
        config = SiteConfig.load()
        provider = sociallogin.account.provider
        if not config.social_enabled(provider):
            messages.error(request, f"{provider.title()} sign-in is turned off.")
            raise ImmediateHttpResponse(redirect("account_login"))
        if sociallogin.is_existing:
            return
        if not _may_register(config, sociallogin):
            messages.error(request, "Registration is closed, or that account has no usable email address.")
            raise ImmediateHttpResponse(redirect("account_login"))

    def is_open_for_signup(self, request, sociallogin):
        config = SiteConfig.load()
        return config.social_enabled(sociallogin.account.provider) and _may_register(config, sociallogin)

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        user.is_staff = False  # social users get the dashboard, never the admin
        user.is_superuser = False
        return user

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        if not _verified_emails(sociallogin):  # no address the provider vouched for: make them confirm it like anyone who signs up
            UserProfile.objects.update_or_create(user=user, defaults={"self_registered": True})
        return user
