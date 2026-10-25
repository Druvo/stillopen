"""The repo stays open-source ready: licence and community files exist, docs point at real files, nothing personal ships."""
import re
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase
from django.urls import reverse

ROOT = Path(settings.BASE_DIR)


class RepoFiles(TestCase):
    def test_licence_and_community_files_exist(self):
        for name in ("LICENSE", "NOTICE", "README.md", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md",
                     "CHANGELOG.md", "docs/SELF-HOSTING.md", "docs/HOSTING.md", "docker-compose.selfhost.yml"):
            self.assertTrue((ROOT / name).is_file(), name)

    def test_licence_is_apache_2(self):
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Apache License", text)
        self.assertIn("Version 2.0, January 2004", text)

    def test_markdown_links_to_local_files_resolve(self):
        link = re.compile(r"\]\((?!https?:|mailto:|#)([^)#\s]+)")
        for name in ("README.md", "CONTRIBUTING.md", "SECURITY.md", "docs/SELF-HOSTING.md"):
            path = ROOT / name
            for target in link.findall(path.read_text(encoding="utf-8")):
                self.assertTrue((path.parent / target).exists(), f"{name} links to missing {target}")

    def test_env_example_has_no_personal_path_or_secret(self):
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"[A-Za-z]:\\")
        for line in text.splitlines():
            key, _, value = line.partition("=")
            if key.strip().endswith(("TOKEN", "PASSWORD", "SECRET_KEY", "CLIENT_SECRET")) and not line.startswith("#"):
                self.assertEqual(value.strip(), "", f"{key} must be empty in the example")

    def test_dockerfile_does_not_run_as_root(self):
        self.assertRegex((ROOT / "Dockerfile").read_text(encoding="utf-8"), r"(?m)^USER\s+\S+")

    def test_secrets_and_data_are_never_tracked_by_ignore_rules(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for pattern in (".env", ".secret_key", "db.sqlite3"):
            self.assertIn(pattern, ignore)


class LandingAngle(TestCase):
    def test_landing_links_to_source_and_self_hosting_guide(self):
        page = self.client.get(reverse("landing")).content.decode()
        self.assertIn('id="open-source"', page)
        self.assertIn("SELF-HOSTING.md", page)
        self.assertIn("Apache-2.0", page)


class PostgresSupport(TestCase):
    def test_compose_override_and_ci_job_exist(self):
        self.assertIn("DATABASE_URL", (ROOT / "docker-compose.postgres.yml").read_text(encoding="utf-8"))
        self.assertIn("test-postgres", (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8"))

    def test_copy_command_refuses_to_run_on_sqlite(self):
        if connection.vendor == "postgresql":
            self.skipTest("this run is on PostgreSQL")
        with self.assertRaisesMessage(CommandError, "must point at PostgreSQL"):
            call_command("copy_to_postgres", "--from", "anything.sqlite3")


class TwoStepSignIn(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user("mfauser", email="mfa@example.com", password="x" * 20)

    def test_the_app_links_to_two_step_setup_and_the_page_loads(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/api/v1/profile").json()["account"]["classic"]["two_step"], reverse("mfa_index"))
        page = self.client.get(reverse("mfa_index"))
        self.assertEqual(page.status_code, 200)

    def test_authenticator_app_setup_page_shows_a_qr_code_without_third_parties(self):
        from tracker.tests_selfhost import EXTERNAL_ASSET

        self.client.post(reverse("account_login"), {"login": "mfauser", "password": "x" * 20})
        asked = self.client.get(reverse("mfa_activate_totp"))  # allauth first asks for the password again
        self.assertEqual(asked.status_code, 302)
        self.client.post(reverse("account_reauthenticate"), {"password": "x" * 20})
        page = self.client.get(reverse("mfa_activate_totp"))
        self.assertEqual(page.status_code, 200, page.get("Location"))
        self.assertContains(page, "<svg")
        self.assertIsNone(EXTERNAL_ASSET.search(page.content.decode()))

    def test_a_person_with_an_authenticator_must_give_a_code_to_sign_in(self):
        from allauth.mfa.models import Authenticator
        from allauth.mfa.totp.internal import auth as totp

        secret = totp.generate_totp_secret()
        Authenticator.objects.create(user=self.user, type=Authenticator.Type.TOTP, data={"secret": secret})
        r = self.client.post(reverse("account_login"), {"login": "mfauser", "password": "x" * 20})
        self.assertRedirects(r, reverse("mfa_authenticate"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)  # signed in only after the second step
        import time

        code = totp.format_hotp_value(totp.hotp_value(secret, int(time.time() // 30)))
        self.client.post(reverse("mfa_authenticate"), {"code": code})
        self.assertIn("_auth_user_id", self.client.session)


class HealthCheckHost(TestCase):
    def test_local_health_check_address_is_always_allowed(self):
        self.assertIn("127.0.0.1", settings.ALLOWED_HOSTS)
