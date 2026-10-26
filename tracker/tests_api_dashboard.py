"""The dashboard API: everything the classic dashboard page showed, with the same rules, for the new app."""
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from tracker.models import (
    Application, CVVersion, Document, DocumentKind, Insight, Interview, ScanLogEntry, ScanRun, SearchArea, SiteConfig, Source, Status, UserProfile,
)
from tracker.services import guide
from tracker.tests_api import BASE, PW, job, person

User = get_user_model()


class DashboardPayload(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        self.client.force_login(self.a)

    def get(self):
        return self.client.get(f"{BASE}/dashboard").json()

    def test_every_job_carries_what_the_card_shows(self):
        source = Source.objects.create(name="Acme Careers", host_contains="acme.example")
        kind = DocumentKind.objects.first() or DocumentKind.objects.create(name="Other")
        app = job(
            self.a, source=source, advertised_pay="USD 90k", risk="medium", next_action="Ask about the team", notes="Met them at a fair",
            decision="Consider seriously, but check the pay first", ai_method="keywords", applied_date=timezone.localdate(), applied_channel="email",
            follow_up_date=timezone.localdate() + timedelta(days=3), score=4.0,
            status=Status.objects.filter(counts_as_applied=True).first(),
        )
        cv = CVVersion.objects.create(owner=self.a, application=app, kind="tailored", label="x", content="c", check_report=[{"claim": "x"}])
        app.applied_cv = cv
        app.save()
        Insight.objects.create(application=app, kind="strength", text="Strong Python")
        Insight.objects.create(application=app, kind="gap", text="No Kubernetes")
        Document.objects.create(application=app, kind=kind, title="report.md", paperless_error="boom")
        data = self.get()
        j = data["jobs"][0]
        self.assertEqual((j["source"], j["advertised_pay"], j["risk"], j["next_action"], j["notes"]), ("Acme Careers", "USD 90k", "medium", "Ask about the team", "Met them at a fair"))
        self.assertEqual(j["ai_method"], "keywords")
        self.assertEqual(j["applied_channel"], "Email")
        self.assertEqual(j["applied_cv"], {"id": cv.pk, "label": f"CV v{cv.pk}"})
        self.assertEqual(j["follow_up_date"], (timezone.localdate() + timedelta(days=3)).isoformat())
        self.assertEqual(j["cv"], {"id": cv.pk, "label": f"CV v{cv.pk}", "flagged": True, "approved": False})
        self.assertEqual(j["strengths"], ["Strong Python"])
        self.assertEqual(j["gaps"], ["No Kubernetes"])
        self.assertEqual(j["documents"], [{"id": j["documents"][0]["id"], "kind": kind.name, "title": "report.md", "paperless_id": None, "paperless_error": "boom"}])
        self.assertTrue(j["counts_as_applied"])
        self.assertTrue(j["ai_evaluated"] is False and j["evaluated"] is True)
        for gone in ("edit_url", "apply_url", "tailor_url", "cover_url", "prep_url"):
            self.assertNotIn(gone, j)

    def test_an_approved_cv_is_not_flagged_for_review(self):
        app = job(self.a)
        CVVersion.objects.create(owner=self.a, application=app, kind="tailored", content="c", check_report=[{"claim": "x"}], approved=True)
        self.assertTrue(self.get()["jobs"][0]["cv"]["approved"])

    def test_card_carries_recognized_tech_skills_against_the_owners_knowledge(self):
        from tracker.models import KnowledgeSource

        KnowledgeSource.objects.create(owner=self.a, title="CV", kind="cv", text="Backend engineer with Docker experience.")
        job(self.a, description="We need someone who knows Docker and Kubernetes well.")
        j = self.get()["jobs"][0]
        by_name = {t["name"]: t for t in j["tech_skills"]}
        self.assertTrue(by_name["Docker"]["have"])
        self.assertFalse(by_name["Kubernetes"]["have"])

    def test_the_fit_badge_follows_the_classic_rule(self):
        job(self.a)
        self.assertIsNone(self.get()["jobs"][0]["fit_badge"])  # no places yet: "Fit unknown" is not shown
        SearchArea.objects.create(owner=self.a, place="Malaysia", allow_onsite=True)
        data = self.get()
        self.assertTrue(data["has_areas"])
        self.assertIn(data["jobs"][0]["fit_badge"], {"fits", "check", "unknown"})
        self.assertEqual(data["jobs"][0]["fit_badge"], {"ok": "fits", "warn": "check"}.get(data["jobs"][0]["fit_level"], "unknown"))

    def test_the_header_facts(self):
        config = SiteConfig.load()
        data = self.get()
        self.assertEqual(data["urgent_days"], config.urgent_days)
        self.assertIsNone(data["checked_at"])
        self.assertIsNone(data["scan"])
        self.assertFalse(data["paperless_on"])
        self.assertFalse(data["can_import"])
        self.assertEqual(data["paperless_url"], "")
        self.assertIn("prep_enabled", data)
        self.assertTrue(data["judge_label"])
        self.assertTrue(data["band_labels"])
        when = timezone.now() - timedelta(hours=3)
        job(self.a, live_checked_at=when)
        job(self.a, live_checked_at=when - timedelta(days=1))
        self.assertEqual(self.get()["checked_at"], when.isoformat())

    def test_coming_up_lists_the_next_five_pending_future_interviews_of_mine_only(self):
        app = job(self.a, company="AliceCo", role="Dev")
        theirs = job(self.b, company="BobCo")
        now = timezone.now()
        for n in range(1, 8):
            Interview.objects.create(owner=self.a, application=app, scheduled_at=now + timedelta(days=n), kind="video")
        Interview.objects.create(owner=self.a, application=app, scheduled_at=now - timedelta(days=1))  # already happened
        Interview.objects.create(owner=self.a, application=app, scheduled_at=now + timedelta(days=1), outcome="done")  # not pending
        Interview.objects.create(owner=self.b, application=theirs, scheduled_at=now + timedelta(hours=1))
        data = self.get()["upcoming_interviews"]
        self.assertEqual(len(data), 5)
        self.assertEqual(data[0]["kind"], "Video call")
        self.assertEqual((data[0]["company"], data[0]["role"], data[0]["job_id"]), ("AliceCo", "Dev", app.pk))
        self.assertNotIn("BobCo", str(data))
        self.assertEqual([i["when"] for i in data], sorted(i["when"] for i in data))

    def test_followups_carry_the_applied_date(self):
        today = timezone.localdate()
        job(self.a, applied_date=today - timedelta(days=9), follow_up_date=today, status=Status.objects.filter(is_terminal=False).first())
        f = self.get()["followups"][0]
        self.assertEqual(f["applied_date"], (today - timedelta(days=9)).isoformat())

    def test_a_repost_comes_with_the_evidence(self):
        from tracker.models import JobSource, Posting, PostingSighting

        src = JobSource.objects.create(owner=self.a, name="Board", connector="greenhouse", board_token="board")
        first = Posting.objects.create(source=src, url="https://b.example/1", company="Acme", title="Dev", title_key="acme|dev")
        second = Posting.objects.create(source=src, url="https://b.example/2", company="Acme", title="Dev", title_key="acme|dev")
        today = timezone.localdate()
        PostingSighting.objects.create(posting=first, seen_date=today - timedelta(days=5))
        PostingSighting.objects.create(posting=second, seen_date=today)
        job(self.a, posting=second, url=second.url)
        r = self.get()["jobs"][0]["repost"]
        self.assertEqual((r["distinct_urls"], r["distinct_dates"]), (2, 2))
        self.assertTrue(r["first_seen"] and r["last_seen"])

    @mock.patch.dict("os.environ", {"PAPERLESS_URL": ""})
    def test_paperless_and_import_are_for_site_admins_with_the_setting(self):
        SiteConfig.objects.update(paperless_enabled=True, paperless_url="https://paper.example.com/", careerops_path="/tmp/x")
        data = self.get()  # a normal person
        self.assertFalse(data["paperless_on"])
        self.assertFalse(data["can_import"])
        self.assertEqual(data["paperless_url"], "")
        staff = User.objects.create_user("root", email="root@example.com", password=PW, is_staff=True)
        self.client.force_login(staff)
        data = self.get()
        self.assertTrue(data["paperless_on"])
        self.assertEqual(data["paperless_url"], "https://paper.example.com")
        self.assertTrue(data["can_import"])

    def test_the_number_of_queries_does_not_grow_with_the_number_of_jobs(self):
        kind = DocumentKind.objects.first() or DocumentKind.objects.create(name="Other")

        def add(n):
            for i in range(n):
                app = job(self.a, company=f"Co{i}-{Application.objects.count()}", score=3.0, live_checked_at=timezone.now())
                Insight.objects.create(application=app, kind="strength", text="s")
                Insight.objects.create(application=app, kind="gap", text="g")
                Document.objects.create(application=app, kind=kind, title="d")
                CVVersion.objects.create(owner=self.a, application=app, kind="tailored", content="c")
                Interview.objects.create(owner=self.a, application=app, scheduled_at=timezone.now() + timedelta(days=1))

        add(3)
        self.get()  # warm caches (the first call may start a search)
        with CaptureQueriesContext(connection) as few:
            self.get()
        add(27)
        with CaptureQueriesContext(connection) as many:
            data = self.get()
        self.assertEqual(len(data["jobs"]), 30)
        self.assertLessEqual(len(many), len(few) + 2, "the dashboard must not run queries per job")


class ScanProgress(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        self.client.force_login(self.a)

    def status(self, log=True):
        return self.client.get(f"{BASE}/scan/status" + ("?log=1" if log else "")).json()

    def test_no_run_yet(self):
        data = self.status()
        self.assertEqual((data["running"], data["phase"], data["entries"], data["started_at"], data["note"]), (False, "done", [], None, ""))
        self.assertNotIn("entries", self.status(log=False))  # the log is only sent when asked for

    def test_the_log_note_and_phases_mirror_the_classic_page(self):
        run = ScanRun.objects.create(owner=self.a, running=True, total=10, done=4, found=30, added=2, note="Only the best were added")
        ScanLogEntry.objects.create(run=run, source_name="Acme", connector="greenhouse", found=5, matched=3, added=2, duplicates=1, outside=1)
        ScanLogEntry.objects.create(run=run, source_name="Broken", connector="lever", error="HTTP 500")
        data = self.status()
        self.assertEqual(data["phase"], "reading")
        self.assertEqual(data["note"], "Only the best were added")
        self.assertTrue(data["started_at"])
        self.assertEqual(data["entries"][0], {"source": "Acme", "connector": "Greenhouse", "found": 5, "matched": 3, "added": 2, "duplicates": 1, "outside": 1, "error": ""})
        self.assertEqual(data["entries"][1]["error"], "HTTP 500")
        ScanRun.objects.filter(pk=run.pk).update(done=10)
        self.assertEqual(self.status()["phase"], "sorting")
        ScanRun.objects.filter(pk=run.pk).update(running=False)
        self.assertEqual(self.status()["phase"], "done")

    def test_the_dashboard_carries_the_same_summary(self):
        run = ScanRun.objects.create(owner=self.a, running=False, total=3, done=3, found=9, added=1)
        ScanLogEntry.objects.create(run=run, source_name="Acme", connector="greenhouse")
        scan = self.client.get(f"{BASE}/dashboard").json()["scan"]
        self.assertEqual((scan["found"], scan["added"], scan["phase"]), (9, 1, "done"))
        self.assertNotIn("entries", scan)  # the dashboard says how many rows the log has; the rows come when the log is opened
        self.assertEqual(scan["entries_count"], 1)

    def test_someone_elses_search_is_never_shown(self):
        ScanRun.objects.create(owner=self.b, running=False, total=3, done=3, found=99, added=7, note="bob's note")
        data = self.status()
        self.assertEqual(data["found"], 0)
        self.assertNotIn("bob", str(data))
        self.assertIsNone(self.client.get(f"{BASE}/dashboard").json()["scan"])

    def test_starting_a_search_answers_with_the_same_shape(self):
        with mock.patch("tracker.services.scan.threading.Thread"):
            r = self.client.post(f"{BASE}/scan", content_type="application/json")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        for key in ("running", "done", "total", "found", "added", "note", "started_at", "phase", "entries_count", "error"):
            self.assertIn(key, data)
        self.assertNotIn("entries", data)


class WhoAmI(TestCase):
    def setUp(self):
        cache.clear()
        self.a = person("alice")
        self.staff = User.objects.create_user("root", email="root@example.com", password=PW, is_staff=True)

    def me(self, user):
        self.client.force_login(user)
        return self.client.get(f"{BASE}/me").json()

    def test_the_extra_fields(self):
        SiteConfig.objects.update(site_title="Where Is My Job", prep_enabled=True, mcp_remote_enabled=True)
        data = self.me(self.a)
        self.assertEqual(data["site_title"], "Where Is My Job")
        self.assertTrue(data["prep_enabled"])
        self.assertTrue(data["assistant_enabled"])
        SiteConfig.objects.update(prep_enabled=False, mcp_remote_enabled=False)
        data = self.me(self.a)
        self.assertFalse(data["prep_enabled"])
        self.assertFalse(data["assistant_enabled"])

    def test_the_staff_banners_are_for_staff_only(self):
        with mock.patch.object(SiteConfig, "signup_open", new_callable=mock.PropertyMock, return_value=True), mock.patch("tracker.context.integrations.require_email_confirmation", return_value=False), mock.patch("tracker.context.legal.has_placeholders", return_value=True):
            staff = self.me(self.staff)
            other = self.me(self.a)
        self.assertTrue(staff["email_unverified_signups"])
        self.assertTrue(staff["legal_has_blanks"])
        self.assertFalse(other["email_unverified_signups"])
        self.assertFalse(other["legal_has_blanks"])
        with mock.patch.object(SiteConfig, "signup_open", new_callable=mock.PropertyMock, return_value=True), mock.patch("tracker.context.integrations.require_email_confirmation", return_value=True), mock.patch("tracker.context.legal.has_placeholders", return_value=False):
            staff = self.me(self.staff)
        self.assertFalse(staff["email_unverified_signups"])
        self.assertFalse(staff["legal_has_blanks"])

    def test_jooble_dormant_banner_only_when_enabled_sitewide_and_no_key(self):
        from tracker.models import JobSource

        self.assertFalse(self.me(self.staff)["jooble_sources_dormant"])  # no Jooble source at all yet
        JobSource.objects.create(name="Jooble Bangladesh", connector="jooble", board_token="bd", enabled=True)
        self.assertTrue(self.me(self.staff)["jooble_sources_dormant"])
        self.assertFalse(self.me(self.a)["jooble_sources_dormant"])  # staff-only, same as the other two banners
        SiteConfig.objects.update(jooble_api_key="some-key")
        self.assertFalse(self.me(self.staff)["jooble_sources_dormant"])  # a key turns it off
        SiteConfig.objects.update(jooble_api_key="")
        JobSource.objects.filter(connector="jooble").update(enabled=False)
        self.assertFalse(self.me(self.staff)["jooble_sources_dormant"])  # disabled source, nothing to nudge about
        JobSource.objects.filter(connector="jooble").update(enabled=True)
        JobSource.objects.filter(connector="jooble").update(owner=self.a)
        self.assertFalse(self.me(self.staff)["jooble_sources_dormant"])  # a per-user source is that user's own choice, not site-wide

    def test_usajobs_dormant_banner_needs_both_a_key_and_an_email(self):
        from tracker.models import JobSource

        self.assertFalse(self.me(self.staff)["usajobs_sources_dormant"])  # no USAJobs source at all yet
        JobSource.objects.create(name="USAJobs", connector="usajobs", board_token="x", enabled=True)
        self.assertTrue(self.me(self.staff)["usajobs_sources_dormant"])
        self.assertFalse(self.me(self.a)["usajobs_sources_dormant"])  # staff-only
        SiteConfig.objects.update(usajobs_api_key="some-key")
        self.assertTrue(self.me(self.staff)["usajobs_sources_dormant"])  # a key alone is not enough
        SiteConfig.objects.update(usajobs_email="admin@example.com")
        self.assertFalse(self.me(self.staff)["usajobs_sources_dormant"])  # key and email together turn it off


class ImportFromCareerOps(TestCase):
    def setUp(self):
        cache.clear()
        self.a = person("alice")
        self.staff = User.objects.create_user("root", email="root@example.com", password=PW, is_staff=True)

    def post(self):
        return self.client.post(f"{BASE}/import", content_type="application/json")

    def test_a_normal_person_is_refused(self):
        self.client.force_login(self.a)
        with mock.patch("tracker.api.routes.careerops.import_all") as run:
            self.assertEqual(self.post().status_code, 403)
        run.assert_not_called()

    def test_signed_out_is_401(self):
        self.assertEqual(self.post().status_code, 401)

    def test_a_site_admin_imports_into_their_own_tracker_and_gets_the_classic_wording(self):
        self.client.force_login(self.staff)
        with mock.patch("tracker.api.routes.careerops.import_all", return_value={"created": 3, "updated": 2, "documents": 1}) as run:
            r = self.post()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["message"], "Imported: 3 new, 2 refreshed")
        self.assertEqual(run.call_args.args[1], self.staff)

    def test_a_missing_folder_is_a_plain_error(self):
        self.client.force_login(self.staff)
        SiteConfig.objects.update(careerops_path="")
        r = self.post()
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.json()["error"])


class NextStepLinksStayInTheApp(TestCase):
    def setUp(self):
        self.u = person("quinn")
        self.profile = UserProfile.for_user(self.u)

    def card(self, percent=None):
        app = Application.objects.create(owner=self.u, company="Globex", role="Dev", description="text", status=Status.objects.get(name="Saved"))
        return {"app": app, "percent": percent, "cv": None}

    def complete(self):
        UserProfile.objects.filter(pk=self.profile.pk).update(profile_cv="I build things " * 20, target_roles="Dev")
        return UserProfile.objects.get(pk=self.profile.pk)

    def test_each_suggestion_points_into_the_app(self):
        self.assertEqual(guide.next_step(self.profile, [])["url"], "/app/profile?welcome=1")
        profile = self.complete()
        self.assertEqual(guide.next_step(profile, [], has_areas=False)["url"], "/app/profile#areas")
        self.assertEqual(guide.next_step(profile, [])["url"], "/app/jobs/add")
        card = self.card()
        self.assertEqual(guide.next_step(profile, [card])["url"], f"#job-{card['app'].pk}")

    def test_todays_practice_opens_the_app_screen(self):
        class Done:
            is_complete = True
            missing_fields = []

        class Plan:
            pk = 7
            title = "Kubernetes"

        expired = Application(status=Status.objects.get(name="Saved"), live_state="expired")
        step = guide.next_step(Done(), [{"app": expired, "percent": 10, "cv": None}], has_areas=True, prep_due=[Plan()])
        self.assertEqual(step["url"], "/app/prep/7/today")

    def test_no_classic_url_is_built_here(self):
        import inspect

        from tracker.api import routes

        for module in (guide, routes):
            self.assertNotIn("reverse(", inspect.getsource(module))
