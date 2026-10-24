"""The repo stays open-source ready: licence and community files exist, docs point at real files, nothing personal ships."""
import re
from pathlib import Path

from django.conf import settings
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
