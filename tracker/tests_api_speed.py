"""The dashboard's cost, how API answers travel (compressed, revalidated), and the saved layout preferences."""
import gzip
import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from tracker.models import Application, Bucket, JobSource, Posting, PostingSighting, SearchArea, SiteConfig, Status, UserProfile
from tracker.services import preferences, scan

User = get_user_model()
PW = "correct-horse-battery-staple"
BASE = "/api/v1"


def person(name):
    return User.objects.create_user(name, email=f"{name}@example.com", password=PW)


def jobs_with_reposts(owner, n, source, start=0):
    """`n` jobs, each from a posting that was listed twice on two different days (the repost pattern), so each card needs the lookup."""
    status = Status.objects.get(name="Evaluated")
    today = timezone.localdate()
    for i in range(start, start + n):
        key = f"engineer-{i}"
        first = Posting.objects.create(source=source, url=f"https://x.example/{i}/a", title=f"Engineer {i}", company="Acme", title_key=key)
        second = Posting.objects.create(source=source, url=f"https://x.example/{i}/b", title=f"Engineer {i}", company="Acme", title_key=key)
        PostingSighting.objects.create(posting=first, seen_date=today - timedelta(days=3))
        PostingSighting.objects.create(posting=second, seen_date=today)
        Application.objects.create(owner=owner, company="Acme", role=f"Engineer {i}", status=status, posting=first, score=3.0)


def make_source():
    return JobSource.objects.create(name="Acme", connector="greenhouse", board_token="acme", enabled=True)


class DashboardCost(TestCase):
    def setUp(self):
        cache.clear()
        self.a = person("alice")
        self.source = make_source()
        self.client.force_login(self.a)

    def count(self):
        with CaptureQueriesContext(connection) as ctx, mock.patch("tracker.services.scan.maybe_auto_start"):  # no background search in a cost test
            r = self.client.get(f"{BASE}/dashboard")
        self.assertEqual(r.status_code, 200)
        return len(ctx), r

    def test_the_number_of_queries_does_not_grow_with_the_number_of_jobs(self):
        jobs_with_reposts(self.a, 3, self.source)
        few, _ = self.count()
        jobs_with_reposts(self.a, 40, self.source, start=3)
        many, response = self.count()
        self.assertLessEqual(many, few + 4, f"{few} queries for 3 jobs but {many} for 43")
        self.assertEqual(len(response.json()["jobs"]), 43)

    def test_the_batch_finds_the_same_reposts_as_looking_one_up_at_a_time(self):
        jobs_with_reposts(self.a, 5, self.source)
        lone = Posting.objects.create(source=self.source, url="https://x.example/lone", title="Lone", company="Acme", title_key="lone")
        PostingSighting.objects.create(posting=lone, seen_date=timezone.localdate())
        postings = list(Posting.objects.all())
        batch = scan.repost_signals(postings)
        for p in postings:
            self.assertEqual(batch[p.pk], scan.repost_signal(p), p.url)
        self.assertIsNone(batch[lone.pk])
        first = Posting.objects.filter(title_key="engineer-0").first()
        self.assertEqual(batch[first.pk]["distinct_urls"], 2)
        self.assertEqual(batch[first.pk]["distinct_dates"], 2)

    def test_expired_postings_go_to_the_closed_stage_without_a_query_each(self):
        SiteConfig.objects.update(auto_close_expired=True)
        status = Status.objects.get(name="Evaluated")
        for i in range(10):
            Application.objects.create(owner=self.a, company="Old", role=f"R{i}", status=status, live_state="expired")
        _, r = self.count()
        closed = Bucket.objects.filter(is_closed=True).first().key
        self.assertEqual({j["bucket_key"] for j in r.json()["jobs"]}, {closed})


class HowAnswersTravel(TestCase):
    def setUp(self):
        patch = mock.patch("tracker.services.scan.maybe_auto_start")  # the dashboard may start a background search; not in these tests
        patch.start()
        self.addCleanup(patch.stop)
        cache.clear()
        self.a = person("alice")
        self.client.force_login(self.a)

    def test_api_answers_are_compressed_when_the_browser_accepts_it(self):
        jobs_with_reposts(self.a, 20, make_source())
        plain = self.client.get(f"{BASE}/dashboard")
        packed = self.client.get(f"{BASE}/dashboard", HTTP_ACCEPT_ENCODING="gzip")
        self.assertEqual(packed["Content-Encoding"], "gzip")
        self.assertEqual(json.loads(gzip.decompress(packed.content)), plain.json())
        self.assertLess(len(packed.content), len(plain.content) / 3)

    def test_pages_are_never_compressed(self):
        for path in ("/", "/accounts/login/", "/privacy/"):
            r = self.client.get(path, HTTP_ACCEPT_ENCODING="gzip")
            self.assertNotIn("Content-Encoding", r, path)  # HTML with a CSRF token next to reflected text is the BREACH setup

    def test_an_unchanged_answer_is_a_304_and_a_changed_one_is_not(self):
        first = self.client.get(f"{BASE}/me")
        tag = first["ETag"]
        self.assertTrue(tag)
        self.assertIn("no-cache", first["Cache-Control"])
        self.assertIn("private", first["Cache-Control"])
        again = self.client.get(f"{BASE}/me", HTTP_IF_NONE_MATCH=tag)
        self.assertEqual(again.status_code, 304)
        self.assertEqual(again.content, b"")
        User.objects.filter(pk=self.a.pk).update(first_name="Alicia")
        changed = self.client.get(f"{BASE}/me", HTTP_IF_NONE_MATCH=tag)
        self.assertEqual(changed.status_code, 200)
        self.assertNotEqual(changed["ETag"], tag)

    def test_only_get_answers_are_tagged(self):
        r = self.client.post(f"{BASE}/liveness", content_type="application/json")
        self.assertNotIn("ETag", r)

    def test_another_persons_tag_never_matches(self):
        bob = person("bob")
        mine = self.client.get(f"{BASE}/dashboard")["ETag"]
        self.client.force_login(bob)
        theirs = self.client.get(f"{BASE}/dashboard", HTTP_IF_NONE_MATCH=mine)
        self.assertEqual(theirs.status_code, 200)  # a 304 here would mean one person's tag answered for another's list


class SavedPreferences(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        self.client.force_login(self.a)

    def put(self, body):
        return self.client.put(f"{BASE}/preferences", data=json.dumps(body), content_type="application/json")

    def test_defaults_are_a_list_with_all_stages(self):
        data = self.client.get(f"{BASE}/preferences").json()
        self.assertEqual((data["view"], data["tab"], data["sort"], data["filters_open"]), ("list", "all", "best", False))
        self.assertEqual((data["sidebar"], data["theme"], data["text_size"], data["density"]), ("expanded", "light", "normal", "comfortable"))
        self.assertEqual(set(data["filters"]), {"fit", "match", "work", "country", "posting", "found"})
        self.assertEqual(set(data["filters"].values()), {""})

    def test_sending_a_few_keys_changes_only_those(self):
        self.put({"view": "board", "text_size": "large"})
        data = self.put({"filters_open": True}).json()
        self.assertEqual((data["view"], data["text_size"], data["filters_open"], data["theme"]), ("board", "large", True, "light"))
        self.assertEqual(self.client.get(f"{BASE}/preferences").json(), data)

    def test_filters_are_replaced_as_a_whole(self):
        self.put({"filters": {"fit": "fits", "country": "MY"}})
        data = self.put({"filters": {"work": "remote"}}).json()
        self.assertEqual(data["filters"], {"fit": "", "match": "", "work": "remote", "country": "", "posting": "", "found": ""})

    def test_they_are_kept_per_person_and_come_with_me(self):
        self.put({"theme": "dark", "view": "board"})
        self.assertEqual(self.client.get(f"{BASE}/me").json()["preferences"]["theme"], "dark")
        self.client.force_login(self.b)
        self.assertEqual(self.client.get(f"{BASE}/preferences").json()["theme"], "light")
        self.assertEqual(self.client.get(f"{BASE}/me").json()["preferences"]["view"], "list")
        self.assertEqual(UserProfile.objects.get(user=self.a).ui_preferences["theme"], "dark")

    def test_every_bad_value_is_refused_with_a_plain_message_and_nothing_is_saved(self):
        bad = (
            {"view": "grid"}, {"sort": "random"}, {"theme": "blue"}, {"text_size": "huge"}, {"density": "tiny"}, {"sidebar": "hidden"},
            {"filters_open": "yes"}, {"filters": {"nope": "x"}}, {"filters": {"fit": "x" * 61}}, {"filters": ["a"]}, {"tab": "no-such-stage"}, {"colour": "red"},
        )
        for body in bad:
            r = self.put(body)
            self.assertEqual(r.status_code, 400, body)
            self.assertTrue(r.json()["fields"], body)
        self.assertEqual(UserProfile.for_user(self.a).ui_preferences, {})

    def test_a_real_stage_is_accepted_and_a_removed_one_falls_back_to_all(self):
        key = Bucket.objects.exclude(is_closed=True).first().key
        self.assertEqual(self.put({"tab": key}).json()["tab"], key)
        Bucket.objects.filter(key=key).update(key="renamed")
        self.assertEqual(self.client.get(f"{BASE}/preferences").json()["tab"], "all")

    def test_damaged_stored_data_never_breaks_a_page(self):
        UserProfile.objects.filter(user=self.a).update(ui_preferences={"view": 5, "filters": "x", "theme": ["dark"], "filters_open": "maybe", "extra": 1})
        data = self.client.get(f"{BASE}/me").json()["preferences"]
        self.assertEqual(data, preferences.normalize({}))

    def test_signed_out_is_refused(self):
        self.client.logout()
        self.assertEqual(self.client.get(f"{BASE}/preferences").status_code, 401)
        self.assertEqual(self.put({"view": "board"}).status_code, 401)


class YourSearchCard(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        self.client.force_login(self.a)

    def test_it_sums_up_what_drives_the_matches(self):
        UserProfile.objects.filter(user=self.a).update(
            target_roles="Backend Engineer\n\nPlatform Engineer", salary_floor="100,000 BDT/month", scan_digest_enabled=True, profile_cv="My CV",
        )
        SearchArea.objects.create(owner=self.a, place="Malaysia", city="Kuala Lumpur", allow_remote=True, allow_hybrid=True)
        SearchArea.objects.create(owner=self.b, place="Secretland", allow_onsite=True)
        card = self.client.get(f"{BASE}/dashboard").json()["search_summary"]
        self.assertEqual(card["roles"], ["Backend Engineer", "Platform Engineer"])
        self.assertEqual(card["places"], [{"place": "Malaysia, Kuala Lumpur", "mode": "remote, hybrid"}])
        self.assertNotIn("Secretland", json.dumps(card))
        self.assertEqual((card["salary_floor"], card["alerts_on"], card["has_cv"], card["ai"]), ("100,000 BDT/month", True, True, "keyword"))
        self.assertIn("remote", card)
        self.assertIn("alerts_available", card)

    def test_a_new_person_sees_what_is_missing(self):
        card = self.client.get(f"{BASE}/dashboard").json()["search_summary"]
        self.assertEqual((card["roles"], card["places"], card["has_cv"], card["alerts_on"]), ([], [], False, False))
