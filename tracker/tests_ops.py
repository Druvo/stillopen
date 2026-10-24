"""Things an operator runs: the email check, the Jooble check, the scheduling files and the CI workflow."""
import re
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from tracker.models import SiteConfig
from tracker.services.netguard import FetchError

User = get_user_model()
ROOT = Path(__file__).resolve().parent.parent


def run(name, *args, **kw):
    out = StringIO()
    call_command(name, *args, stdout=out, **kw)
    return out.getvalue()


class CheckEmail(TestCase):
    @override_settings(EMAIL_CONFIGURED=False)
    def test_without_smtp_it_says_so_plainly_and_sends_nothing(self):
        text = run("check_email")
        self.assertIn("NOT set up", text)
        self.assertEqual(mail.outbox, [])

    @override_settings(EMAIL_CONFIGURED=True, EMAIL_HOST="smtp.example.com", EMAIL_PORT=587, EMAIL_HOST_USER="mailer", EMAIL_HOST_PASSWORD="hunter2-secret", EMAIL_USE_TLS=True)
    def test_with_smtp_it_shows_settings_never_the_password_and_sends_a_test(self):
        User.objects.create_superuser("boss", "boss@example.com", "x" * 12)
        text = run("check_email")
        self.assertIn("smtp.example.com:587", text)
        self.assertIn("mailer", text)
        self.assertNotIn("hunter2-secret", text)
        self.assertEqual([m.to for m in mail.outbox], [["boss@example.com"]])

    @override_settings(EMAIL_CONFIGURED=True, EMAIL_HOST="smtp.example.com")
    def test_to_and_no_send(self):
        run("check_email", "--to", "me@example.com")
        self.assertEqual(mail.outbox[0].to, ["me@example.com"])
        mail.outbox.clear()
        run("check_email", "--no-send")
        self.assertEqual(mail.outbox, [])

    @override_settings(EMAIL_CONFIGURED=True, EMAIL_HOST="smtp.example.com")
    def test_a_failure_is_reported_with_its_reason(self):
        with mock.patch("tracker.management.commands.check_email.send_mail", side_effect=ConnectionRefusedError("refused")):
            with self.assertRaisesMessage(CommandError, "ConnectionRefusedError"):
                run("check_email", "--to", "me@example.com")

    @override_settings(EMAIL_CONFIGURED=True, EMAIL_HOST="smtp.example.com")
    def test_needs_an_address(self):
        with self.assertRaisesMessage(CommandError, "No address"):
            run("check_email")


class CheckJooble(TestCase):
    def test_no_key_explains_how_to_get_one(self):
        with self.assertRaisesMessage(CommandError, "jooble.org/api/about"):
            run("check_jooble")

    def test_works_and_never_prints_the_key(self):
        SiteConfig.objects.filter(pk=1).update(jooble_api_key="sekret-jooble-key")
        jobs = [{"title": "Backend Engineer", "company": "Grab", "location": "Kuala Lumpur, Malaysia", "url": "https://jooble.org/1", "description": ""}]
        with mock.patch("tracker.services.scan.fetch_jooble", return_value=jobs) as fetch:
            text = run("check_jooble", "--place", "bd", "--role", "backend engineer")
        fetch.assert_called_once_with("bd", ["backend engineer"], "sekret-jooble-key")
        self.assertIn("Jooble works", text)
        self.assertIn("Backend Engineer at Grab", text)
        self.assertNotIn("sekret-jooble-key", text)

    def test_a_rejected_key_is_an_error_without_the_key(self):
        SiteConfig.objects.filter(pk=1).update(jooble_api_key="sekret-jooble-key")
        with mock.patch("tracker.services.scan.fetch_jooble", side_effect=FetchError("Jooble did not accept the key. Check it in Site configuration.")):
            with self.assertRaises(CommandError) as ctx:
                run("check_jooble")
        self.assertNotIn("sekret-jooble-key", str(ctx.exception))

    def test_an_empty_answer_is_a_warning_not_a_crash(self):
        SiteConfig.objects.filter(pk=1).update(jooble_api_key="k")
        with mock.patch("tracker.services.scan.fetch_jooble", return_value=[]):
            self.assertIn("returned no", run("check_jooble"))

    def test_unknown_place_is_refused(self):
        SiteConfig.objects.filter(pk=1).update(jooble_api_key="k")
        with self.assertRaisesMessage(CommandError, "Unknown place"):
            run("check_jooble", "--place", "zz")


class DeploymentFiles(TestCase):
    def test_every_command_the_schedules_run_exists(self):
        names = set()
        cron = (ROOT / "deploy" / "crontab.example").read_text(encoding="utf-8")
        for line in cron.splitlines():
            if not line.lstrip().startswith("#"):
                names |= set(re.findall(r"manage\.py (\w+)", line))
        names |= set(re.findall(r'New-StillOpenTask "[^"]+" "(\w+)"', (ROOT / "deploy" / "windows" / "schedule-stillopen.ps1").read_text(encoding="utf-8")))
        self.assertGreaterEqual(names, {"send_interview_reminders", "send_followup_emails", "scheduled_scan", "seed_sources"})
        available = {p.stem for p in (ROOT / "tracker" / "management" / "commands").glob("*.py")}
        self.assertEqual(names - available, set())

    def test_the_ci_workflow_runs_the_suite_and_checks_migrations(self):
        text = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
        self.assertIn("manage.py test", text)
        self.assertIn("makemigrations --check", text)
        self.assertIn("pull_request", text)
        self.assertIn("requirements-mcp.txt", text)
        self.assertIn("requirements-ai.txt", text)  # the Agent SDK provider's test needs the optional package


class LegalTexts(TestCase):
    def test_the_templates_say_what_the_app_really_does(self):
        from tracker import legal
        privacy = legal.PRIVACY.lower()
        for fact in ("jooble", "cookies", "export", "delete your account", "interview reminders", "never leave this server", "third-party"):
            self.assertIn(fact, privacy)
        terms = legal.TERMS.lower()
        for fact in ("never apply for you", "not advice", "estimates"):
            self.assertIn(fact, terms)

    def test_placeholders_are_detected_until_filled_in(self):
        from tracker import legal
        self.assertTrue(legal.has_placeholders(legal.PRIVACY))
        self.assertTrue(legal.has_placeholders(legal.OLD_PRIVACY))  # the old "(Site owner: ...)" note counts
        self.assertFalse(legal.has_placeholders("Acme Ltd runs this site. Write to hello@acme.test. Backups rotate within 30 days."))
        self.assertFalse(legal.has_placeholders(""))
        self.assertFalse(legal.has_placeholders("Arrays like a[1] are fine"))  # too short to be a blank

    def test_new_installs_start_with_the_new_text(self):
        from tracker import legal
        config = SiteConfig.load()
        self.assertEqual(config.privacy_text, legal.PRIVACY)
        self.assertEqual(config.terms_text, legal.TERMS)
        page = self.client.get("/privacy/").content.decode()
        self.assertIn("Cookies", page)

    def test_update_command_replaces_only_an_unedited_old_default(self):
        from tracker import legal
        SiteConfig.objects.filter(pk=1).update(privacy_text=legal.OLD_PRIVACY, terms_text="Our own terms, written by a lawyer.")
        text = run("update_legal_text")
        config = SiteConfig.load()
        self.assertEqual(config.privacy_text, legal.PRIVACY)
        self.assertEqual(config.terms_text, "Our own terms, written by a lawyer.")
        self.assertIn("Kept terms_text", text)
        self.assertIn("Updated privacy_text", text)

    def test_update_command_force_and_nothing_to_do(self):
        from tracker import legal
        SiteConfig.objects.filter(pk=1).update(terms_text="Our own terms.")
        self.assertIn("Kept terms_text", run("update_legal_text"))
        run("update_legal_text", "--force")
        self.assertEqual(SiteConfig.load().terms_text, legal.TERMS)
        SiteConfig.objects.filter(pk=1).update(privacy_text="Mine.", terms_text="Mine too.")
        self.assertIn("Kept privacy_text", run("update_legal_text"))
        self.assertIn("Nothing to update", run("update_legal_text"))

    def test_an_empty_text_is_filled(self):
        from tracker import legal
        SiteConfig.objects.filter(pk=1).update(privacy_text="")
        run("update_legal_text")
        self.assertEqual(SiteConfig.load().privacy_text, legal.PRIVACY)


class LegalWarningOnTheDashboard(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("boss", email="boss@example.com", password="correct-horse-battery-staple", is_staff=True)
        self.normal = User.objects.create_user("jo", email="jo@example.com", password="correct-horse-battery-staple")
        from tracker.models import UserProfile
        UserProfile.objects.filter(user__in=[self.staff, self.normal]).update(onboarding_done=True, target_roles="x")

    def page(self, name):
        self.client.login(username=name, password="correct-horse-battery-staple")
        return self.client.get("/dashboard/").content.decode()

    def test_staff_are_told_while_sign_up_is_open_and_blanks_remain(self):
        SiteConfig.objects.filter(pk=1).update(signup_mode="open")
        self.assertIn("bracketed parts", self.page("boss"))

    def test_ordinary_people_never_see_it(self):
        SiteConfig.objects.filter(pk=1).update(signup_mode="open")
        self.assertNotIn("bracketed parts", self.page("jo"))

    def test_no_warning_when_sign_up_is_closed_or_the_text_is_complete(self):
        self.assertNotIn("bracketed parts", self.page("boss"))  # closed by default
        SiteConfig.objects.filter(pk=1).update(signup_mode="open", privacy_text="Acme Ltd, hello@acme.test.", terms_text="Be kind. hello@acme.test.")
        self.assertNotIn("bracketed parts", self.page("boss"))
