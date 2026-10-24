"""Email sending and social sign-in set up from the admin: used at once, secrets encrypted and never shown, the environment wins."""
from unittest import mock

from allauth.socialaccount.models import SocialApp
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from tracker import crypto
from tracker.admin import SiteConfigForm
from tracker.models import SiteConfig
from tracker.services import integrations

User = get_user_model()


class EmailFromAdmin(TestCase):
    def setUp(self):
        self.config = SiteConfig.load()

    def fill(self, **extra):
        self.config.email_host = "smtp-relay.brevo.com"
        self.config.email_username = "login@example.com"
        self.config.set_email_password("smtp-key-123")
        self.config.email_from = "StillOpen <jobs@example.com>"
        for key, value in extra.items():
            setattr(self.config, key, value)
        self.config.save()

    def test_nothing_set_up_means_console_and_no_confirmation_rule(self):
        self.assertIsNone(integrations.email_settings())
        self.assertFalse(integrations.email_configured())

    def test_admin_settings_are_used_at_once_and_the_password_is_encrypted(self):
        self.fill()
        cfg = integrations.email_settings()
        self.assertEqual((cfg.host, cfg.port, cfg.username, cfg.password, cfg.source), ("smtp-relay.brevo.com", 587, "login@example.com", "smtp-key-123", "admin"))
        self.assertNotIn("smtp-key-123", SiteConfig.objects.get().email_password_encrypted)
        self.assertEqual(crypto.decrypt(SiteConfig.objects.get().email_password_encrypted), "smtp-key-123")
        self.assertEqual(integrations.from_email(), "StillOpen <jobs@example.com>")

    @override_settings(EMAIL_CONFIGURED=True, EMAIL_HOST="env.example.com", EMAIL_PORT=2525, EMAIL_HOST_USER="env", EMAIL_HOST_PASSWORD="envpw", EMAIL_USE_TLS=False)
    def test_the_environment_wins_over_the_admin(self):
        self.fill()
        cfg = integrations.email_settings()
        self.assertEqual((cfg.host, cfg.source), ("env.example.com", "environment"))

    def test_the_backend_sends_through_the_admin_settings(self):
        self.fill()
        from tracker.email_backend import ConfiguredBackend

        with mock.patch("tracker.email_backend.SmtpBackend") as smtp:
            smtp.return_value.send_messages.return_value = 1
            sent = ConfiguredBackend().send_messages([mail.EmailMessage("s", "b", "a@example.com", ["b@example.com"])])
        self.assertEqual(sent, 1)
        kwargs = smtp.call_args.kwargs
        self.assertEqual((kwargs["host"], kwargs["port"], kwargs["username"], kwargs["password"], kwargs["use_tls"]),
                         ("smtp-relay.brevo.com", 587, "login@example.com", "smtp-key-123", True))

    def test_the_confirmation_rule_follows_whether_email_works(self):
        with override_settings(STILLOPEN_REQUIRE_EMAIL_CONFIRMATION=None):
            self.assertFalse(integrations.require_email_confirmation())
            self.fill()
            self.assertTrue(integrations.require_email_confirmation())
        with override_settings(STILLOPEN_REQUIRE_EMAIL_CONFIRMATION=False):
            self.assertFalse(integrations.require_email_confirmation())  # an explicit setting always wins

    def test_check_email_reads_the_same_settings(self):
        from io import StringIO

        from django.core.management import call_command

        self.fill()
        out = StringIO()
        call_command("check_email", "--no-send", stdout=out)
        self.assertIn("smtp-relay.brevo.com", out.getvalue())
        self.assertNotIn("smtp-key-123", out.getvalue())


class EmailTestPage(TestCase):
    def test_only_staff_can_open_it_and_a_test_goes_to_their_own_address(self):
        user = User.objects.create_user("plain", email="p@example.com", password="x" * 20)
        boss = User.objects.create_user("boss", email="boss@example.com", password="x" * 20, is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("email_test")).status_code, 302)
        self.client.force_login(boss)
        self.assertContains(self.client.get(reverse("email_test")), "not set up")
        config = SiteConfig.load()
        config.email_host = "smtp.example.com"
        config.save()
        with mock.patch("django.core.mail.send_mail", return_value=1) as send:
            r = self.client.post(reverse("email_test"))
        self.assertContains(r, "Sent to boss@example.com")
        self.assertEqual(send.call_args.args[3], ["boss@example.com"])


class AdminForm(TestCase):
    def data(self, **extra):
        form = SiteConfigForm(instance=SiteConfig.load())
        data = {name: ("" if value is None else value) for name, value in form.initial.items()}
        data = {k: v for k, v in data.items() if v not in (False,)}
        data.update(extra)
        return data

    def test_secrets_are_saved_encrypted_and_blank_keeps_them(self):
        form = SiteConfigForm(self.data(email_host="smtp.example.com", email_password="pw-1", github_client_id="gh-id", github_secret="gh-secret",
                                        github_login_enabled="on"), instance=SiteConfig.load())
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        saved = SiteConfig.objects.get()
        self.assertEqual((saved.email_password, saved.social_secret("github"), saved.github_client_id), ("pw-1", "gh-secret", "gh-id"))
        self.assertTrue(saved.github_login_enabled)
        again = SiteConfigForm(self.data(email_host="smtp.example.com", github_login_enabled="on"), instance=saved)
        self.assertTrue(again.is_valid(), again.errors)
        again.save()
        kept = SiteConfig.objects.get()
        self.assertEqual((kept.email_password, kept.social_secret("github")), ("pw-1", "gh-secret"))

    def test_the_admin_page_renders_without_secrets(self):
        boss = User.objects.create_superuser("root", "root@example.com", "x" * 20)
        config = SiteConfig.load()
        config.set_email_password("never-shown-pw")
        config.set_social_secret("google", "never-shown-secret")
        config.save()
        self.client.force_login(boss)
        page = self.client.get(reverse("admin:tracker_siteconfig_change", args=[config.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Email sending")
        self.assertContains(page, "Sign-in with Google, GitHub or Facebook")
        self.assertNotContains(page, "never-shown")


class SocialFromAdmin(TestCase):
    def setUp(self):
        self.config = SiteConfig.load()

    def test_a_provider_configured_in_the_admin_gets_its_button_only_when_switched_on(self):
        self.config.github_client_id = "gh-id"
        self.config.set_social_secret("github", "gh-secret")
        self.config.save()
        self.assertNotContains(self.client.get(reverse("account_login")), "Continue with GitHub")  # keys alone are not enough
        self.config.github_login_enabled = True
        self.config.save()
        self.assertContains(self.client.get(reverse("account_login")), "Continue with GitHub")

    def test_switched_on_without_keys_shows_no_button(self):
        self.config.facebook_login_enabled = True
        self.config.save()
        self.assertNotContains(self.client.get(reverse("account_login")), "Continue with Facebook")

    def test_the_old_social_applications_way_still_works(self):
        from django.contrib.sites.models import Site

        SocialApp.objects.create(provider="google", name="Google", client_id="old", secret="old").sites.add(Site.objects.get_current())
        self.config.google_login_enabled = True
        self.config.save()
        self.assertContains(self.client.get(reverse("account_login")), "Continue with Google")

    @override_settings()
    def test_the_environment_wins_over_the_admin(self):
        import os

        self.config.google_client_id = "admin-id"
        self.config.set_social_secret("google", "admin-secret")
        self.config.save()
        with mock.patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "env-id", "GOOGLE_CLIENT_SECRET": "env-secret"}):
            self.assertEqual(integrations.social_credentials("google"), ("env-id", "env-secret"))
        self.assertEqual(integrations.social_credentials("google"), ("admin-id", "admin-secret"))


class AiSettingsPage(TestCase):
    def test_the_first_screen_asks_only_for_a_provider_and_a_key(self):
        user = User.objects.create_user("ai", email="ai@example.com", password="x" * 20)
        self.client.force_login(user)
        page = self.client.get(reverse("profile_ai")).content.decode()
        self.assertIn("1. Choose your AI provider", page)
        self.assertIn("2. Paste your API key", page)
        before_advanced = page.split("Advanced options")[0]
        for technical in ("id_ai_base_url", "id_ai_model", "id_ai_custom_headers", "id_rag_top_k", "id_ai_timeout"):
            self.assertNotIn(technical, before_advanced)
            self.assertIn(technical, page)
