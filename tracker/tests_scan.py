"""Job-board scanning: connectors, matching, dedup, multi-user isolation, rate limiting."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from tracker.models import Application, JobSource, Posting, ScanLogEntry, ScanRun, Status, UserProfile
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
REMOTEOK_PAYLOAD = [
    {"legal": "API Terms of Service: ..."},  # RemoteOK's own first element, not a job
    {"id": "1", "position": "Backend Engineer", "url": "https://remoteok.com/remote-jobs/1", "location": "", "company": "Acme Corp"},
    {"id": "2", "position": "Marketing Manager", "url": "https://remoteok.com/remote-jobs/2", "location": "Worldwide", "company": "Beta Inc"},
]
WWR_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Acme Corp: Backend Engineer</title>
    <region>Anywhere in the World</region>
    <link>https://weworkremotely.com/remote-jobs/acme-backend-engineer</link>
  </item>
  <item>
    <title>No Colon Here Just A Title</title>
    <region>USA Only</region>
    <link>https://weworkremotely.com/remote-jobs/no-colon</link>
  </item>
</channel></rss>"""
HIMALAYAS_PAYLOAD = {
    "jobs": [
        {"title": "Backend Engineer", "applicationLink": "https://himalayas.app/jobs/1", "companyName": "Acme Corp", "locationRestrictions": ["Poland"]},
        {"title": "Marketing Manager", "applicationLink": "https://himalayas.app/jobs/2", "companyName": "Beta Inc", "locationRestrictions": []},
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

    @mock.patch("tracker.services.scan.safe_get")
    def test_remoteok_parses_jobs_and_skips_its_own_legal_notice(self, get):
        get.return_value = mock.Mock(status_code=200, json=lambda: REMOTEOK_PAYLOAD)
        out = scan.fetch_remoteok("all")
        self.assertEqual(len(out), 2)  # the legal-notice element is not a job and must not appear
        self.assertEqual(out[0], {"title": "Backend Engineer", "url": "https://remoteok.com/remote-jobs/1", "location": "Remote", "company": "Acme Corp"})
        self.assertEqual(out[1]["location"], "Worldwide")  # a real location is kept, not overridden to "Remote"

    @mock.patch("tracker.services.scan.safe_get")
    def test_remoteok_token_all_omits_the_tag_filter(self, get):
        get.return_value = mock.Mock(status_code=200, json=lambda: [])
        scan.fetch_remoteok("all")
        self.assertEqual(get.call_args[0][0], "https://remoteok.com/api")
        scan.fetch_remoteok("dev")
        self.assertEqual(get.call_args[0][0], "https://remoteok.com/api?tags=dev")

    @mock.patch("tracker.services.scan.safe_get")
    def test_weworkremotely_splits_company_from_role_in_the_title(self, get):
        get.return_value = mock.Mock(status_code=200, text=WWR_RSS)
        out = scan.fetch_weworkremotely("all")
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0], {
            "title": "Backend Engineer", "url": "https://weworkremotely.com/remote-jobs/acme-backend-engineer",
            "location": "Anywhere in the World", "company": "Acme Corp",
        })
        # No "Company: Role" split found -- the whole title is kept as the role, company left blank rather than guessed.
        self.assertEqual(out[1]["title"], "No Colon Here Just A Title")
        self.assertEqual(out[1]["company"], "")

    @mock.patch("tracker.services.scan.safe_get")
    def test_weworkremotely_token_all_uses_the_combined_feed(self, get):
        get.return_value = mock.Mock(status_code=200, text="<rss><channel></channel></rss>")
        scan.fetch_weworkremotely("all")
        self.assertEqual(get.call_args[0][0], "https://weworkremotely.com/remote-jobs.rss")
        scan.fetch_weworkremotely("remote-full-stack-programming-jobs")
        self.assertEqual(get.call_args[0][0], "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss")

    @mock.patch("tracker.services.scan.safe_get")
    def test_himalayas_parses_jobs(self, get):
        get.return_value = mock.Mock(status_code=200, json=lambda: HIMALAYAS_PAYLOAD)
        out = scan.fetch_himalayas("all")
        self.assertEqual(out[0], {"title": "Backend Engineer", "url": "https://himalayas.app/jobs/1", "location": "Poland", "company": "Acme Corp"})
        self.assertEqual(out[1]["location"], "Remote")  # no locationRestrictions -- defaults to Remote, not blank

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


class RepostDetectionTests(TestCase):
    """career-ops' own detect-reposts.mjs requires 2+ distinct URLs seen on 2+ distinct scan dates for the same
    title identity, so a same-day batch of genuinely concurrent openings is never mistaken for a repost. Same
    discipline here, and it's an observation surfaced to the user, never a verdict."""

    def setUp(self):
        self.source = JobSource.objects.create(name="Acme", connector="greenhouse", board_token="acme", enabled=True)

    def test_title_key_normalizes_case_and_whitespace(self):
        self.assertEqual(scan.title_key("  Senior   Backend  Engineer "), "senior backend engineer")
        self.assertEqual(scan.title_key("Senior Backend Engineer"), scan.title_key("SENIOR BACKEND ENGINEER"))

    def test_a_single_sighting_is_not_a_repost(self):
        p = scan.record_sighting(self.source, "Backend Engineer", "https://x.test/1", "Remote")
        self.assertIsNone(scan.repost_signal(p))

    def test_company_defaults_to_the_source_name_for_a_single_company_board(self):
        p = scan.record_sighting(self.source, "Backend Engineer", "https://x.test/1", "Remote")
        self.assertEqual(p.company, "Acme")

    def test_aggregator_source_keeps_two_different_real_employers_apart(self):
        # Two different real companies, same title, same aggregator source -- must never look like one repost.
        aggregator = JobSource.objects.create(name="RemoteOK", connector="remoteok", board_token="all", enabled=True)
        import datetime
        day1, day2 = datetime.date(2026, 1, 1), datetime.date(2026, 1, 15)
        p1 = scan.record_sighting(aggregator, "Backend Engineer", "https://remoteok.test/1", "", company="Acme Corp", seen_date=day1)
        p2 = scan.record_sighting(aggregator, "Backend Engineer", "https://remoteok.test/2", "", company="Beta Inc", seen_date=day2)
        self.assertNotEqual(p1.title_key, p2.title_key)
        self.assertIsNone(scan.repost_signal(p1))
        self.assertIsNone(scan.repost_signal(p2))

    def test_aggregator_source_still_flags_the_same_employer_reposting(self):
        aggregator = JobSource.objects.create(name="RemoteOK", connector="remoteok", board_token="all", enabled=True)
        import datetime
        day1, day2 = datetime.date(2026, 1, 1), datetime.date(2026, 1, 15)
        p1 = scan.record_sighting(aggregator, "Backend Engineer", "https://remoteok.test/1", "", company="Acme Corp", seen_date=day1)
        p2 = scan.record_sighting(aggregator, "Backend Engineer", "https://remoteok.test/2", "", company="Acme Corp", seen_date=day2)
        signal = scan.repost_signal(p2)
        self.assertIsNotNone(signal)
        self.assertEqual(signal["distinct_urls"], 2)

    def test_two_urls_seen_the_same_day_is_not_flagged(self):
        # Two genuinely concurrent openings (different reqs, same title) posted on the same day.
        import datetime
        today = datetime.date(2026, 1, 1)
        p1 = scan.record_sighting(self.source, "Backend Engineer", "https://x.test/1", "Remote", seen_date=today)
        p2 = scan.record_sighting(self.source, "Backend Engineer", "https://x.test/2", "Remote", seen_date=today)
        self.assertIsNone(scan.repost_signal(p1))
        self.assertIsNone(scan.repost_signal(p2))

    def test_two_urls_on_two_distinct_days_is_flagged(self):
        import datetime
        day1, day2 = datetime.date(2026, 1, 1), datetime.date(2026, 1, 15)
        p1 = scan.record_sighting(self.source, "Backend Engineer", "https://x.test/1", "Remote", seen_date=day1)
        # The old URL goes stale (its own last_seen_at stays at day1); a new req appears under a new URL later.
        p2 = scan.record_sighting(self.source, "Backend Engineer", "https://x.test/2", "Remote", seen_date=day2)
        signal = scan.repost_signal(p2)
        self.assertIsNotNone(signal)
        self.assertEqual(signal["distinct_urls"], 2)
        self.assertEqual(signal["distinct_dates"], 2)
        # Both sibling postings carry the same signal -- it's a property of the title+source, not one URL.
        self.assertEqual(scan.repost_signal(p1), signal)

    def test_different_sources_never_cross_contaminate_the_signal(self):
        other_source = JobSource.objects.create(name="Other", connector="lever", board_token="other", enabled=True)
        import datetime
        day1, day2 = datetime.date(2026, 1, 1), datetime.date(2026, 1, 15)
        scan.record_sighting(self.source, "Backend Engineer", "https://x.test/1", "", seen_date=day1)
        p = scan.record_sighting(other_source, "Backend Engineer", "https://y.test/1", "", seen_date=day2)
        self.assertIsNone(scan.repost_signal(p))  # same title text, different company -- not a sibling

    @mock.patch("tracker.services.scan.fetch_greenhouse")
    def test_a_sighting_is_recorded_even_when_nothing_matches_the_users_roles(self, fetch):
        user = User.objects.create_user("zahid2", password=PW)
        fetch.return_value = [{"title": "Marketing Manager", "url": "https://x.test/1", "location": ""}]
        scan.start_run(user, background=False)
        self.assertEqual(Application.objects.filter(owner=user).count(), 0)  # no role matched it
        self.assertTrue(Posting.objects.filter(source=self.source, url="https://x.test/1").exists())  # still recorded

    @mock.patch("tracker.services.scan.fetch_greenhouse")
    def test_matched_application_is_linked_to_its_posting(self, fetch):
        user = User.objects.create_user("zahid3", password=PW)
        UserProfile.objects.filter(user=user).update(target_roles="Backend Engineer")
        fetch.return_value = [{"title": "Backend Engineer", "url": "https://x.test/1", "location": ""}]
        scan.start_run(user, background=False)
        app = Application.objects.get(owner=user)
        self.assertIsNotNone(app.posting_id)
        self.assertEqual(app.posting.url, "https://x.test/1")

    @mock.patch("tracker.services.scan.fetch_greenhouse")
    def test_dashboard_shows_the_repost_badge(self, fetch):
        import datetime
        user = User.objects.create_user("zahid4", password=PW)
        UserProfile.objects.filter(user=user).update(target_roles="Backend Engineer")
        self.client.force_login(user)
        scan.record_sighting(self.source, "Backend Engineer", "https://x.test/old", "", seen_date=datetime.date(2026, 1, 1))
        fetch.return_value = [{"title": "Backend Engineer", "url": "https://x.test/new", "location": ""}]
        with mock.patch("django.utils.timezone.localdate", return_value=datetime.date(2026, 1, 15)):
            scan.start_run(user, background=False)
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "Possible repost")
