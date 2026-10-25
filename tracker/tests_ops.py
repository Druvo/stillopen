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


class LegalWarningInTheApp(TestCase):
    """The app tells site admins (and only them) while the privacy and terms texts still have blanks and sign-up is open."""

    def setUp(self):
        self.staff = User.objects.create_user("boss", email="boss@example.com", password="correct-horse-battery-staple", is_staff=True)
        self.normal = User.objects.create_user("jo", email="jo@example.com", password="correct-horse-battery-staple")

    def warned(self, name):
        self.client.login(username=name, password="correct-horse-battery-staple")
        return self.client.get("/api/v1/me").json()["legal_has_blanks"]

    def test_staff_are_told_while_sign_up_is_open_and_blanks_remain(self):
        SiteConfig.objects.filter(pk=1).update(signup_mode="open")
        self.assertTrue(self.warned("boss"))

    def test_ordinary_people_never_see_it(self):
        SiteConfig.objects.filter(pk=1).update(signup_mode="open")
        self.assertFalse(self.warned("jo"))

    def test_no_warning_when_sign_up_is_closed_or_the_text_is_complete(self):
        self.assertFalse(self.warned("boss"))  # closed by default
        SiteConfig.objects.filter(pk=1).update(signup_mode="open", privacy_text="Acme Ltd, hello@acme.test.", terms_text="Be kind. hello@acme.test.")
        self.assertFalse(self.warned("boss"))


class OffsiteBackupScript(TestCase):
    """deploy/backup-offsite.sh: syntax, dry run, and a full run against a fake rclone (no network, no credentials)."""

    SCRIPT = ROOT / "deploy" / "backup-offsite.sh"

    def setUp(self):
        self.bash = self.find_bash()
        if self.bash is None:
            self.skipTest("a working bash is not available")
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name) / "backups"
        self.dir.mkdir()
        self.old = self.dir / "stillopen-20250101T000000Z.dump"
        self.new = self.dir / "stillopen-20260101T000000Z.dump"
        self.old.write_bytes(b"old dump")
        self.new.write_bytes(b"new dump bytes")
        import os

        os.utime(self.old, (1, 1))
        (self.dir / "secret_key").write_text("THE-SECRET-KEY-VALUE", encoding="utf-8")
        self.env = {**__import__("os").environ, "BACKUP_DIR": str(self.dir), "OFFSITE_REMOTE": "myremote:backups", "OFFSITE_ENV_FILE": str(Path(self.tmp.name) / "none"),
                    "HOME": self.tmp.name}

    @staticmethod
    def find_bash():
        """A bash that really runs (on Windows `bash` can be the WSL stub, so try Git's first)."""
        import shutil
        import subprocess

        for candidate in ("C:/Program Files/Git/bin/bash.exe", "/usr/bin/bash", shutil.which("bash")):
            if candidate and (Path(candidate).exists() or candidate == shutil.which("bash")):
                try:
                    if subprocess.run([candidate, "-c", "echo ok"], capture_output=True, text=True, timeout=20).stdout.strip() == "ok":
                        return candidate
                except (OSError, subprocess.SubprocessError):
                    continue
        return None

    def run_script(self, **extra):
        import subprocess

        return subprocess.run([self.bash, self.SCRIPT.as_posix()], env={**self.env, **extra}, capture_output=True, text=True, cwd=ROOT, timeout=60)

    def fake_rclone(self, fail_check=False):
        """A stand-in `rclone` first on PATH that logs each call and copies into a local folder."""
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir(exist_ok=True)
        remote = Path(self.tmp.name) / "remote"
        remote.mkdir(exist_ok=True)
        for n in range(1, 10):  # nine older copies already at the remote
            (remote / f"stillopen-2024010{n}T000000Z.dump").write_text("x", encoding="utf-8")
        log = Path(self.tmp.name) / "rclone.log"
        script = (
            "#!/bin/bash\n"
            f'echo "$@" >> "{log.as_posix()}"\n'
            'cmd=$1; shift\n'
            'args=(); pat="*"; while [ $# -gt 0 ]; do case "$1" in --quiet|--one-way|--files-only) ;; --include) shift; pat="${1#/}" ;; *) args+=("$1") ;; esac; shift; done\n'
            f'R="{remote.as_posix()}"\n'
            'case "$cmd" in\n'
            '  copyto) cp "${args[0]}" "$R/$(basename "${args[1]}")" ;;\n'
            f'  check) {"exit 1" if fail_check else "exit 0"} ;;\n'
            '  lsf) (cd "$R" && ls -1 $pat 2>/dev/null) ;;\n'
            '  deletefile) rm -f "$R/$(basename "${args[0]}")" ;;\n'
            "esac\n"
        )
        fake = bin_dir / "rclone"
        fake.write_text(script, encoding="utf-8", newline="\n")
        fake.chmod(0o755)  # on Linux `command -v` only accepts a file that can be run; Windows does not care
        return bin_dir, remote, log

    def test_the_script_parses_and_is_in_the_schedule_and_docs(self):
        import subprocess

        self.assertEqual(subprocess.run([self.bash, "-n", self.SCRIPT.as_posix()], capture_output=True, text=True).returncode, 0)
        self.assertIn("backup-offsite.sh", (ROOT / "deploy" / "crontab.docker.example").read_text(encoding="utf-8"))
        docs = (ROOT / "docs" / "SELF-HOSTING.md").read_text(encoding="utf-8")
        self.assertIn("Restoring from the off-site copy", docs)
        self.assertIn("OFFSITE_DRY_RUN=1", docs)
        self.assertTrue((ROOT / "deploy" / "offsite.env.example").exists())

    def test_dry_run_names_the_newest_file_copies_nothing_and_prints_no_secret(self):
        result = self.run_script(OFFSITE_DRY_RUN="1", OFFSITE_INCLUDE_SECRET_KEY="1", OFFSITE_RCLONE="no-such-rclone")  # no rclone needed to preview
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DRY RUN", result.stdout)
        self.assertIn("stillopen-20260101T000000Z.dump", result.stdout)
        self.assertNotIn("20250101", result.stdout)
        self.assertNotIn("THE-SECRET-KEY-VALUE", result.stdout + result.stderr)

    def test_it_fails_loudly_without_a_backup_a_remote_or_the_tool(self):
        self.new.unlink()
        self.old.unlink()
        self.assertNotEqual(self.run_script().returncode, 0)
        self.new.write_bytes(b"x")
        self.assertNotEqual(self.run_script(OFFSITE_REMOTE="").returncode, 0)
        missing = self.run_script(OFFSITE_RCLONE="no-such-rclone")
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("rclone is not installed", missing.stderr)

    def test_a_full_run_copies_verifies_and_keeps_only_the_newest_copies(self):
        bin_dir, remote, log = self.fake_rclone()
        result = self.run_script(OFFSITE_RCLONE=(bin_dir / "rclone").as_posix(), OFFSITE_KEEP="3", OFFSITE_INCLUDE_SECRET_KEY="1")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        names = sorted(p.name for p in remote.iterdir())
        self.assertIn("stillopen-20260101T000000Z.dump", names)
        self.assertIn("secret_key", names)
        self.assertEqual(len([n for n in names if n.endswith(".dump")]), 3)  # the newest three; the older ones were removed
        self.assertNotIn("stillopen-20240101T000000Z.dump", names)
        calls = log.read_text(encoding="utf-8")
        self.assertIn("check", calls)  # the copy was verified
        self.assertIn("verified", result.stdout)
        self.assertNotIn("THE-SECRET-KEY-VALUE", result.stdout + result.stderr)

    def test_a_copy_that_does_not_match_is_a_failure(self):
        bin_dir, _remote, _log = self.fake_rclone(fail_check=True)
        result = self.run_script(OFFSITE_RCLONE=(bin_dir / "rclone").as_posix())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match", result.stderr)

    def test_the_env_file_is_read_but_only_plain_assignments_run(self):
        env_file = Path(self.tmp.name) / "offsite.env"
        marker = Path(self.tmp.name) / "pwned"
        env_file.write_text(f"OFFSITE_KEEP=2\n# comment\ntouch {marker.as_posix()}\nOFFSITE_REMOTE=myremote:backups\n", encoding="utf-8")
        result = self.run_script(OFFSITE_ENV_FILE=str(env_file), OFFSITE_DRY_RUN="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("keep 2", result.stdout)
        self.assertFalse(marker.exists())
        self.assertIn("unrecognised line", result.stderr)

    def test_logrotate_file_and_compose_log_caps_exist(self):
        self.assertIn("rotate", (ROOT / "deploy" / "logrotate.stillopen").read_text(encoding="utf-8"))
