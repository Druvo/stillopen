"""The private calendar link: what it contains, that it never shows anyone else's dates, rotation, rate limits and the API behind the card."""
import json
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from tracker.models import CalendarFeed, Interview, Status
from tracker.services import ics
from tracker.tests_apply import job, person
from tracker.tests_cv import PW


def api(client, method, path):
    return getattr(client, method)(f"/api/v1{path}", content_type="application/json")


class FeedBase(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        today = timezone.localdate()
        self.app_a = job(self.a, company="Acme", role="Backend Engineer", follow_up_date=today + timedelta(days=2), deadline=today + timedelta(days=5),
                         notes="PRIVATE-NOTE-A", description="SECRET-DESCRIPTION-A")
        self.app_b = job(self.b, company="Hidden Co", role="Spy", follow_up_date=today + timedelta(days=2))
        Interview.objects.create(owner=self.a, application=self.app_a, scheduled_at=timezone.now() + timedelta(days=1), kind="video",
                                 where="https://meet.example.com/secret-room", notes="PRIVATE-INTERVIEW-NOTE")
        Interview.objects.create(owner=self.b, application=self.app_b, scheduled_at=timezone.now() + timedelta(days=1), kind="phone")

    def link(self, user):
        self.client.force_login(user)
        r = api(self.client, "post", "/calendar-link")
        self.assertEqual(r.status_code, 200)
        self.client.logout()
        return r.json()["url"].split("testserver")[1]


class FeedContentTests(FeedBase):
    def test_it_lists_my_dates_and_nothing_private(self):
        r = self.client.get(self.link(self.a))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["Content-Type"].startswith("text/calendar"))
        text = r.content.decode()
        for expected in ("Video call: Acme - Backend Engineer", "Follow up: Acme - Backend Engineer", "Apply by: Acme - Backend Engineer", "BEGIN:VCALENDAR"):
            self.assertIn(expected, text)
        for secret in ("PRIVATE-NOTE-A", "SECRET-DESCRIPTION-A", "PRIVATE-INTERVIEW-NOTE", "meet.example.com", "jobs.example.com", "example.com"):
            self.assertNotIn(secret, text)

    def test_one_persons_link_never_shows_another_persons_dates(self):
        text_a = self.client.get(self.link(self.a)).content.decode()
        text_b = self.client.get(self.link(self.b)).content.decode()
        self.assertNotIn("Hidden Co", text_a)
        self.assertNotIn("Spy", text_a)
        self.assertIn("Hidden Co - Spy", text_b)
        self.assertNotIn("Acme", text_b)

    def test_past_cancelled_and_closed_jobs_are_left_out(self):
        Interview.objects.create(owner=self.a, application=self.app_a, scheduled_at=timezone.now() - timedelta(days=3), kind="onsite")
        Interview.objects.create(owner=self.a, application=self.app_a, scheduled_at=timezone.now() + timedelta(days=2), kind="final", outcome="cancelled")
        text = self.client.get(self.link(self.a)).content.decode()
        self.assertNotIn("On-site", text)
        self.assertNotIn("Final round", text)
        Status.objects.filter(pk=self.app_a.status_id).update(is_terminal=True)
        text = self.client.get(self.link(self.a)).content.decode()
        self.assertNotIn("Follow up:", text)
        self.assertNotIn("Apply by:", text)

    def test_an_applied_job_has_no_apply_by_day(self):
        type(self.app_a).objects.filter(pk=self.app_a.pk).update(applied_date=timezone.localdate())
        self.assertNotIn("Apply by:", self.client.get(self.link(self.a)).content.decode())

    def test_headers_keep_the_address_private_and_allow_a_304(self):
        url = self.link(self.a)
        r = self.client.get(url)
        self.assertIn("private", r["Cache-Control"])
        self.assertIn("noindex", r["X-Robots-Tag"])
        self.assertEqual(r["Referrer-Policy"], "no-referrer")
        again = self.client.get(url, HTTP_IF_NONE_MATCH=r["ETag"])
        self.assertEqual(again.status_code, 304)
        Interview.objects.create(owner=self.a, application=self.app_a, scheduled_at=timezone.now() + timedelta(days=4), kind="phone")
        self.assertEqual(self.client.get(url, HTTP_IF_NONE_MATCH=r["ETag"]).status_code, 200)

    def test_read_only(self):
        url = self.link(self.a)
        self.assertEqual(self.client.post(url).status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)


class FeedAccessTests(FeedBase):
    def test_unknown_malformed_and_revoked_tokens_are_404(self):
        for path in ("/calendar/cal_" + "x" * 43 + ".ics", "/calendar/nonsense.ics", "/calendar/..%2Fetc.ics"):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_the_token_is_not_stored_readable_and_hashes_to_the_lookup(self):
        url = self.link(self.a)
        raw = url.rsplit("/", 1)[1][:-4]
        row = CalendarFeed.objects.get(owner=self.a)
        self.assertNotIn(raw, row.token_hash + row.token_encrypted)
        self.assertEqual(row.token, raw)
        self.assertEqual(CalendarFeed.lookup(raw).pk, row.pk)
        self.assertIsNone(CalendarFeed.lookup(raw + "x"))

    def test_a_new_link_replaces_the_old_one(self):
        old = self.link(self.a)
        self.assertEqual(self.client.get(old).status_code, 200)
        new = self.link(self.a)
        self.assertNotEqual(old, new)
        self.assertEqual(self.client.get(old).status_code, 404)
        self.assertEqual(self.client.get(new).status_code, 200)
        self.assertEqual(CalendarFeed.objects.filter(owner=self.a).count(), 1)

    def test_turning_it_off_kills_the_link(self):
        url = self.link(self.a)
        self.client.force_login(self.a)
        r = api(self.client, "delete", "/calendar-link")
        self.assertFalse(r.json()["enabled"])
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_an_inactive_account_gets_nothing(self):
        url = self.link(self.a)
        self.a.is_active = False
        self.a.save()
        self.assertEqual(self.client.get(url).status_code, 404)

    @override_settings(STILLOPEN_CALENDAR_FEED_PER_HOUR=3)
    def test_reads_are_rate_limited_per_address(self):
        url = self.link(self.a)
        codes = [self.client.get(url).status_code for _ in range(5)]
        self.assertEqual(codes, [200, 200, 200, 429, 429])

    @override_settings(STILLOPEN_CALENDAR_FEED_BAD_PER_HOUR=2)
    def test_guessing_is_rate_limited(self):
        codes = [self.client.get("/calendar/cal_" + "a" * 43 + ".ics").status_code for _ in range(4)]
        self.assertEqual(codes, [404, 404, 429, 429])


class FeedApiTests(FeedBase):
    def test_signed_out_is_401(self):
        for method in ("get", "post", "delete"):
            self.assertEqual(api(self.client, method, "/calendar-link").status_code, 401, method)

    def test_state_before_and_after(self):
        self.client.login(username="alice", password=PW)
        first = api(self.client, "get", "/calendar-link").json()
        self.assertEqual((first["enabled"], first["url"]), (False, ""))
        made = api(self.client, "post", "/calendar-link").json()
        self.assertTrue(made["enabled"])
        self.assertRegex(made["url"], r"/calendar/cal_[A-Za-z0-9_-]+\.ics$")
        self.assertEqual(api(self.client, "get", "/calendar-link").json()["url"], made["url"])
        self.assertEqual(api(self.client, "get", "/calendar-link").headers["Cache-Control"], "no-store")

    def test_each_person_sees_only_their_own_link(self):
        mine = self.link(self.a)
        self.client.login(username="bob", password=PW)
        self.assertFalse(api(self.client, "get", "/calendar-link").json()["enabled"])
        theirs = api(self.client, "post", "/calendar-link").json()["url"]
        self.assertNotEqual(theirs.split("testserver")[1], mine)
        api(self.client, "delete", "/calendar-link")
        self.client.logout()
        self.assertEqual(self.client.get(mine).status_code, 200)  # bob switching his off leaves alice's alone

    @override_settings(STILLOPEN_CALENDAR_LINKS_PER_HOUR=2)
    def test_making_links_is_rate_limited(self):
        self.client.login(username="alice", password=PW)
        codes = [api(self.client, "post", "/calendar-link").status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])


class IcsWriterTests(TestCase):
    def test_escaping_and_folding(self):
        self.assertEqual(ics.escape("a,b;c\\d\nINJECT:1"), "a\\,b\\;c\\\\d INJECT:1")
        folded = ics.fold("SUMMARY:" + "é" * 80)
        for line in folded.split("\r\n"):
            self.assertLessEqual(len(line.encode()), 75)
        self.assertEqual(folded.replace("\r\n ", ""), "SUMMARY:" + "é" * 80)

    def test_robots_keeps_the_feed_out_of_search(self):
        self.assertIn("Disallow: /calendar/", self.client.get("/robots.txt").content.decode())

    def test_json_dump_of_state_has_no_other_keys(self):
        # the card gets only these fields -- no owner id, no hash
        user = person("carol")
        self.client.force_login(user)
        data = api(self.client, "post", "/calendar-link").json()
        self.assertEqual(set(data), {"enabled", "url", "created_at", "last_used_at"})
        self.assertNotIn(CalendarFeed.objects.get(owner=user).token_hash, json.dumps(data))
