"""scripts/release_notes.py: a version's section of CHANGELOG.md, or a clear error."""
import importlib.util
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("release_notes", ROOT / "scripts" / "release_notes.py")
release_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_notes)

SAMPLE = """# Changelog

## [Unreleased]

- Not out yet.

## 1.2.0 - 2026-11-01

- Added a thing.
- Fixed another.

## [1.1.0] - 2026-10-01

- Older.

## 1.0.0 - unreleased draft

- Draft.

## 0.9.0 - 2026-09-01
"""


class Extract(SimpleTestCase):
    def test_returns_only_that_section(self):
        self.assertEqual(release_notes.extract(SAMPLE, "v1.2.0"), "- Added a thing.\n- Fixed another.\n")

    def test_accepts_a_bare_version_and_bracketed_headings(self):
        self.assertEqual(release_notes.extract(SAMPLE, "1.1.0"), "- Older.\n")

    def test_missing_version_says_what_to_add(self):
        with self.assertRaisesRegex(release_notes.ReleaseNotesError, "no section headed"):
            release_notes.extract(SAMPLE, "v3.0.0")

    def test_a_draft_heading_is_refused(self):
        with self.assertRaisesRegex(release_notes.ReleaseNotesError, "unreleased draft"):
            release_notes.extract(SAMPLE, "v1.0.0")

    def test_an_empty_section_is_refused(self):
        with self.assertRaisesRegex(release_notes.ReleaseNotesError, "empty"):
            release_notes.extract(SAMPLE, "v0.9.0")

    def test_not_a_version_is_refused(self):
        for bad in ("latest", "v1.2", "", "Unreleased"):
            with self.assertRaises(release_notes.ReleaseNotesError, msg=bad):
                release_notes.extract(SAMPLE, bad)


class RealChangelog(SimpleTestCase):
    def test_the_first_release_is_drafted_and_not_yet_publishable(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## 0.1.0 - unreleased draft", text)
        self.assertLess(text.index("## [Unreleased]"), text.index("## 0.1.0"))
        with self.assertRaisesRegex(release_notes.ReleaseNotesError, "unreleased draft"):
            release_notes.extract(text, "v0.1.0")

    def test_command_line_exits_1_with_the_error_on_stderr(self):
        script = str(ROOT / "scripts" / "release_notes.py")
        done = subprocess.run([sys.executable, "-I", script, "v0.1.0"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 1)
        self.assertIn("unreleased draft", done.stderr)
        self.assertEqual(done.stdout, "")
        usage = subprocess.run([sys.executable, "-I", script], capture_output=True, text=True)
        self.assertEqual(usage.returncode, 2)
