"""The notification centre, the AI usage page and the optional update check: behaviour, producers and strict per-person isolation."""
import json
from datetime import timedelta
from unittest import mock

from allauth.account.models import EmailAddress
from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from tracker.models import AIUsageEvent, Interview, Notification, ScanRun, SiteConfig, Status, UserProfile
from tracker.services import ai, aiusage, liveness, notifications, pipeline, updatecheck
from tracker.tests_api import BASE, job, person


def login(user):
    c = Client()
    c.force_login(user)
    return c


def post(client, path, body=None):
    return client.post(f"{BASE}{path}", data=json.dumps(body or {}), content_type="application/json")


class NotificationService(TestCase):
    def setUp(self):
        self.u = person("alice")

    def test_a_notice_is_made_trimmed_and_unread(self):
        n = notifications.notify(self.u, "search", "T" * 500, "x" * 900, "/jobs/1/apply")
        self.assertEqual((len(n.title), len(n.text)), (120, 300))
        self.assertIsNone(n.read_at)
        self.assertEqual(notifications.unread_count(self.u), 1)

    def test_a_link_is_an_app_path_only(self):
        for bad in ("https://evil.example/x", "//evil.example", "javascript:alert(1)", "\\\\evil"):
            self.assertEqual(notifications.notify(self.u, "search", "t", link=bad).link, "")
        self.assertEqual(notifications.notify(self.u, "search", "t", link="/interviews").link, "/interviews")

    def test_the_same_key_is_announced_once_even_after_clearing(self):
        self.assertIsNotNone(notifications.notify(self.u, "closed", "a", key="closed:1"))
        self.assertIsNone(notifications.notify(self.u, "closed", "a", key="closed:1"))
        notifications.clear_all(self.u)
        self.assertIsNone(notifications.notify(self.u, "closed", "a", key="closed:1"))
        self.assertEqual(notifications.unread_count(self.u), 0)

    def test_a_switched_off_kind_is_not_made_and_unknown_kinds_are_ignored(self):
        notifications.set_muted(self.u, ["search", "nonsense"])
        self.assertEqual(UserProfile.for_user(self.u).notify_muted, ["search"])
        self.assertIsNone(notifications.notify(self.u, "search", "t"))
        self.assertIsNone(notifications.notify(self.u, "nonsense", "t"))
        self.assertIsNotNone(notifications.notify(self.u, "closed", "t"))

    def test_at_most_200_are_kept_and_the_oldest_go(self):
        now = timezone.now()
        Notification.objects.bulk_create([Notification(owner=self.u, kind="search", title=f"n{i}", created_at=now - timedelta(minutes=300 - i)) for i in range(200)])
        notifications.notify(self.u, "search", "newest")
        titles = list(Notification.objects.filter(owner=self.u).values_list("title", flat=True))
        self.assertEqual(len(titles), 200)
        self.assertIn("newest", titles)
        self.assertNotIn("n0", titles)

    def test_the_cap_is_per_person(self):
        other = person("bob")
        Notification.objects.bulk_create([Notification(owner=other, kind="search", title="x") for _ in range(200)])
        notifications.notify(self.u, "search", "mine")
        self.assertEqual(Notification.objects.filter(owner=other).count(), 200)


class NotificationApi(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        self.ca, self.cb = login(self.a), login(self.b)
        self.mine = notifications.notify(self.a, "search", "Your search found 2 new jobs", "Open your dashboard.", "/")
        self.theirs = notifications.notify(self.b, "search", "Bob only", "secret-for-bob", "/")

    def test_summary_is_small_and_counts_only_my_unread(self):
        r = self.ca.get(f"{BASE}/notifications/summary")
        self.assertEqual(r.json(), {"unread": 1})

    def test_summary_answers_304_when_nothing_changed_and_a_new_body_when_it_did(self):
        r = self.ca.get(f"{BASE}/notifications/summary")
        etag = r["ETag"]
        self.assertEqual(self.ca.get(f"{BASE}/notifications/summary", HTTP_IF_NONE_MATCH=etag).status_code, 304)
        notifications.notify(self.a, "closed", "x")
        r = self.ca.get(f"{BASE}/notifications/summary", HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["unread"], 2)

    def test_the_list_never_shows_someone_elses_notice(self):
        data = self.ca.get(f"{BASE}/notifications").json()
        self.assertEqual([i["title"] for i in data["items"]], ["Your search found 2 new jobs"])
        self.assertNotIn("secret-for-bob", json.dumps(data))

    def test_mark_one_read_and_all_read_and_clear(self):
        second = notifications.notify(self.a, "closed", "two")
        self.assertEqual(post(self.ca, f"/notifications/{self.mine.pk}/read").json(), {"unread": 1})
        self.assertEqual(post(self.ca, "/notifications/read-all").json(), {"unread": 0})
        self.assertEqual(self.ca.delete(f"{BASE}/notifications/{second.pk}").json(), {"unread": 0})
        self.assertEqual(len(self.ca.get(f"{BASE}/notifications").json()["items"]), 1)
        post(self.ca, "/notifications/clear")
        self.assertEqual(self.ca.get(f"{BASE}/notifications").json()["items"], [])
        self.assertEqual(len(self.cb.get(f"{BASE}/notifications").json()["items"]), 1)

    def test_someone_elses_notice_is_a_404_and_stays_untouched(self):
        self.assertEqual(post(self.ca, f"/notifications/{self.theirs.pk}/read").status_code, 404)
        self.assertEqual(self.ca.delete(f"{BASE}/notifications/{self.theirs.pk}").status_code, 404)
        self.theirs.refresh_from_db()
        self.assertIsNone(self.theirs.read_at)
        self.assertFalse(self.theirs.cleared)

    def test_read_all_and_clear_touch_only_my_notices(self):
        post(self.ca, "/notifications/read-all")
        post(self.ca, "/notifications/clear")
        self.theirs.refresh_from_db()
        self.assertIsNone(self.theirs.read_at)
        self.assertFalse(self.theirs.cleared)

    def test_settings_round_trip_and_stay_mine(self):
        kinds = self.ca.get(f"{BASE}/notifications/settings").json()["kinds"]
        self.assertTrue(all(k["on"] for k in kinds))
        r = self.ca.put(f"{BASE}/notifications/settings", data=json.dumps({"muted": ["deadline"]}), content_type="application/json")
        self.assertEqual({k["key"]: k["on"] for k in r.json()["kinds"]}["deadline"], False)
        self.assertTrue(all(k["on"] for k in self.cb.get(f"{BASE}/notifications/settings").json()["kinds"]))

    def test_signed_out_is_refused(self):
        self.assertEqual(Client().get(f"{BASE}/notifications/summary").status_code, 401)


class Producers(TestCase):
    def setUp(self):
        cache.clear()
        self.u = person("alice")

    def titles(self, user=None):
        return list(Notification.objects.filter(owner=user or self.u).values_list("title", flat=True))

    def test_a_finished_search_with_new_jobs(self):
        run = ScanRun.objects.create(owner=self.u, running=False, added=3)
        notifications.search_finished(run)
        notifications.search_finished(run)
        self.assertEqual(self.titles(), ["Your search found 3 new jobs"])

    def test_a_search_with_nothing_new_makes_no_notice(self):
        notifications.search_finished(ScanRun.objects.create(owner=self.u, running=False, added=0))
        self.assertEqual(self.titles(), [])

    def test_a_job_the_check_finds_closed_is_announced_once(self):
        app = job(self.u, url="https://jobs.example.com/1", company="Acme", role="Dev")
        with mock.patch("tracker.services.liveness.check_url", return_value=("expired", "closed")):
            liveness.start_run(self.u, background=False)
            liveness.start_run(self.u, background=False)
        self.assertEqual(self.titles(), ["Acme: the posting looks closed"])
        self.assertEqual(Notification.objects.get(owner=self.u).link, f"/jobs/{app.pk}/edit")

    def test_a_job_that_stays_open_makes_no_notice(self):
        job(self.u, url="https://jobs.example.com/1")
        with mock.patch("tracker.services.liveness.check_url", return_value=("active", "ok")):
            liveness.start_run(self.u, background=False)
        self.assertEqual(self.titles(), [])

    def test_an_interview_reminder_that_was_sent(self):
        EmailAddress.objects.create(user=self.u, email=self.u.email, verified=True, primary=True)
        app = job(self.u, company="Acme")
        Interview.objects.create(owner=self.u, application=app, scheduled_at=timezone.now() + timedelta(hours=5), kind="video")
        items = pipeline.due_interview_reminders(self.u)
        self.assertTrue(pipeline.send_interview_reminders(self.u, items))
        self.assertEqual(self.titles(), ["Interview soon: Acme"])

    def test_no_notice_when_the_reminder_email_could_not_be_sent(self):
        app = job(self.u)
        Interview.objects.create(owner=self.u, application=app, scheduled_at=timezone.now() + timedelta(hours=5), kind="video")
        self.assertFalse(pipeline.send_interview_reminders(self.u, pipeline.due_interview_reminders(self.u)))
        self.assertEqual(self.titles(), [])

    def test_drafts_waiting(self):
        notifications.drafts_waiting(self.u, 0)
        notifications.drafts_waiting(self.u, 2)
        self.assertEqual(self.titles(), ["2 CV drafts waiting for your review"])

    def test_the_dashboard_announces_a_close_deadline_and_a_due_follow_up_once(self):
        today = timezone.localdate()
        job(self.u, company="Acme", deadline=today + timedelta(days=1), url="https://x.example/1")
        job(self.u, company="Beta", follow_up_date=today, status=Status.objects.get(name="Applied"), applied_date=today - timedelta(days=7))
        c = login(self.u)
        with mock.patch("tracker.services.scan.maybe_auto_start"):
            c.get(f"{BASE}/dashboard")
            c.get(f"{BASE}/dashboard")
        self.assertCountEqual(self.titles(), ["Acme: apply by tomorrow", "Follow up with Beta"])
        with mock.patch("tracker.services.scan.maybe_auto_start"):
            post(c, "/notifications/clear")
            c.get(f"{BASE}/dashboard")
        self.assertEqual(notifications.unread_count(self.u), 0)  # cleared stays cleared

    def test_a_far_deadline_makes_no_notice_and_a_muted_kind_stays_quiet(self):
        today = timezone.localdate()
        job(self.u, company="Far", deadline=today + timedelta(days=60))
        job(self.u, company="Near", deadline=today + timedelta(days=1), url="https://x.example/2")
        notifications.set_muted(self.u, ["deadline"])
        with mock.patch("tracker.services.scan.maybe_auto_start"):
            login(self.u).get(f"{BASE}/dashboard")
        self.assertEqual(self.titles(), [])

    def test_one_persons_dashboard_never_makes_a_notice_for_another(self):
        bob = person("bob")
        job(bob, company="Bobco", deadline=timezone.localdate() + timedelta(days=1), url="https://x.example/3")
        with mock.patch("tracker.services.scan.maybe_auto_start"):
            login(self.u).get(f"{BASE}/dashboard")
        self.assertEqual(Notification.objects.count(), 0)


FAKE_CONFIG = dict(ai_provider="openai", ai_model="gpt-4o-mini")


def fake_backend(tokens=(100, 50), fail=False):
    def backend(system, user, config):
        if fail:
            raise ai.AIError("The AI service did not answer.")
        ai._last_usage.set({"input_tokens": tokens[0], "output_tokens": tokens[1], "cost_usd": ai.estimate_cost(config.ai_model, *tokens), "cost_is_estimate": True})
        return "reply"
    return backend


class AiUsageRecording(TestCase):
    def setUp(self):
        self.u = person("alice")
        self.config = SiteConfig(**FAKE_CONFIG)

    def test_a_call_records_model_and_duration(self):
        with mock.patch.dict(ai.BACKENDS, {"openai": fake_backend()}):
            ai.complete(self.config, "s", "u", purpose="refine", owner=self.u)
        e = AIUsageEvent.objects.get(owner=self.u)
        self.assertEqual((e.model, e.purpose, e.ok), ("gpt-4o-mini", "refine", True))
        self.assertIsNotNone(e.duration_ms)

    def test_a_failed_call_is_recorded_as_failed_and_still_raises(self):
        with mock.patch.dict(ai.BACKENDS, {"openai": fake_backend(fail=True)}):
            with self.assertRaises(ai.AIError):
                ai.complete(self.config, "s", "u", purpose="refine", owner=self.u)
        e = AIUsageEvent.objects.get(owner=self.u)
        self.assertFalse(e.ok)
        self.assertIsNone(e.input_tokens)

    def test_a_failure_does_not_count_in_the_settings_page_total(self):
        with mock.patch.dict(ai.BACKENDS, {"openai": fake_backend(fail=True)}):
            with self.assertRaises(ai.AIError):
                ai.complete(self.config, "s", "u", owner=self.u)
        data = login(self.u).get(f"{BASE}/ai-settings").json()
        self.assertEqual(data["usage"]["calls"], 0)


class AiUsageReport(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")

    def event(self, owner, **kw):
        fields = dict(owner=owner, provider="openai", purpose="evaluate", model="gpt-4o-mini", input_tokens=1000, output_tokens=200, cost_usd="0.0100", duration_ms=500, ok=True)
        fields.update(kw)
        return AIUsageEvent.objects.create(**fields)

    def test_totals_per_model_per_purpose_failures_and_latency(self):
        for ms in (100, 200, 300, 400, 5000):
            self.event(self.a, duration_ms=ms)
        self.event(self.a, purpose="refine", model="mystery-model", cost_usd=None)
        self.event(self.a, ok=False, input_tokens=None, output_tokens=None, cost_usd=None, duration_ms=9000)
        r = aiusage.report(self.a)
        self.assertEqual((r["calls"], r["failed"]), (7, 1))
        self.assertEqual((r["input_tokens"], r["output_tokens"]), (6000, 1200))
        self.assertEqual(r["costs"], [{"currency": "USD", "amount": 0.05}])
        priced = next(m for m in r["models"] if m["model"] == "gpt-4o-mini")
        mystery = next(m for m in r["models"] if m["model"] == "mystery-model")
        self.assertEqual(priced["cost"], 0.05)
        self.assertIsNone(mystery["cost"])  # an unpriced model is never given a guessed cost
        self.assertEqual(mystery["unpriced_calls"], 1)
        self.assertEqual(r["unpriced_calls"], 1)
        self.assertEqual({p["purpose"]: p["calls"] for p in r["purposes"]}, {"evaluate": 6, "refine": 1})
        self.assertEqual(r["latency"]["p50_ms"], 300)  # six timed successful calls: 100 200 300 400 500 5000
        self.assertEqual(r["latency"]["p95_ms"], 5000)  # the failed call's 9000 ms is not counted

    def test_older_events_without_a_duration_leave_latency_blank(self):
        self.event(self.a, duration_ms=None)
        r = aiusage.report(self.a)
        self.assertEqual(r["latency"], {"samples": 0, "p50_ms": None, "p95_ms": None})

    def test_the_last_25_calls_newest_first(self):
        for i in range(30):
            self.event(self.a, input_tokens=i)
        recent = aiusage.report(self.a)["recent"]
        self.assertEqual(len(recent), 25)
        self.assertEqual(recent[0]["input_tokens"], 29)

    def test_only_my_calls(self):
        self.event(self.a)
        self.event(self.b, input_tokens=99999, purpose="tailor")
        data = login(self.a).get(f"{BASE}/ai-usage").json()
        self.assertEqual(data["calls"], 1)
        self.assertNotIn("99999", json.dumps(data))
        self.assertEqual(Client().get(f"{BASE}/ai-usage").status_code, 401)

    def test_an_admin_sees_only_their_own_numbers(self):
        admin = person("boss")
        admin.is_staff = True
        admin.save()
        self.event(self.a)
        self.assertEqual(login(admin).get(f"{BASE}/ai-usage").json()["calls"], 0)

    def test_no_prompt_or_reply_text_can_appear(self):
        with mock.patch.dict(ai.BACKENDS, {"openai": fake_backend()}):
            ai.complete(SiteConfig(**FAKE_CONFIG), "SECRET-SYSTEM-PROMPT", "SECRET-USER-TEXT private cv", purpose="tailor", owner=self.a)
        body = login(self.a).get(f"{BASE}/ai-usage").content.decode()
        for text in ("SECRET-SYSTEM-PROMPT", "SECRET-USER-TEXT", "private cv", "reply"):
            self.assertNotIn(text, body)
        self.assertFalse({"prompt", "response", "content", "text"} & {f.name for f in AIUsageEvent._meta.fields})
        keys = set(login(self.a).get(f"{BASE}/ai-usage").json()["recent"][0])
        self.assertEqual(keys, {"id", "at", "purpose", "provider", "model", "input_tokens", "output_tokens", "cost", "currency", "duration_ms", "ok"})


class UpdateCheck(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = person("boss")
        self.admin.is_staff = True
        self.admin.save()
        self.user = person("alice")

    def response(self, tag="v9.9.9", url="https://github.com/Druvo/stillopen/releases/tag/v9.9.9", **extra):
        return mock.Mock(status_code=200, json=lambda: {"tag_name": tag, "html_url": url, **extra})

    def test_the_running_version_comes_from_the_version_file(self):
        self.assertRegex(updatecheck.running_version(), r"^\d+\.\d+\.\d+$")
        self.assertEqual(login(self.user).get(f"{BASE}/version").json()["version"], updatecheck.running_version())

    def test_off_means_no_request_at_all(self):
        with mock.patch("tracker.services.netguard.safe_get") as get:
            out = login(self.admin).get(f"{BASE}/update-check").json()
            updatecheck.status(SiteConfig.load())
        get.assert_not_called()
        self.assertEqual((out["enabled"], out["available"]), (False, False))

    def test_on_asks_the_fixed_releases_address_once_and_caches_for_hours(self):
        SiteConfig.objects.update_or_create(pk=1, defaults={"update_check_enabled": True})
        c = login(self.admin)
        with mock.patch("tracker.services.netguard.safe_get", return_value=self.response()) as get:
            first = c.get(f"{BASE}/update-check").json()
            c.get(f"{BASE}/update-check")
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args[0][0], "https://api.github.com/repos/Druvo/stillopen/releases/latest")
        self.assertNotIn("params", get.call_args[1])
        self.assertTrue(first["available"])
        self.assertEqual(first["latest"], "9.9.9")
        self.assertTrue(first["url"].startswith("https://github.com/Druvo/stillopen/"))

    def test_not_newer_not_available(self):
        SiteConfig.objects.update_or_create(pk=1, defaults={"update_check_enabled": True})
        with mock.patch("tracker.services.netguard.safe_get", return_value=self.response(tag="v0.0.1", url="https://github.com/Druvo/stillopen/releases/tag/v0.0.1")):
            self.assertFalse(login(self.admin).get(f"{BASE}/update-check").json()["available"])

    def test_failures_are_silent_and_not_retried_at_once(self):
        from tracker.services.netguard import FetchError

        SiteConfig.objects.update_or_create(pk=1, defaults={"update_check_enabled": True})
        with mock.patch("tracker.services.netguard.safe_get", side_effect=FetchError("down")) as get:
            c = login(self.admin)
            self.assertFalse(c.get(f"{BASE}/update-check").json()["available"])
            c.get(f"{BASE}/update-check")
        self.assertEqual(get.call_count, 1)

    def test_a_prerelease_or_a_foreign_link_is_never_offered(self):
        SiteConfig.objects.update_or_create(pk=1, defaults={"update_check_enabled": True})
        for resp in (self.response(prerelease=True), self.response(url="https://evil.example/x"), self.response(tag="nightly")):
            cache.clear()
            with mock.patch("tracker.services.netguard.safe_get", return_value=resp):
                self.assertFalse(updatecheck.status(SiteConfig.load())["available"])

    def test_only_admins_can_ask_and_me_tells_only_admins(self):
        SiteConfig.objects.update_or_create(pk=1, defaults={"update_check_enabled": True})
        with mock.patch("tracker.services.netguard.safe_get") as get:
            self.assertEqual(login(self.user).get(f"{BASE}/update-check").status_code, 403)
        get.assert_not_called()
        self.assertFalse(login(self.user).get(f"{BASE}/me").json()["update_check_enabled"])
        self.assertTrue(login(self.admin).get(f"{BASE}/me").json()["update_check_enabled"])

    def test_version_comparison(self):
        self.assertTrue(updatecheck.is_newer("v0.2.0", "0.1.9"))
        self.assertTrue(updatecheck.is_newer("1.0", "0.9.9"))
        self.assertFalse(updatecheck.is_newer("0.1.0", "0.1.0"))
        self.assertFalse(updatecheck.is_newer("1.0.0-rc1", "0.1.0"))
        self.assertFalse(updatecheck.is_newer("2.0.0", ""))
