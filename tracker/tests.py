import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from tracker.models import Application, Bucket, Document, DocumentKind, ScoreBand, SiteConfig, Status
from tracker.services import careerops, liveness
from tracker.services.paperless import PaperlessClient, PaperlessError, push_document

TRACKER = """# Applications Tracker

| # | Date | Company | Role | Score | Status | PDF | Report | Notes | URL |
|---|------|---------|------|-------|--------|-----|--------|-------|-----|
| 1 | 2026-10-01 | Acme | Backend Engineer | 4.2/5 | Applied | ✅ | [001](../reports/001-acme-2026-10-01.md) | Deadline 24 Oct 2026 | [ashby](https://jobs.ashbyhq.com/acme/123) |
| 2 | 2026-10-02 | Beta | .NET Developer | N/A | Evaluated | ❌ | | | https://jobs.beta.test/net-dev |
"""

REPORT = """# Report

| TL;DR | **Great** fit for backend work |

```yaml
final_decision: Strong apply
legitimacy_tier: High Confidence
risk_level: Low
top_strengths:
  - C# depth
soft_gaps:
  - No cloud cert
```
"""


class SeedTests(TestCase):
    def test_defaults_seeded(self):
        self.assertEqual(Bucket.objects.count(), 3)
        self.assertTrue(Status.objects.filter(name="Applied", counts_as_applied=True).exists())
        self.assertTrue(DocumentKind.objects.filter(name="Cover letter").exists())
        self.assertEqual(SiteConfig.load().pk, 1)


class ParsingTests(TestCase):
    def test_tracker_rows(self):
        rows = careerops.parse_tracker_table(TRACKER)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["score"], 4.2)
        self.assertEqual(rows[0]["report"], "reports/001-acme-2026-10-01.md")
        self.assertIsNone(rows[1]["score"])

    def test_tracker_url_extracted_from_markdown_link_and_bare_cell(self):
        # career-ops renders a URL cell as a markdown link with a short label
        # once the raw URL is long (AGENTS.md "URL cell rendering" #3516), or
        # bare when the link form can't carry it. Both must yield the href.
        rows = careerops.parse_tracker_table(TRACKER)
        self.assertEqual(rows[0]["url"], "https://jobs.ashbyhq.com/acme/123")
        self.assertEqual(rows[1]["url"], "https://jobs.beta.test/net-dev")

    def test_machine_summary_and_deadline(self):
        s = careerops.parse_machine_summary(REPORT)
        self.assertEqual(s["final_decision"], "Strong apply")
        self.assertEqual(s["top_strengths"], ["C# depth"])
        self.assertEqual(careerops.parse_tldr(REPORT), "Great fit for backend work")
        self.assertEqual(careerops.parse_deadline("Deadline 24 Oct 2026"), date(2026, 10, 24))

    def test_checker_output(self):
        out = "✅ active  https://x.test/job\n   Apply button found\n"
        self.assertEqual(liveness.parse_checker_output(out), ("active", "Apply button found"))
        self.assertIsNone(liveness.parse_checker_output("nothing"))

    def test_bdjobs_url_normalized(self):
        self.assertIn("ln=1", liveness.normalize_url("https://jobs.bdjobs.com/h/details/123"))


class ImportTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "data").mkdir()
        (root / "reports").mkdir()
        (root / "output").mkdir()
        (root / "data" / "applications.md").write_text(TRACKER, encoding="utf-8")
        (root / "reports" / "001-acme-2026-10-01.md").write_text(REPORT, encoding="utf-8")
        (root / "output" / "cv-jane-acme-2026-10-01.pdf").write_bytes(b"%PDF-1.4")
        (root / "output" / "acme-cover.pdf").write_bytes(b"%PDF-1.4")
        config = SiteConfig.load()
        config.careerops_path = str(root)
        config.save()
        self.user = get_user_model().objects.create_user("importer", password="x" * 20, is_staff=True)

    def test_import_is_idempotent_and_keeps_local_status(self):
        config = SiteConfig.load()
        careerops.import_all(config, self.user)
        app = Application.objects.get(owner=self.user, careerops_num=1)
        self.assertEqual(app.status.name, "Applied")
        self.assertEqual(app.summary, "Great fit for backend work")
        self.assertEqual(app.deadline, date(2026, 10, 24))
        self.assertEqual({i.kind for i in app.insights.all()}, {"strength", "gap"})
        kinds = {d.kind.name for d in app.documents.all()}
        self.assertEqual(kinds, {"CV", "Cover letter", "Report"})

        app.status = Status.objects.get(name="Interview")
        app.save()
        careerops.import_all(config, self.user)
        app.refresh_from_db()
        self.assertEqual(app.status.name, "Interview")
        self.assertEqual(Application.objects.filter(owner=self.user).count(), 2)
        self.assertEqual(Document.objects.filter(application=app).count(), 3)

        careerops.import_all(config, self.user, sync_status=True)
        app.refresh_from_db()
        self.assertEqual(app.status.name, "Applied")

    def test_import_needs_path(self):
        config = SiteConfig.load()
        config.careerops_path = ""
        with self.assertRaises(careerops.ImportErrorMessage):
            careerops.import_all(config, self.user)

    def test_two_people_can_import_the_same_tracker_without_clashing(self):
        other = get_user_model().objects.create_user("other", password="x" * 20, is_staff=True)
        config = SiteConfig.load()
        careerops.import_all(config, self.user)
        careerops.import_all(config, other)  # same row numbers, different owner: must not collide
        self.assertEqual(Application.objects.filter(owner=self.user).count(), 2)
        self.assertEqual(Application.objects.filter(owner=other).count(), 2)


class ModelTests(TestCase):
    def test_match_percent_uses_configured_scale(self):
        status = Status.objects.get(name="Evaluated")
        app = Application.objects.create(company="A", role="B", status=status, score=4.0)
        self.assertEqual(app.match_percent(5), 80)
        self.assertEqual(app.match_percent(10), 40)
        app.score = None
        self.assertIsNone(app.match_percent())

    def test_expired_posting_moves_to_closed_unless_applied(self):
        config = SiteConfig.load()
        evaluated = Application.objects.create(company="A", role="B", status=Status.objects.get(name="Evaluated"), live_state="expired")
        applied = Application.objects.create(company="C", role="D", status=Status.objects.get(name="Applied"), live_state="expired")
        self.assertTrue(evaluated.effective_bucket(config).is_closed)
        self.assertFalse(applied.effective_bucket(config).is_closed)
        config.auto_close_expired = False
        self.assertFalse(evaluated.effective_bucket(config).is_closed)

    def test_source_assigned_from_url(self):
        app = Application.objects.create(
            company="A", role="B", status=Status.objects.get(name="Evaluated"), url="https://www.linkedin.com/jobs/view/1"
        )
        self.assertEqual(app.source.name, "LinkedIn")


class ViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("tester", password="x" * 20)
        self.client.force_login(self.user)
        self.evaluated = Status.objects.get(name="Evaluated")
        self.app = Application.objects.create(
            owner=self.user, company="Acme", role="Dev", status=self.evaluated, score=4.5, summary="Short summary",
            deadline=date.today() + timedelta(days=2),
        )

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_dashboard_renders_match_and_summary(self):
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "90%")
        self.assertContains(r, "Short summary")
        self.assertContains(r, "Strong")

    def test_labels_come_from_config(self):
        config = SiteConfig.load()
        config.site_title = "My custom board"
        config.save()
        Bucket.objects.filter(key="apply").update(label="Queue")
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "My custom board")
        self.assertContains(r, "Queue (1)")

    def test_score_band_editable(self):
        ScoreBand.objects.all().delete()
        ScoreBand.objects.create(label="Great", min_percent=50, color="#00ff00")
        self.assertContains(self.client.get(reverse("dashboard")), "Great")

    def test_set_status_stamps_applied_date(self):
        applied = Status.objects.get(name="Applied")
        r = self.client.post(reverse("set_status", args=[self.app.pk]), {"status": applied.pk})
        self.assertEqual(r.status_code, 200)
        self.app.refresh_from_db()
        self.assertEqual(self.app.status, applied)
        self.assertEqual(self.app.applied_date, date.today())
        self.assertEqual(self.app.events.count(), 1)

    def test_set_status_requires_post_and_csrf(self):
        self.assertEqual(self.client.get(reverse("set_status", args=[self.app.pk])).status_code, 405)
        from django.test import Client
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        r = strict.post(reverse("set_status", args=[self.app.pk]), {"status": self.evaluated.pk})
        self.assertEqual(r.status_code, 403)

    def test_admin_documents_are_served_only_from_allowed_folders(self):
        boss = get_user_model().objects.create_user("boss", password="x" * 20, is_staff=True)
        boss_app = Application.objects.create(owner=boss, company="S", role="R", status=self.evaluated)
        self.client.force_login(boss)
        with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as other:
            good = Path(allowed) / "cv.pdf"
            good.write_bytes(b"%PDF-1.4")
            bad = Path(other) / "secret.pdf"
            bad.write_bytes(b"%PDF-1.4")
            config = SiteConfig.load()
            config.careerops_path = allowed
            config.save()
            kind = DocumentKind.objects.get(name="CV")
            ok = Document.objects.create(application=boss_app, kind=kind, title="cv", source_path=str(good))
            nope = Document.objects.create(application=boss_app, kind=kind, title="s", source_path=str(bad))
            r = self.client.get(reverse("document_file", args=[ok.pk]))
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r["Content-Type"], "application/pdf")
            r.close()
            self.assertEqual(self.client.get(reverse("document_file", args=[nope.pk])).status_code, 404)

    def test_ordinary_users_cannot_read_server_paths_through_documents(self):
        with tempfile.TemporaryDirectory() as folder:
            secret = Path(folder) / "cv.pdf"
            secret.write_bytes(b"%PDF-1.4")
            config = SiteConfig.load()
            config.careerops_path = folder  # a server-side folder, set by an admin
            config.save()
            doc = Document.objects.create(application=self.app, kind=DocumentKind.objects.get(name="CV"), title="cv", source_path=str(secret))
            self.assertEqual(self.client.get(reverse("document_file", args=[doc.pk])).status_code, 404)

    def test_uploaded_documents_are_served_to_their_owner_only(self):
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            from django.core.files.base import ContentFile

            doc = Document(application=self.app, kind=DocumentKind.objects.get(name="CV"), title="cv")
            doc.file.save("cv.pdf", ContentFile(b"%PDF-1.4"), save=True)
            r = self.client.get(reverse("document_file", args=[doc.pk]))
            self.assertEqual(r.status_code, 200)
            r.close()
            intruder = get_user_model().objects.create_user("intruder", password="x" * 20)
            self.client.force_login(intruder)
            self.assertEqual(self.client.get(reverse("document_file", args=[doc.pk])).status_code, 404)


class PaperlessTests(TestCase):
    def test_client_requires_credentials(self):
        with self.assertRaises(PaperlessError):
            PaperlessClient("", "")

    def test_disabled_by_default(self):
        with self.assertRaises(PaperlessError):
            PaperlessClient.from_config(SiteConfig.load())

    @override_settings()
    def test_push_stores_id(self):
        with tempfile.TemporaryDirectory() as root:
            pdf = Path(root) / "cv.pdf"
            pdf.write_bytes(b"%PDF-1.4")
            config = SiteConfig.load()
            config.careerops_path = root
            config.paperless_enabled = True
            config.paperless_url = "http://paperless.test"
            config.paperless_token = "t"
            config.save()
            app = Application.objects.create(company="Acme", role="Dev", status=Status.objects.get(name="Evaluated"))
            doc = Document.objects.create(application=app, kind=DocumentKind.objects.get(name="CV"), title="cv", source_path=str(pdf))
            client = PaperlessClient.from_config(config, session=mock.MagicMock())
            with mock.patch.object(PaperlessClient, "find_document", return_value=None), \
                 mock.patch.object(PaperlessClient, "ensure_named", return_value=1), \
                 mock.patch.object(PaperlessClient, "upload", return_value="task-1"), \
                 mock.patch.object(PaperlessClient, "wait_for_document", return_value=42):
                self.assertEqual(push_document(doc, client, config), 42)
            doc.refresh_from_db()
            self.assertEqual(doc.paperless_id, 42)
            self.assertEqual(doc.paperless_error, "")

    def test_push_records_error_for_missing_file(self):
        config = SiteConfig.load()
        app = Application.objects.create(company="Acme", role="Dev", status=Status.objects.get(name="Evaluated"))
        doc = Document.objects.create(application=app, kind=DocumentKind.objects.get(name="CV"), title="cv", source_path="C:/nope/x.pdf")
        client = PaperlessClient("http://paperless.test", "t", session=mock.MagicMock())
        self.assertIsNone(push_document(doc, client, config))
        doc.refresh_from_db()
        self.assertIn("not found", doc.paperless_error)


class LivenessTests(TestCase):
    @mock.patch("tracker.services.liveness.safe_get")
    def test_http_check_uses_admin_phrases(self, get):
        from tracker.models import ExpiredPhrase
        ExpiredPhrase.objects.create(phrase="custom closed text")
        get.return_value = mock.Mock(status_code=200, text="<html>Custom Closed Text. Apply</html>")
        state, _ = liveness.check_http("https://x.test", SiteConfig.load())
        self.assertEqual(state, "expired")

    @mock.patch("tracker.services.liveness.safe_get")
    def test_http_active_and_404(self, get):
        get.return_value = mock.Mock(status_code=200, text="<button>Apply now</button>")
        self.assertEqual(liveness.check_http("https://x.test", SiteConfig.load())[0], "active")
        get.return_value = mock.Mock(status_code=404, text="")
        self.assertEqual(liveness.check_http("https://x.test", SiteConfig.load())[0], "expired")

    def test_private_and_non_http_links_are_not_fetched(self):
        config = SiteConfig.load()
        config.liveness_mode = "http"  # the seeded default may be the local browser checker
        state, detail = liveness.check_url("http://127.0.0.1:8000/admin/", config)
        self.assertEqual(state, "uncertain")
        self.assertIn("not checked", detail)
        self.assertEqual(liveness.check_url("file:///etc/passwd", config)[0], "uncertain")
        self.assertEqual(liveness.check_url("http://169.254.169.254/latest/meta-data/", config)[0], "uncertain")

    def test_a_run_only_touches_its_owners_applications(self):
        a = get_user_model().objects.create_user("a", password="x" * 20)
        b = get_user_model().objects.create_user("b", password="x" * 20)
        evaluated = Status.objects.get(name="Evaluated")
        mine = Application.objects.create(owner=a, company="Mine", role="R", status=evaluated, url="https://a.example.com/1")
        theirs = Application.objects.create(owner=b, company="Theirs", role="R", status=evaluated, url="https://b.example.com/1")
        with mock.patch("tracker.services.liveness.check_url", return_value=("expired", "gone")):
            run = liveness.start_run(a, background=False)
        self.assertEqual((run.total, run.done), (1, 1))
        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertEqual(mine.live_state, "expired")
        self.assertEqual(theirs.live_state, "unknown")


class GoogleLoginTests(TestCase):
    def setUp(self):
        from django.contrib.sites.models import Site
        from allauth.socialaccount.models import SocialApp

        self.config = SiteConfig.load()
        app = SocialApp.objects.create(provider="google", name="Google", client_id="test-id", secret="test-secret")
        app.sites.add(Site.objects.get_current())

    def _request(self):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        request = RequestFactory().get("/accounts/google/login/callback/")
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def _login(self, email, verified=True, existing=False):
        from allauth.account.models import EmailAddress
        from allauth.socialaccount.models import SocialLogin

        user = get_user_model().objects.create_user("existing", email=email) if existing else get_user_model()(email=email)
        return SocialLogin(user=user, email_addresses=[EmailAddress(email=email, verified=verified)])

    def test_allowlist_rules(self):
        self.config.google_allowed_emails = "Me@Gmail.com\n@acme.com\n"
        self.assertTrue(self.config.google_email_allowed("me@gmail.com"))
        self.assertTrue(self.config.google_email_allowed("anyone@ACME.com"))
        self.assertFalse(self.config.google_email_allowed("other@gmail.com"))
        self.assertFalse(self.config.google_email_allowed("me@gmail.com.evil.test"))
        self.assertFalse(self.config.google_email_allowed(""))
        self.config.google_allowed_emails = ""
        self.assertFalse(self.config.google_email_allowed("me@gmail.com"))

    def test_login_page_button_follows_the_admin_switch(self):
        self.assertNotContains(self.client.get(reverse("account_login")), "Continue with Google")
        self.config.google_login_enabled = True
        self.config.save()
        r = self.client.get(reverse("account_login"))
        self.assertContains(r, "Continue with Google")
        self.assertContains(r, "/accounts/google/login/")

    def test_signup_gated_by_allowlist_and_verified_email(self):
        from tracker.auth import SocialAdapter

        adapter = SocialAdapter()
        self.config.google_login_enabled = True
        self.config.google_allowed_emails = "me@gmail.com"
        self.config.save()
        self.assertTrue(adapter.is_open_for_signup(self._request(), self._login("me@gmail.com")))
        self.assertFalse(adapter.is_open_for_signup(self._request(), self._login("stranger@gmail.com")))
        self.assertFalse(adapter.is_open_for_signup(self._request(), self._login("me@gmail.com", verified=False)))
        self.config.google_login_enabled = False
        self.config.save()
        self.assertFalse(adapter.is_open_for_signup(self._request(), self._login("me@gmail.com")))

    def test_pre_login_blocks_disabled_and_unlisted_but_lets_existing_users_in(self):
        from allauth.core.exceptions import ImmediateHttpResponse
        from tracker.auth import SocialAdapter

        adapter = SocialAdapter()
        with self.assertRaises(ImmediateHttpResponse):  # switched off
            adapter.pre_social_login(self._request(), self._login("me@gmail.com"))
        self.config.google_login_enabled = True
        self.config.save()
        with self.assertRaises(ImmediateHttpResponse):  # new, not listed
            adapter.pre_social_login(self._request(), self._login("stranger@gmail.com"))
        adapter.pre_social_login(self._request(), self._login("owner@gmail.com", existing=True))  # no exception

    def test_google_users_never_get_admin_access(self):
        from tracker.auth import SocialAdapter

        user = SocialAdapter().populate_user(self._request(), self._login("me@gmail.com"), {"email": "me@gmail.com"})
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_local_signup_is_closed(self):
        from tracker.auth import AccountAdapter

        self.assertFalse(AccountAdapter().is_open_for_signup(self._request()))


class LandingTests(TestCase):
    def test_public_and_uses_admin_text(self):
        config = SiteConfig.load()
        config.landing_headline = "Custom headline here"
        config.landing_github_url = "https://github.com/example/stillopen"
        config.save()
        r = self.client.get(reverse("landing"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Custom headline here")
        self.assertContains(r, "https://github.com/example/stillopen")
        self.assertContains(r, reverse("account_login"))
        self.assertNotContains(r, "Open dashboard")

    def test_does_not_leak_tracked_jobs(self):
        Application.objects.create(company="SecretCorp", role="Hidden", status=Status.objects.get(name="Evaluated"))
        self.assertNotContains(self.client.get(reverse("landing")), "SecretCorp")

    def test_logged_in_visitor_sees_dashboard_link(self):
        self.client.force_login(get_user_model().objects.create_user("u", password="x" * 20))
        self.assertContains(self.client.get(reverse("landing")), "Open dashboard")

    def test_can_be_switched_off(self):
        config = SiteConfig.load()
        config.landing_enabled = False
        config.save()
        r = self.client.get(reverse("landing"))
        self.assertRedirects(r, reverse("dashboard"), fetch_redirect_response=False)
        follow = self.client.get(reverse("dashboard"))  # anonymous visitors then land on sign-in
        self.assertIn("/accounts/login/", follow["Location"])

    def test_dashboard_moved_and_still_protected(self):
        self.assertEqual(reverse("dashboard"), "/dashboard/")
        r = self.client.get(reverse("dashboard"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])
