"""People's own company job boards: validation, SSRF-shaped inputs, limits, and strict isolation."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from tracker.forms import OwnSourceForm, board_token_from
from tracker.models import Application, JobSource, Posting, UserProfile
from tracker.services import scan
from tracker.services.netguard import FetchError

User = get_user_model()
PW = "correct-horse-battery-staple"
JOB = {"title": "Backend Engineer", "url": "https://boards.greenhouse.io/acme/1", "location": "Remote", "company": "Acme", "description": ""}


def user(name):
    u = User.objects.create_user(name, email=f"{name}@example.com", password=PW)
    UserProfile.objects.filter(user=u).update(target_roles="Backend Engineer")
    return u


class TokenParsing(TestCase):
    def test_known_careers_addresses(self):
        self.assertEqual(board_token_from("greenhouse", "https://boards.greenhouse.io/acme/jobs/123"), "acme")
        self.assertEqual(board_token_from("greenhouse", "https://job-boards.greenhouse.io/acme"), "acme")
        self.assertEqual(board_token_from("lever", "https://jobs.lever.co/acme"), "acme")
        self.assertEqual(board_token_from("ashby", "https://jobs.ashbyhq.com/acme"), "acme")
        self.assertEqual(board_token_from("smartrecruiters", "https://jobs.smartrecruiters.com/Acme"), "Acme")
        self.assertEqual(board_token_from("recruitee", "https://acme.recruitee.com/"), "acme")
        self.assertEqual(board_token_from("lever", "acme"), "acme")

    def test_foreign_or_mismatched_addresses_give_nothing(self):
        self.assertEqual(board_token_from("lever", "https://evil.example.com/acme"), "")
        self.assertEqual(board_token_from("lever", "https://boards.greenhouse.io/acme"), "")
        self.assertEqual(board_token_from("greenhouse", "http://169.254.169.254/latest"), "")
        self.assertEqual(board_token_from("recruitee", "https://recruitee.com/"), "")

    def form(self, **kw):
        data = {"connector": "greenhouse", "board_token": "acme", "name": ""}
        data.update(kw)
        return OwnSourceForm(data)

    def test_nasty_tokens_are_invalid(self):
        for bad in ["..", "../x", "a/b", "a b", "acme?x=1", "acme#", "-acme", "a" * 61, "evil.com", "", "%2e%2e", "http://x"]:
            self.assertFalse(self.form(board_token=bad).is_valid(), bad)

    def test_only_single_company_systems_are_offered(self):
        for aggregator in ("remoteok", "weworkremotely", "himalayas", "bogus"):
            self.assertFalse(self.form(connector=aggregator).is_valid(), aggregator)
        self.assertTrue(self.form().is_valid())

    def test_name_defaults_to_the_token(self):
        f = self.form(board_token="https://jobs.lever.co/acme", connector="lever")
        self.assertTrue(f.is_valid())
        self.assertEqual((f.cleaned_data["board_token"], f.cleaned_data["name"]), ("acme", "acme"))


@override_settings(STILLOPEN_SOURCE_ADDS_PER_HOUR=1000)
class AddingBoards(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = user("alice"), user("bob")
        self.client.login(username="alice", password=PW)

    def add(self, token="acme", connector="greenhouse", **kw):
        return self.client.post(reverse("sources"), {"connector": connector, "board_token": token, "name": kw.get("name", "")})

    def test_adds_a_working_board_as_mine(self):
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=[JOB]) as fetch:
            self.add(name="Acme Inc")
        fetch.assert_called_once_with("acme")
        s = JobSource.objects.get()
        self.assertEqual((s.owner, s.name, s.connector, s.board_token), (self.a, "Acme Inc", "greenhouse", "acme"))

    def test_a_board_that_does_not_answer_is_not_saved(self):
        with mock.patch("tracker.services.scan.fetch_greenhouse", side_effect=FetchError("HTTP 404")):
            r = self.add(token="nosuchco", connector="greenhouse")
        self.assertEqual(JobSource.objects.count(), 0)
        self.assertContains(self.client.get(reverse("sources")), "Add a company")
        self.assertEqual(r.status_code, 200)

    def test_no_fetch_at_all_for_invalid_input(self):
        with mock.patch("tracker.services.scan.fetch_greenhouse") as fetch, mock.patch("tracker.services.scan.safe_get") as get:
            self.add(token="../../etc")
            self.add(token="https://evil.example.com/x")
            self.add(token="x", connector="remoteok")
        fetch.assert_not_called()
        get.assert_not_called()
        self.assertEqual(JobSource.objects.count(), 0)

    def test_the_fetch_url_is_built_by_the_app_on_the_fixed_host(self):
        with mock.patch("tracker.services.scan.safe_get") as get:
            get.return_value.status_code = 200
            get.return_value.json.return_value = {"jobs": []}
            self.add(token="https://boards.greenhouse.io/acme/jobs/9?gh_src=x#top")
        (url,), _ = get.call_args
        self.assertTrue(url.startswith("https://boards-api.greenhouse.io/"), url)
        self.assertIn("/acme/", url)

    def test_site_wide_board_is_not_duplicated(self):
        JobSource.objects.create(name="Acme", connector="greenhouse", board_token="acme")
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=[]) as fetch:
            self.add()
        fetch.assert_not_called()
        self.assertEqual(JobSource.objects.count(), 1)

    def test_two_people_may_each_add_the_same_company_and_never_see_each_other(self):
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=[]):
            self.add(name="Alice's Acme")
            self.client.logout()
            self.client.login(username="bob", password=PW)
            self.add(name="Bob's Acme")
        self.assertEqual(JobSource.objects.count(), 2)
        page = self.client.get(reverse("sources")).content.decode()
        self.assertIn("Bob&#x27;s Acme", page)
        self.assertNotIn("Alice", page)
        self.assertEqual(JobSource.objects.get(name="Bob's Acme").owner, self.b)

    @override_settings(STILLOPEN_MAX_OWN_SOURCES=2)
    def test_cap_per_person(self):
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=[]):
            for t in ("a1", "a2", "a3"):
                self.add(token=t)
        self.assertEqual(JobSource.objects.filter(owner=self.a).count(), 2)

    @override_settings(STILLOPEN_SOURCE_ADDS_PER_HOUR=2)
    def test_rate_limit_stops_a_scripted_prober(self):
        with mock.patch("tracker.services.scan.fetch_greenhouse", side_effect=FetchError("HTTP 404")) as fetch:
            for t in ("a1", "a2", "a3", "a4"):
                self.add(token=t)
        self.assertEqual(fetch.call_count, 2)

    def test_name_is_escaped_on_the_page(self):
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=[]):
            self.add(name="<script>alert(1)</script>")
        self.assertNotContains(self.client.get(reverse("sources")), "<script>alert(1)</script>")

    def test_login_required(self):
        self.client.logout()
        r = self.client.get(reverse("sources"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])


class Isolation(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = user("alice"), user("bob")
        self.shared = JobSource.objects.create(name="SharedCo", connector="lever", board_token="sharedco")
        self.mine = JobSource.objects.create(owner=self.a, name="AliceCo", connector="greenhouse", board_token="aliceco")
        self.posting = scan.record_sighting(self.mine, "Backend Engineer", "https://boards.greenhouse.io/aliceco/1", "Remote", company="AliceCo")

    def fetcher(self, calls):
        def fake(token):
            calls.append(token)
            return [JOB]
        return fake

    def test_a_scan_uses_the_site_boards_plus_only_my_own(self):
        a_calls, b_calls = [], []
        with mock.patch("tracker.services.scan.fetch_greenhouse", self.fetcher(a_calls)), mock.patch("tracker.services.scan.fetch_lever", self.fetcher(a_calls)):
            run = scan.start_run(self.a, background=False)
        self.assertEqual(sorted(a_calls), ["aliceco", "sharedco"])
        self.assertEqual(run.total, 2)
        with mock.patch("tracker.services.scan.fetch_greenhouse", self.fetcher(b_calls)), mock.patch("tracker.services.scan.fetch_lever", self.fetcher(b_calls)):
            run = scan.start_run(self.b, background=False)
        self.assertEqual(b_calls, ["sharedco"])
        self.assertEqual(run.total, 1)

    def test_paused_board_is_skipped(self):
        JobSource.objects.filter(pk=self.mine.pk).update(enabled=False)
        calls = []
        with mock.patch("tracker.services.scan.fetch_lever", self.fetcher(calls)), mock.patch("tracker.services.scan.fetch_greenhouse", self.fetcher(calls)):
            scan.start_run(self.a, background=False)
        self.assertEqual(calls, ["sharedco"])

    def test_nobody_else_can_toggle_delete_or_see_my_board(self):
        self.client.login(username="bob", password=PW)
        post = self.client.post
        self.assertEqual(post(reverse("source_action", args=[self.mine.pk, "delete"])).status_code, 404)
        self.assertEqual(post(reverse("source_action", args=[self.mine.pk, "toggle"])).status_code, 404)
        self.assertEqual(post(reverse("source_action", args=[self.shared.pk, "delete"])).status_code, 404)  # site-wide: admin only
        self.assertTrue(JobSource.objects.filter(pk=self.mine.pk, enabled=True).exists())
        self.assertNotContains(self.client.get(reverse("sources")), "AliceCo")
        self.assertContains(self.client.get(reverse("sources")), "SharedCo")

    def test_owner_can_pause_and_remove(self):
        self.client.login(username="alice", password=PW)
        self.client.post(reverse("source_action", args=[self.mine.pk, "toggle"]))
        self.mine.refresh_from_db()
        self.assertFalse(self.mine.enabled)
        self.client.post(reverse("source_action", args=[self.mine.pk, "delete"]))
        self.assertFalse(JobSource.objects.filter(pk=self.mine.pk).exists())
        self.assertEqual(Posting.objects.count(), 0)

    def test_get_and_unknown_actions(self):
        self.client.login(username="alice", password=PW)
        self.assertEqual(self.client.get(reverse("source_action", args=[self.mine.pk, "delete"])).status_code, 405)
        self.assertEqual(self.client.post(reverse("source_action", args=[self.mine.pk, "explode"])).status_code, 404)

    def test_all_postings_hides_other_peoples_private_boards(self):
        self.client.login(username="bob", password=PW)
        self.assertNotContains(self.client.get(reverse("all_postings")), "AliceCo")
        self.assertEqual(self.client.post(reverse("add_posting", args=[self.posting.pk])).status_code, 404)
        self.assertEqual(Application.objects.filter(owner=self.b).count(), 0)
        self.client.login(username="alice", password=PW)
        self.assertContains(self.client.get(reverse("all_postings")), "AliceCo")
        self.assertEqual(self.client.post(reverse("add_posting", args=[self.posting.pk])).status_code, 302)

    def test_filtering_all_postings_by_someone_elses_source_shows_nothing(self):
        self.client.login(username="bob", password=PW)
        page = self.client.get(reverse("all_postings"), {"source": self.mine.pk})
        self.assertNotContains(page, "Backend Engineer")

    def test_dashboard_offers_search_when_only_my_own_board_exists(self):
        JobSource.objects.filter(owner__isnull=True).delete()
        UserProfile.objects.filter(user__in=[self.a, self.b]).update(onboarding_done=True)
        self.client.login(username="alice", password=PW)
        self.assertContains(self.client.get(reverse("dashboard")), 'id="btn-scan"')
        self.client.login(username="bob", password=PW)
        self.assertNotContains(self.client.get(reverse("dashboard")), 'id="btn-scan"')
