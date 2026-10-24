"""The search engine a candidate relies on without any AI: out-of-the-box sources, smarter matching, location
relevance, free scoring, shared caching, automatic searching, and the new free connectors."""
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tracker import seed
from tracker.models import Application, JobSource, ScanRun, SearchArea, SiteConfig, UserProfile
from tracker.seed_sources import COMPANIES, DEFAULT_SOURCES, FEEDS
from tracker.services import fit, scan
from tracker.services.netguard import FetchError

User = get_user_model()
PW = "correct-horse-battery-staple"
CV = "Backend engineer. C#, SQL Server, REST APIs, Docker, Kubernetes, payment systems."


def person(name="rina", roles="Backend Engineer", cv=CV, **extra):
    u = User.objects.create_user(name, email=f"{name}@example.com", password=PW)
    UserProfile.objects.filter(user=u).update(target_roles=roles, profile_cv=cv, onboarding_done=True, **extra)
    return u


def job(title="Backend Engineer", url="https://x.test/1", location="Remote", company="Acme", description="Build REST APIs in C# on SQL Server with Docker."):
    return {"title": title, "url": url, "location": location, "company": company, "description": description}


class TitleMatching(TestCase):
    def test_words_in_any_order_and_synonyms(self):
        roles = ["backend engineer"]
        for title in ["Backend Engineer", "Senior Software Engineer, Back-end", "Backend Developer", "Back End Developer (Remote)", "Staff Backend Engineer"]:
            self.assertTrue(scan._matches(title, roles), title)

    def test_unrelated_titles_do_not_match(self):
        roles = ["backend engineer"]
        for title in ["Marketing Manager", "Frontend Engineer", "Backend Account Executive", "Data Scientist", ""]:
            self.assertFalse(scan._matches(title, roles), title)

    def test_seniority_words_in_the_role_do_not_block_a_match(self):
        self.assertTrue(scan._matches("Backend Engineer II", ["senior backend engineer"]))

    def test_phrase_still_matches(self):
        self.assertTrue(scan._matches("Solutions Architect, Payments", ["solutions architect"]))

    def test_no_roles_matches_nothing(self):
        self.assertFalse(scan._matches("Backend Engineer", []))


class EngineRuns(TestCase):
    def setUp(self):
        cache.clear()
        self.u = person()
        self.src = JobSource.objects.create(name="Acme", connector="greenhouse", board_token="acme")

    def run_scan(self, postings, user=None, **settings_kw):
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=postings), override_settings(**settings_kw):
            return scan.start_run(user or self.u, background=False)

    def test_new_jobs_keep_their_description_and_get_a_free_score(self):
        self.run_scan([job()])
        app = Application.objects.get(owner=self.u)
        self.assertIn("REST APIs", app.description)
        self.assertIsNotNone(app.score)
        self.assertEqual(app.ai_method, "keywords")
        self.assertEqual(app.status.name, "Evaluated")  # fit already checked: nothing to press

    def test_location_is_read_from_the_feed_not_only_the_description(self):
        self.run_scan([job(location="Berlin, Germany", description="Backend role.")])
        app = Application.objects.get(owner=self.u)
        self.assertEqual(app.country, "DE")

    def test_clear_location_mismatch_is_left_out_but_still_recorded_publicly(self):
        SearchArea.objects.create(owner=self.u, place="Bangladesh", allow_onsite=True, allow_hybrid=True)
        UserProfile.objects.filter(user=self.u).update(home_country="BD")
        run = self.run_scan([job(location="Berlin, Germany", description="On-site in Berlin."), job(title="Backend Engineer II", url="https://x.test/2", location="Dhaka, Bangladesh", description="On-site in Dhaka.")])
        self.assertEqual(Application.objects.filter(owner=self.u).count(), 1)
        self.assertEqual(Application.objects.get(owner=self.u).country, "BD")
        entry = run.entries.get()
        self.assertEqual((entry.matched, entry.outside, entry.added), (2, 1, 1))
        from tracker.models import Posting
        self.assertEqual(Posting.objects.count(), 2)

    def test_unknown_location_is_never_excluded(self):
        SearchArea.objects.create(owner=self.u, place="Bangladesh", allow_onsite=True)
        self.run_scan([job(location="", description="Backend role, details to follow.")])
        self.assertEqual(Application.objects.filter(owner=self.u).count(), 1)

    def test_worldwide_remote_fits_a_remote_search_anywhere(self):
        SearchArea.objects.create(owner=self.u, place="Anywhere", allow_remote=True)
        self.run_scan([job(location="Worldwide", description="Fully remote, work from anywhere.")])
        self.assertEqual(Application.objects.filter(owner=self.u).count(), 1)

    def test_same_job_on_two_sources_is_added_once(self):
        JobSource.objects.create(name="Remotive", connector="remotive", board_token="all")
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=[job(url="https://a.test/1")]), \
                mock.patch("tracker.services.scan.fetch_remotive", return_value=[job(url="https://b.test/1")]):
            run = scan.start_run(self.u, background=False)
        self.assertEqual(Application.objects.filter(owner=self.u).count(), 1)
        self.assertEqual(run.added, 1)

    def test_cap_keeps_the_best_matches_first(self):
        weak = job(title="Backend Engineer", url="https://x.test/weak", description="Our office has a kitchen and a view.")
        strong = job(title="Backend Engineer", url="https://x.test/strong", company="Strongco", description="C# SQL Server REST APIs Docker Kubernetes payment systems.")
        run = self.run_scan([weak, strong], STILLOPEN_SCAN_MAX_NEW=1)
        self.assertEqual(Application.objects.get(owner=self.u).url, "https://x.test/strong")
        self.assertIn("best new matches", run.error)

    def test_role_matches_outrank_skill_only_matches(self):
        titled = job(title="Backend Engineer", url="https://x.test/t", company="T", description="Kitchen.")
        skills = job(title="Platform Developer", url="https://x.test/s", company="S", description="C# SQL Server REST APIs Docker Kubernetes payment systems.")
        self.run_scan([skills, titled], STILLOPEN_SCAN_MAX_NEW=1, STILLOPEN_SKILL_MATCH_MIN_OVERLAP=3)
        self.assertEqual(Application.objects.get(owner=self.u).url, "https://x.test/t")

    def test_one_broken_source_does_not_stop_the_others(self):
        JobSource.objects.create(name="Lever Co", connector="lever", board_token="levco")
        with mock.patch("tracker.services.scan.fetch_greenhouse", side_effect=FetchError("HTTP 500")), \
                mock.patch("tracker.services.scan.fetch_lever", return_value=[job(url="https://l.test/1")]):
            run = scan.start_run(self.u, background=False)
        self.assertEqual(run.added, 1)
        self.assertEqual(run.entries.get(source_name="Acme").error, "HTTP 500")

    @override_settings(STILLOPEN_SCAN_CACHE_SECONDS=600)
    def test_sources_are_read_once_for_everyone_searching(self):
        other = person("sam")
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=[job()]) as fetch:
            scan.start_run(self.u, background=False)
            scan.start_run(other, background=False)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(Application.objects.filter(owner=other).count(), 1)

    def test_second_persons_search_makes_no_duplicate_sighting_writes(self):
        from tracker.models import Posting, PostingSighting
        other = person("sam")
        self.run_scan([job()])
        self.run_scan([job()], user=other)
        self.assertEqual(Posting.objects.count(), 1)
        self.assertEqual(PostingSighting.objects.count(), 1)

    def test_old_sightings_are_pruned(self):
        from tracker.models import Posting, PostingSighting
        self.run_scan([job()])
        posting = Posting.objects.get()
        PostingSighting.objects.create(posting=posting, seen_date=timezone.localdate() - timedelta(days=400))
        self.run_scan([job(url="https://x.test/other")])
        self.assertFalse(PostingSighting.objects.filter(seen_date__lt=timezone.localdate() - timedelta(days=180)).exists())

    def test_a_candidate_with_no_cv_still_gets_title_matches(self):
        bare = person("bare", cv="")
        self.run_scan([job()], user=bare)
        app = Application.objects.get(owner=bare)
        self.assertIsNone(app.score)

    def test_nothing_is_ever_sent_to_an_ai(self):
        UserProfile.objects.filter(user=self.u).update(ai_provider="openai")
        with mock.patch("tracker.services.ai._openai") as paid:
            self.run_scan([job()])
        paid.assert_not_called()


class ClearlyOutside(TestCase):
    def setUp(self):
        self.u = person()
        self.area = SearchArea.objects.create(owner=self.u, place="Malaysia", allow_onsite=True)

    def test_only_when_every_area_says_no(self):
        berlin = Application(owner=self.u, company="x", role="y", country="DE", arrangement="onsite", location_text="Berlin")
        kl = Application(owner=self.u, company="x", role="y", country="MY", arrangement="onsite", location_text="Kuala Lumpur")
        self.assertTrue(fit.clearly_outside(berlin, [self.area]))
        self.assertFalse(fit.clearly_outside(kl, [self.area]))

    def test_unknown_and_no_areas_are_never_excluded(self):
        blank = Application(owner=self.u, company="x", role="y")
        self.assertFalse(fit.clearly_outside(blank, [self.area]))
        self.assertFalse(fit.clearly_outside(Application(owner=self.u, company="x", role="y", country="DE"), []))


@override_settings(STILLOPEN_AUTO_SCAN=True)
class AutoSearch(TestCase):
    def setUp(self):
        cache.clear()
        self.u = person()
        JobSource.objects.create(name="Acme", connector="greenhouse", board_token="acme")
        self.client.login(username="rina", password=PW)

    def start(self):
        with mock.patch("tracker.services.scan.start_run") as start:
            self.client.get(reverse("dashboard"))
        return start

    def test_opening_the_dashboard_starts_a_search_for_a_new_candidate(self):
        self.assertEqual(self.start().call_count, 1)

    def test_not_again_within_the_interval_even_if_it_found_nothing(self):
        ScanRun.objects.create(owner=self.u, running=False)
        self.assertEqual(self.start().call_count, 0)

    def test_again_once_the_interval_has_passed(self):
        run = ScanRun.objects.create(owner=self.u, running=False)
        ScanRun.objects.filter(pk=run.pk).update(started_at=timezone.now() - timedelta(hours=13))
        self.assertEqual(self.start().call_count, 1)

    def test_not_while_one_is_running(self):
        ScanRun.objects.create(owner=self.u, running=True)
        self.assertEqual(self.start().call_count, 0)

    def test_off_when_hours_is_zero(self):
        SiteConfig.objects.filter(pk=1).update(auto_scan_hours=0)
        self.assertEqual(self.start().call_count, 0)

    def test_needs_to_know_what_the_person_wants(self):
        UserProfile.objects.filter(user=self.u).update(target_roles="", profile_cv="")
        self.assertEqual(self.start().call_count, 0)

    def test_needs_at_least_one_source(self):
        JobSource.objects.all().delete()
        self.assertEqual(self.start().call_count, 0)

    def test_each_person_has_their_own_clock(self):
        other = person("sam")
        ScanRun.objects.create(owner=other, running=False)
        self.assertEqual(self.start().call_count, 1)

    def test_the_search_really_runs_end_to_end(self):
        real = scan.start_run
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=[job()]),                 mock.patch("tracker.services.scan.start_run", side_effect=lambda owner: real(owner, background=False)):
            run = scan.maybe_auto_start(self.u)
        self.assertEqual(run.added, 1)
        self.assertEqual(Application.objects.filter(owner=self.u).count(), 1)


class SeededSources(TestCase):
    def test_every_default_is_well_formed_and_unique(self):
        keys = [(c, t) for _, c, t in DEFAULT_SOURCES]
        self.assertEqual(len(keys), len(set(keys)))
        valid = dict(JobSource.CONNECTORS)
        for name, connector, token in DEFAULT_SOURCES:
            self.assertIn(connector, valid)
            self.assertTrue(name.strip())
            self.assertRegex(token, r"^[A-Za-z0-9._-]+$")
        self.assertGreaterEqual(len(FEEDS), 8)
        self.assertGreaterEqual(len(COMPANIES), 80)

    def test_seeding_adds_all_and_is_idempotent_and_leaves_changes_alone(self):
        self.assertEqual(JobSource.objects.count(), 0)  # tests do not get the migration's seed
        first = seed.ensure_default_sources(JobSource)
        self.assertEqual(first, len(DEFAULT_SOURCES))
        JobSource.objects.filter(connector="remotive").update(name="Mine", enabled=False)
        self.assertEqual(seed.ensure_default_sources(JobSource), 0)
        s = JobSource.objects.get(connector="remotive")
        self.assertEqual((s.name, s.enabled), ("Mine", False))
        self.assertTrue(all(x.owner is None for x in JobSource.objects.all()))

    def test_command_reports_and_adds(self):
        from io import StringIO
        out = StringIO()
        call_command("seed_sources", stdout=out)
        self.assertIn(f"Added {len(DEFAULT_SOURCES)}", out.getvalue())

    def test_fresh_candidate_with_seeded_sources_can_search(self):
        seed.ensure_default_sources(JobSource)
        u = person()
        self.client.login(username="rina", password=PW)
        self.assertContains(self.client.get(reverse("dashboard")), 'id="btn-scan"')
        self.assertEqual(JobSource.for_user(u, enabled=True).count(), len(DEFAULT_SOURCES))


class NewConnectors(TestCase):
    def resp(self, payload, status=200):
        r = mock.Mock(status_code=status)
        r.json.return_value = payload
        return r

    @mock.patch("tracker.services.scan.safe_get")
    def test_remotive(self, get):
        get.return_value = self.resp({"jobs": [{"title": "Go Dev", "url": "https://remotive.com/1", "company_name": "Acme", "candidate_required_location": "Worldwide", "description": "<p>Build things</p>"}]})
        j = scan.fetch_remotive("all")[0]
        self.assertEqual((j["title"], j["company"], j["location"]), ("Go Dev", "Acme", "Worldwide"))
        self.assertIn("Build things", j["description"])

    @mock.patch("tracker.services.scan.safe_get")
    def test_arbeitnow_unescapes_and_marks_remote(self, get):
        get.return_value = self.resp({"data": [{"title": "Dev", "url": "https://an.test/1", "company_name": "Jet", "location": "Berlin", "remote": True, "description": "&lt;p&gt;Hello team&lt;/p&gt;"}]})
        j = scan.fetch_arbeitnow("all")[0]
        self.assertEqual(j["location"], "Berlin (remote)")
        self.assertIn("Hello team", j["description"])
        self.assertNotIn("<p>", j["description"])

    @mock.patch("tracker.services.scan.safe_get")
    def test_jobicy(self, get):
        get.return_value = self.resp({"jobs": [{"jobTitle": "PM", "url": "https://j.test/1", "companyName": "Eleven", "jobGeo": "USA", "jobDescription": "<b>Lead</b>"}]})
        j = scan.fetch_jobicy("all")[0]
        self.assertEqual((j["title"], j["company"], j["location"]), ("PM", "Eleven", "Remote (USA)"))

    @mock.patch("tracker.services.scan.safe_get")
    def test_workingnomads(self, get):
        get.return_value = self.resp([{"title": "Angular Dev", "url": "https://wn.test/1", "company_name": "Lemon", "location": "Europe", "description": "<p>x</p>"}])
        self.assertEqual(scan.fetch_workingnomads("all")[0]["company"], "Lemon")

    @mock.patch("tracker.services.scan.safe_get")
    def test_themuse_reads_pages_up_to_the_limit(self, get):
        page = lambda n: self.resp({"page_count": 50, "results": [{"name": f"Role {n}", "refs": {"landing_page": f"https://m.test/{n}"}, "company": {"name": "Celonis"}, "locations": [{"name": "Madrid, Spain"}], "contents": "<p>c</p>"}]})
        get.side_effect = [page(i) for i in range(1, 6)]
        out = scan.fetch_themuse("all")
        self.assertEqual(len(out), 5)
        self.assertEqual(get.call_count, 5)
        self.assertEqual(out[0]["location"], "Madrid, Spain")

    @mock.patch("tracker.services.scan.safe_get")
    def test_http_errors_raise_for_every_new_connector(self, get):
        get.return_value = self.resp({}, status=503)
        for fetcher in (scan.fetch_remotive, scan.fetch_arbeitnow, scan.fetch_jobicy, scan.fetch_workingnomads, scan.fetch_themuse):
            with self.assertRaises(FetchError):
                fetcher("all")

    def test_connectors_are_wired_into_the_dispatcher_and_the_model(self):
        for name in ("remotive", "arbeitnow", "jobicy", "workingnomads", "themuse"):
            self.assertIn(name, dict(JobSource.CONNECTORS))
            self.assertTrue(callable(globals().get("scan") and getattr(scan, f"fetch_{name}")))
        self.assertNotIn("remotive", JobSource.OWN_CONNECTORS)  # aggregators stay site-wide


class DuplicateRules(TestCase):
    def setUp(self):
        cache.clear()
        self.u = person()
        self.a = JobSource.objects.create(name="Agoda", connector="greenhouse", board_token="agoda")

    def test_same_role_in_several_cities_on_one_source_is_kept(self):
        rows = [job(url=f"https://x.test/{c}", location=c, company="Agoda") for c in ("Bangkok", "Gurugram", "Singapore")]
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=rows):
            scan.start_run(self.u, background=False)
        self.assertEqual(Application.objects.filter(owner=self.u).count(), 3)

    def test_a_job_added_by_hand_is_not_added_again_by_a_search(self):
        Application.objects.create(owner=self.u, company="Acme", role="Backend Engineer", status=__import__("tracker.models", fromlist=["Status"]).Status.objects.first())
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=[job(url="https://other.test/9")]):
            run = scan.start_run(self.u, background=False)
        self.assertEqual(run.added, 0)
        self.assertEqual(run.entries.get().duplicates, 1)

    def test_the_cap_ranks_across_every_source_not_just_the_first(self):
        JobSource.objects.create(name="Zed", connector="lever", board_token="zed")
        first = [job(url=f"https://a.test/{i}", company="Agoda", title="Backend Engineer", description="Kitchen and a view.") for i in range(3)]
        best = [job(url="https://z.test/1", company="Zed", title="Backend Engineer", description="C# SQL Server REST APIs Docker Kubernetes payment systems.")]
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=first), \
                mock.patch("tracker.services.scan.fetch_lever", return_value=best), override_settings(STILLOPEN_SCAN_MAX_NEW=1):
            run = scan.start_run(self.u, background=False)
        self.assertEqual(Application.objects.get(owner=self.u).company, "Zed")
        self.assertEqual(run.entries.get(source_name="Zed").added, 1)
        self.assertEqual(run.entries.get(source_name="Agoda").added, 0)
        self.assertEqual(run.done, 2)  # every source was still read


class SlowSources(TestCase):
    def test_one_slow_source_is_skipped_not_waited_for(self):
        import threading
        release = threading.Event()
        JobSource.objects.create(name="Fast", connector="greenhouse", board_token="fast")
        JobSource.objects.create(name="Slow", connector="lever", board_token="slow")

        def slow(token):
            release.wait(10)  # a host that takes forever
            return []

        u = person()
        try:
            with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=[job()]), \
                    mock.patch("tracker.services.scan.fetch_lever", side_effect=slow), \
                    override_settings(STILLOPEN_SCAN_DEADLINE_SECONDS=1):
                run = scan.start_run(u, background=False)
        finally:
            release.set()
        self.assertEqual(run.added, 1)  # the fast one still delivered
        self.assertIn("Took too long", run.entries.get(source_name="Slow").error)
        self.assertEqual(run.done, 2)


class BulkSightingsAndRanking(TestCase):
    def setUp(self):
        cache.clear()
        self.u = person()
        self.src = JobSource.objects.create(name="Acme", connector="greenhouse", board_token="acme")

    def test_bulk_recording_matches_the_one_at_a_time_result(self):
        from tracker.models import Posting, PostingSighting
        rows = [job(url=f"https://x.test/{i}", title=f"Role {i}", company="Acme") for i in range(3)] + [job(url="https://x.test/0", title="Role 0 renamed", company="Acme")]
        scan.record_sightings(self.src, rows)
        self.assertEqual(Posting.objects.count(), 3)
        self.assertEqual(PostingSighting.objects.count(), 3)
        scan.record_sightings(self.src, [job(url="https://x.test/1", title="Role 1 renamed", location="Dhaka")])
        p = Posting.objects.get(url="https://x.test/1")
        self.assertEqual((p.title, p.location), ("Role 1 renamed", "Dhaka"))
        self.assertEqual(PostingSighting.objects.count(), 3)  # same day: no second sighting
        self.assertEqual(p.title_key, scan.title_key("Acme :: Role 1 renamed"))

    def test_first_seen_survives_a_refresh(self):
        from tracker.models import Posting
        scan.record_sightings(self.src, [job(url="https://x.test/1")])
        first = Posting.objects.get().first_seen_at
        scan.record_sightings(self.src, [job(url="https://x.test/1", title="Backend Engineer II")])
        self.assertEqual(Posting.objects.get().first_seen_at, first)

    def test_clear_fits_outrank_unknown_ones_under_the_cap(self):
        SearchArea.objects.create(owner=self.u, place="Malaysia", allow_onsite=True)
        unknown = job(url="https://x.test/u", company="Unknownco", location="", description="Backend work. C# SQL Server REST APIs Docker Kubernetes payment systems.")
        clear = job(url="https://x.test/c", company="Clearco", location="Kuala Lumpur, Malaysia", description="On-site in Kuala Lumpur. Kitchen and a view.")
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=[unknown, clear]), override_settings(STILLOPEN_SCAN_MAX_NEW=1):
            scan.start_run(self.u, background=False)
        self.assertEqual(Application.objects.get(owner=self.u).company, "Clearco")
