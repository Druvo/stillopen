"""Job-board scanning: connectors, matching, dedup, multi-user isolation, rate limiting."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from tracker.models import Application, JobSource, ScanLogEntry, ScanRun, Status, UserProfile
from tracker.services import scan
from tracker.services.netguard import FetchError

User = get_user_model()
PW = "correct-horse-battery-staple"


def user(name, **profile):
    u = User.objects.create_user(name, password=PW)
    if profile:
        UserProfile.objects.filter(user=u).update(**profile)
    return u


GREENHOUSE_PAYLOAD = {
    "jobs": [
        {"title": "Senior Backend Engineer", "absolute_url": "https://boards.greenhouse.io/acme/1", "location": {"name": "Remote"}},
        {"title": "Marketing Manager", "absolute_url": "https://boards.greenhouse.io/acme/2", "location": {"name": "NYC"}},
    ]
}
LEVER_PAYLOAD = [
    {"text": "Backend Developer", "hostedUrl": "https://jobs.lever.co/acme/1", "categories": {"location": "Remote"}},
]
ASHBY_PAYLOAD = {
    "jobs": [
        {"title": "Platform Engineer", "jobUrl": "https://jobs.ashbyhq.com/acme/1", "location": "Remote"},
    ]
}


class ConnectorTests(TestCase):
    @mock.patch("tracker.services.scan.safe_get")
    def test_greenhouse_parses_jobs(self, get):
        get.return_value = mock.Mock(status_code=200, json=lambda: GREENHOUSE_PAYLOAD)
        out = scan.fetch_greenhouse("acme")
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0], {"title": "Senior Backend Engineer", "url": "https://boards.greenhouse.io/acme/1", "location": "Remote"})

    @mock.patch("tracker.services.scan.safe_get")
    def test_lever_parses_postings(self, get):
        get.return_value = mock.Mock(status_code=200, json=lambda: LEVER_PAYLOAD)
        out = scan.fetch_lever("acme")
        self.assertEqual(out, [{"title": "Backend Developer", "url": "https://jobs.lever.co/acme/1", "location": "Remote"}])

    @mock.patch("tracker.services.scan.safe_get")
    def test_ashby_parses_postings(self, get):
        get.return_value = mock.Mock(status_code=200, json=lambda: ASHBY_PAYLOAD)
        out = scan.fetch_ashby("acme")
        self.assertEqual(out, [{"title": "Platform Engineer", "url": "https://jobs.ashbyhq.com/acme/1", "location": "Remote"}])

    @mock.patch("tracker.services.scan.safe_get")
    def test_non_200_raises_fetch_error(self, get):
        get.return_value = mock.Mock(status_code=404, json=lambda: {})
        with self.assertRaises(FetchError):
            scan.fetch_greenhouse("missing")

    def test_title_matching_is_case_insensitive_phrase_containment(self):
        roles = ["backend engineer"]
        self.assertTrue(scan._matches("Senior Backend Engineer", roles))
        self.assertFalse(scan._matches("Marketing Manager", roles))
        self.assertFalse(scan._matches("Backend Engineer", []))

    def test_invalid_board_token_is_rejected_before_any_request(self):
        self.assertIsNone(scan.TOKEN_RE.match("acme/../../etc"))
        self.assertIsNone(scan.TOKEN_RE.match("acme?x=1"))
        self.assertIsNotNone(scan.TOKEN_RE.match("acme-corp_1.2"))


class ScanRunTests(TestCase):
    def setUp(self):
        self.u = user("zahid", target_roles="Senior Backend Engineer")
        JobSource.objects.create(name="Acme", connector="greenhouse", board_token="acme", enabled=True)

    @mock.patch("tracker.services.scan.fetch_greenhouse")
    def test_matching_posting_is_added_once(self, fetch):
        fetch.return_value = [
            {"title": "Senior Backend Engineer", "url": "https://boards.greenhouse.io/acme/1", "location": "Remote"},
            {"title": "Marketing Manager", "url": "https://boards.greenhouse.io/acme/2", "location": "NYC"},
        ]
        run = scan.start_run(self.u, background=False)
        self.assertFalse(run.running)
        self.assertEqual(run.found, 2)
        self.assertEqual(run.added, 1)
        apps = Application.objects.filter(owner=self.u)
        self.assertEqual(apps.count(), 1)
        app = apps.first()
        self.assertEqual(app.company, "Acme")
        self.assertEqual(app.url, "https://boards.greenhouse.io/acme/1")
        entry = run.entries.get()
        self.assertEqual((entry.found, entry.matched, entry.added, entry.duplicates), (2, 1, 1, 0))

        # Scanning again must not create a duplicate for the same posting URL.
        run2 = scan.start_run(self.u, background=False)
        self.assertEqual(run2.added, 0)
        self.assertEqual(Application.objects.filter(owner=self.u).count(), 1)
        self.assertEqual(run2.entries.get().duplicates, 1)

    @mock.patch("tracker.services.scan.fetch_greenhouse")
    def test_no_target_roles_means_nothing_matches(self, fetch):
        UserProfile.objects.filter(user=self.u).update(target_roles="")
        fetch.return_value = [{"title": "Senior Backend Engineer", "url": "https://x.test/1", "location": ""}]
        run = scan.start_run(self.u, background=False)
        self.assertEqual(run.added, 0)
        self.assertFalse(Application.objects.filter(owner=self.u).exists())

    @mock.patch("tracker.services.scan.fetch_greenhouse", side_effect=FetchError("HTTP 404"))
    def test_one_source_failing_does_not_stop_the_run(self, fetch):
        JobSource.objects.create(name="Other", connector="lever", board_token="other", enabled=True)
        with mock.patch("tracker.services.scan.fetch_lever", return_value=[]):
            run = scan.start_run(self.u, background=False)
        self.assertFalse(run.running)
        self.assertEqual(run.entries.count(), 2)
        acme_entry = run.entries.get(source_name="Acme")
        self.assertIn("HTTP 404", acme_entry.error)

    def test_disabled_sources_are_not_scanned(self):
        JobSource.objects.filter(name="Acme").update(enabled=False)
        run = scan.start_run(self.u, background=False)
        self.assertEqual(run.total, 0)
        self.assertEqual(run.entries.count(), 0)

    @mock.patch("tracker.services.scan.fetch_greenhouse")
    def test_a_run_only_touches_its_owners_applications(self, fetch):
        fetch.return_value = [{"title": "Senior Backend Engineer", "url": "https://x.test/1", "location": ""}]
        other = user("other", target_roles="Senior Backend Engineer")
        scan.start_run(other, background=False)
        self.assertEqual(Application.objects.filter(owner=other).count(), 1)
        self.assertEqual(Application.objects.filter(owner=self.u).count(), 0)

    @mock.patch("tracker.services.scan.fetch_greenhouse")
    def test_stops_at_the_application_limit_instead_of_blowing_past_it(self, fetch):
        fetch.return_value = [
            {"title": "Senior Backend Engineer", "url": f"https://x.test/{i}", "location": ""} for i in range(10)
        ]
        with override_settings(STILLOPEN_MAX_APPLICATIONS=3):
            run = scan.start_run(self.u, background=False)
        self.assertEqual(Application.objects.filter(owner=self.u).count(), 3)
        self.assertEqual(run.added, 3)
        self.assertIn("tracker limit", run.error)

    @mock.patch("tracker.services.scan.fetch_greenhouse")
    def test_second_scan_reuses_the_running_run_instead_of_starting_another(self, fetch):
        fetch.return_value = []
        run1 = ScanRun.objects.create(owner=self.u, total=1)  # still "running"
        run2 = scan.start_run(self.u, background=False)
        self.assertEqual(run1.pk, run2.pk)


class ScanViewTests(TestCase):
    """Background completion is exercised directly against the service (ScanRunTests, background=False) --
    same split as LivenessTests/tests_multiuser.py use for liveness_start. These views are tested for auth,
    isolation, throttling and response shape only, never by waiting on a daemon thread's real network call."""

    def setUp(self):
        cache.clear()
        self.u = user("zahid", target_roles="Senior Backend Engineer")
        self.client.force_login(self.u)

    def test_status_reads_a_completed_run_from_the_database(self):
        JobSource.objects.create(name="Acme", connector="greenhouse", board_token="acme", enabled=True)
        with mock.patch("tracker.services.scan.fetch_greenhouse") as fetch:
            fetch.return_value = [{"title": "Senior Backend Engineer", "url": "https://x.test/1", "location": ""}]
            scan.start_run(self.u, background=False)
        r = self.client.get(reverse("scan_status"))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertFalse(data["running"])
        self.assertEqual(data["added"], 1)
        self.assertEqual(len(data["entries"]), 1)
        self.assertEqual(data["entries"][0]["source"], "Acme")

    def test_status_with_no_run_yet(self):
        r = self.client.get(reverse("scan_status"))
        self.assertEqual(r.json(), {"running": False, "done": 0, "total": 0, "found": 0, "added": 0, "error": "", "entries": []})

    def test_scan_runs_are_per_person(self):
        other = user("other")
        ScanRun.objects.create(owner=other, total=9, done=4, running=True)
        data = self.client.get(reverse("scan_status")).json()
        self.assertEqual(data["total"], 0)  # the other person's run is not this one's

    @mock.patch("tracker.services.scan.start_run")
    def test_start_calls_the_service_and_returns_its_state(self, start_run):
        start_run.return_value = ScanRun(owner=self.u, running=False, done=0, total=0)
        r = self.client.post(reverse("scan_start"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"running": False, "done": 0, "total": 0})
        start_run.assert_called_once_with(self.u)

    @mock.patch("tracker.services.scan.start_run")
    def test_throttled_after_the_hourly_limit(self, start_run):
        start_run.return_value = ScanRun(owner=self.u, running=False, done=0, total=0)
        with override_settings(STILLOPEN_SCANS_PER_HOUR=1):
            r1 = self.client.post(reverse("scan_start"))
            r2 = self.client.post(reverse("scan_start"))
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 429)

    def test_anonymous_cannot_start_a_scan(self):
        self.client.logout()
        r = self.client.post(reverse("scan_start"))
        self.assertEqual(r.status_code, 302)  # redirected to login
