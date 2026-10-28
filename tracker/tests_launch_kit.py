"""The launch kit: README links and pictures, repo files, workflows, update scripts, the project site and the demo seed."""
import importlib.util
import os
import re
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from tracker.models import Application, CVVersion, UserProfile

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("check_links", ROOT / "scripts" / "check_links.py")
check_links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_links)


class Links(SimpleTestCase):
    def test_every_relative_link_and_image_in_the_markdown_files_resolves(self):
        self.assertEqual(check_links.check(), [])

    def test_the_checker_catches_a_missing_file_and_a_missing_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.md").write_text("# Title\n\n[ok](b.md#hello) [gone](nope.md) [bad](b.md#nothing) `[code](ignored.md)` [web](https://x.example/y)\n", encoding="utf-8")
            (root / "b.md").write_text("## Hello\n", encoding="utf-8")
            with mock.patch.object(check_links, "ROOT", root):
                problems = check_links.check([root / "a.md"])
        self.assertEqual(len(problems), 2)
        self.assertTrue(any("nope.md" in p for p in problems))
        self.assertTrue(any("#nothing" in p for p in problems))


class Readme(SimpleTestCase):
    def test_pictures_exist_and_are_small(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        images = set(re.findall(r"\(docs/images/([\w.-]+\.(?:png|gif|jpg))\)", text))
        self.assertTrue({"dashboard.png", "board.png", "cv-fact-check.png", "insights.png", "openings.png", "mobile.png", "demo.gif"} <= images)
        for name in images:
            size = (ROOT / "docs" / "images" / name).stat().st_size
            self.assertLess(size, 5_000_000 if name.endswith(".gif") else 400_000, name)

    def test_the_published_image_line_is_only_there_with_a_workflow_that_builds_it(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        if "ghcr.io/druvo/stillopen" in text:
            self.assertTrue((ROOT / ".github" / "workflows" / "image.yml").exists())
            self.assertIn("after the first tagged release", text)

    def test_has_the_honest_sections(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        for heading in ("## Known limitations", "## Performance and sizing", "## Support the project", "## Quick start"):
            self.assertIn(heading, text)
        for phrase in ("LinkedIn, Indeed and Glassdoor are never scraped", "no mobile app", "English only"):
            self.assertIn(phrase, text)


class RepoFiles(SimpleTestCase):
    def test_funding_placeholder_is_commented_out(self):
        lines = (ROOT / ".github" / "FUNDING.yml").read_text(encoding="utf-8").splitlines()
        active = [line for line in lines if line.strip() and not line.lstrip().startswith("#")]
        self.assertEqual(active, [])
        self.assertIn("# github: [your-username]", lines)

    def test_blank_issues_are_off_and_help_is_linked(self):
        text = (ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml").read_text(encoding="utf-8")
        self.assertIn("blank_issues_enabled: false", text)
        for needle in ("docs/SELF-HOSTING.md", "/discussions", "/security/advisories/new"):
            self.assertIn(needle, text)
        for form in ("bug_report.yml", "feature_request.yml", "new_job_source.yml"):
            self.assertTrue((ROOT / ".github" / "ISSUE_TEMPLATE" / form).exists())

    def test_version_file_is_semver_and_matches_the_draft_heading(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        self.assertIn(f"## {version} - ", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))


class Workflows(SimpleTestCase):
    def read(self, name):
        return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")

    def test_every_action_is_pinned_to_a_version(self):
        for name in ("release.yml", "pages.yml"):
            for line in self.read(name).splitlines():
                if re.match(r"\s*-?\s*uses:", line):
                    self.assertRegex(line, r"uses:\s*[\w./-]+@v\d+(\.\d+){0,2}\s*$", line)

    def test_release_runs_on_version_tags_with_least_privilege_and_the_notes_script(self):
        text = self.read("release.yml")
        self.assertIn('- "v*"', text)
        self.assertRegex(text, r"permissions:\s*\n\s*contents: write")
        self.assertEqual(len(re.findall(r"^\s+(?:id-token|pages|packages|actions|issues): ", text, re.M)), 0)
        self.assertIn("scripts/release_notes.py", text)
        self.assertIn("gh release create", text)
        self.assertTrue((ROOT / "scripts" / "release_notes.py").exists())
        self.assertTrue((ROOT / ".github" / "workflows" / "image.yml").exists())
        self.assertTrue((ROOT / "docs" / "RELEASING.md").exists())

    def test_pages_publishes_the_site_folder_only(self):
        text = self.read("pages.yml")
        self.assertIn("path: site", text)
        self.assertIn("pages: write", text)
        self.assertIn("contents: read", text)


class UpdateScripts(SimpleTestCase):
    def test_both_scripts_refuse_a_dirty_tree_and_name_a_real_compose_file(self):
        sh = (ROOT / "deploy" / "update.sh").read_text(encoding="utf-8")
        ps = (ROOT / "deploy" / "update.ps1").read_text(encoding="utf-8")
        self.assertTrue(sh.startswith("#!/usr/bin/env bash"))
        self.assertIn("set -euo pipefail", sh)
        for text in (sh, ps):
            self.assertIn("git status --porcelain", text)
            compose = re.search(r"docker-compose[\w.-]*\.yml", text).group(0)
            self.assertTrue((ROOT / compose).exists(), compose)
            self.assertIn("--ff-only", text)
            self.assertRegex(text, r"(?i)dry.?run")
            self.assertIn("manage.py migrate", text)

    def test_they_are_documented_where_updating_is_explained(self):
        text = (ROOT / "docs" / "SELF-HOSTING.md").read_text(encoding="utf-8")
        self.assertIn("deploy/update.sh", text)
        self.assertIn("update.ps1", text)


class Site(SimpleTestCase):
    def test_the_site_loads_nothing_from_another_host(self):
        html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        for pattern in (
            r"<script[^>]+src=[\"'](?:https?:)?//", r"<link[^>]+href=[\"'](?:https?:)?//", r"<img[^>]+src=[\"'](?:https?:)?//",
            r"<iframe[^>]+src=", r"<source[^>]+src=[\"'](?:https?:)?//", r"@import", r"url\([\"']?(?:https?:)?//",
        ):
            self.assertIsNone(re.search(pattern, html, re.I), pattern)
        css = (ROOT / "site" / "style.css").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"@import|url\([\"']?(?:https?:)?//|@font-face", css, re.I))
        js = (ROOT / "site" / "main.js").read_text(encoding="utf-8")
        for call in ("fetch(", "XMLHttpRequest", "sendBeacon", "document.cookie", "http://", "https://"):
            self.assertNotIn(call, js)

    def test_local_references_exist_and_theme_is_set_before_first_paint(self):
        html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        for ref in re.findall(r"(?:src|href)=\"([^\"#:]+)\"", html):
            self.assertTrue((ROOT / "site" / ref).exists(), ref)
        self.assertLess(html.index("data-theme"), html.index('rel="stylesheet"'))
        for section in ("how", "honest", "features", "privacy", "install", "limits", "cta"):
            self.assertIn(f'id="{section}"', html)
        self.assertEqual(html.count('role="tab"'), 2)


class DemoSeed(TestCase):
    def seed(self, *args):
        with mock.patch.dict(os.environ, {"STILLOPEN_E2E": "1"}):
            call_command("e2e_seed", *args, stdout=StringIO())

    def test_without_the_flag_there_is_no_jane(self):
        self.seed()
        self.assertFalse(get_user_model().objects.filter(username="jane").exists())

    def test_with_the_flag_jane_has_nine_jobs_across_stages_and_a_flagged_cv(self):
        self.seed("--demo")
        jane = get_user_model().objects.get(username="jane")
        jobs = Application.objects.filter(owner=jane)
        self.assertEqual(jobs.count(), 9)
        self.assertGreaterEqual(len({j.status.name for j in jobs}), 5)
        self.assertTrue(CVVersion.objects.filter(owner=jane, kind="tailored").exclude(check_report=[]).exists())
        self.assertTrue(UserProfile.objects.get(user=jane).onboarding_done)
        self.assertEqual(Application.objects.filter(owner__username="alice").count(), 3)
        self.seed("--demo")
        self.assertEqual(Application.objects.filter(owner=jane).count(), 9)
