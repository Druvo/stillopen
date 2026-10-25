"""Per-person time zone: at the same instant a person in Dhaka and one in Los Angeles are on different days, and everything that turns a moment
into a calendar day (streak, today's practice, follow-ups, deadlines, the greeting, the stats) follows each person's own clock."""
import datetime as dt
from datetime import date, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils import timezone

from tracker import middleware
from tracker.models import Application, PrepChallenge, PrepPlan, SiteConfig, Status, UserProfile
from tracker.services import apply as apply_service
from tracker.services import quiz, stats, tz
from tracker.tests_api import BASE, PW, job, person
from tracker.tests_quiz import QuizBase

User = get_user_model()
# 2026-10-25 20:00 UTC: already 02:00 on the 26th in Dhaka (UTC+6), still 13:00 on the 25th in Los Angeles (UTC-7, summer time until 1 November).
INSTANT = dt.datetime(2026, 10, 25, 20, 0, tzinfo=dt.timezone.utc)
DHAKA_DAY, LA_DAY = date(2026, 10, 26), date(2026, 10, 25)


def at_instant():
    return mock.patch("django.utils.timezone.now", return_value=INSTANT)


def set_zone(user, name):
    UserProfile.objects.update_or_create(user=user, defaults={"timezone": name})
    return User.objects.get(pk=user.pk)


class Helpers(TestCase):
    def setUp(self):
        self.dhaka = set_zone(person("dhaka"), "Asia/Dhaka")
        self.la = set_zone(person("la"), "America/Los_Angeles")
        self.blank = person("blank")

    def test_the_same_instant_is_a_different_day_for_each_person(self):
        with at_instant():
            self.assertEqual(tz.today_for(self.dhaka), DHAKA_DAY)
            self.assertEqual(tz.today_for(self.la), LA_DAY)
            self.assertEqual((tz.now_for(self.dhaka).hour, tz.now_for(self.la).hour), (2, 13))

    def test_blank_means_the_sites_zone_exactly_as_before(self):
        with at_instant():
            self.assertEqual(tz.today_for(self.blank), timezone.localdate())
            self.assertEqual(tz.today_for(None), timezone.localdate())
            self.assertEqual(tz.today_for(self.blank.pk), timezone.localdate())  # an id works too
        self.assertEqual(str(tz.zone_for(self.blank)), settings_zone())

    def test_a_zone_that_can_no_longer_be_loaded_falls_back_quietly(self):
        UserProfile.objects.filter(user=self.blank).update(timezone="Mars/Olympus")
        self.assertEqual(str(tz.zone_for(self.blank)), settings_zone())

    def test_validation(self):
        for good in ("", "Asia/Dhaka", "America/Los_Angeles", "UTC", "Europe/London"):
            self.assertTrue(tz.is_valid(good), good)
        for bad in ("Mars/Olympus", "dhaka", "../etc/passwd", "Asia/Dhaka ; drop", "EST5EDT/x"):
            self.assertFalse(tz.is_valid(bad), bad)
        with self.assertRaises(Exception):
            tz.validate_timezone("Nope/Nope")
        self.assertTrue(set(tz.COMMON_ZONES) <= set(tz.all_zones()))

    def test_local_date_of_a_stored_moment(self):
        self.assertEqual(tz.local_date(INSTANT, self.dhaka), DHAKA_DAY)
        self.assertEqual(tz.local_date(INSTANT, self.la), LA_DAY)
        self.assertIsNone(tz.local_date(None, self.la))


def settings_zone():
    from django.conf import settings

    return settings.TIME_ZONE


class Practice(QuizBase):
    """Streak, today's practice and the 'practise today' nudge, per person."""

    def setUp(self):
        super().setUp()
        self.dhaka = set_zone(self.user, "Asia/Dhaka")
        self.la = set_zone(self.other, "America/Los_Angeles")

    def finished(self, plan, day):
        number = plan.challenges.count() + 1
        return PrepChallenge.objects.create(plan=plan, number=number, day=day, completed_at=INSTANT)

    def test_todays_practice_is_made_for_each_persons_own_day(self):
        pd, pl = self.plan_with_questions(owner=self.dhaka), self.plan_with_questions(owner=self.la)
        with at_instant():
            self.assertEqual(quiz.build_challenge(pd, 3).day, DHAKA_DAY)
            self.assertEqual(quiz.build_challenge(pl, 3).day, LA_DAY)

    def test_the_streak_counts_from_each_persons_today(self):
        pd, pl = self.plan_with_questions(owner=self.dhaka), self.plan_with_questions(owner=self.la)
        self.finished(pd, date(2026, 10, 24))
        self.finished(pl, date(2026, 10, 24))
        with at_instant():
            self.assertEqual(quiz.streak(pd), 0)  # in Dhaka the 26th has begun and the 25th was missed
            self.assertEqual(quiz.streak(pl), 1)  # in Los Angeles the 25th is still today, so yesterday's practice keeps the streak alive

    def test_a_practice_done_on_the_25th_still_counts_today_in_la_but_is_yesterday_in_dhaka(self):
        pd, pl = self.plan_with_questions(owner=self.dhaka), self.plan_with_questions(owner=self.la)
        self.finished(pd, LA_DAY)
        self.finished(pl, LA_DAY)
        with at_instant():
            self.assertEqual((quiz.streak(pd), quiz.streak(pl)), (1, 1))  # alive either way, but...
            self.assertEqual(quiz.due_plans(self.dhaka), [pd])  # ...Dhaka's day 26 has no practice yet
            self.assertEqual(quiz.due_plans(self.la), [])  # LA already practised today

    def test_answers_are_dated_by_the_persons_day(self):
        plan = self.plan_with_questions(owner=self.dhaka)
        with at_instant():
            challenge = quiz.build_challenge(plan, 2)
            quiz.submit(challenge, {item.question_id: [0] if item.question.kind == "single" else [0, 2] for item in challenge.items.select_related("question")})
        self.assertEqual({a.answered_on for a in challenge.answers.all()}, {DHAKA_DAY})

    def test_the_api_reports_done_today_by_the_persons_day(self):
        pl = self.plan_with_questions(owner=self.la)
        self.finished(pl, LA_DAY)
        self.client.force_login(self.la)
        with at_instant():
            self.assertTrue(self.client.get(f"{BASE}/prep/plans/{pl.pk}").json()["done_today"])
        pd = self.plan_with_questions(owner=self.dhaka)
        self.finished(pd, LA_DAY)
        self.client.force_login(self.dhaka)
        with at_instant():
            self.assertFalse(self.client.get(f"{BASE}/prep/plans/{pd.pk}").json()["done_today"])


class FollowUpsAndDeadlines(TestCase):
    def setUp(self):
        cache.clear()
        self.dhaka = set_zone(person("dhaka"), "Asia/Dhaka")
        self.la = set_zone(person("la"), "America/Los_Angeles")
        applied = Status.objects.filter(counts_as_applied=True).first()
        for owner in (self.dhaka, self.la):
            job(owner, company="Due", follow_up_date=DHAKA_DAY, status=applied, deadline=DHAKA_DAY, applied_date=date(2026, 10, 19))

    def test_a_follow_up_dated_the_26th_is_due_in_dhaka_but_not_yet_in_la(self):
        with at_instant():
            self.assertEqual([a.company for a in apply_service.due_followups(self.dhaka)], ["Due"])
            self.assertEqual(list(apply_service.due_followups(self.la)), [])
            self.assertEqual(apply_service.due_followups_to_email(self.la).count(), 0)
            self.assertEqual(apply_service.due_followups_to_email(self.dhaka).count(), 1)

    def test_snoozing_counts_from_the_persons_today(self):
        with at_instant():
            for owner, today in ((self.dhaka, DHAKA_DAY), (self.la, LA_DAY)):
                app = Application.objects.get(owner=owner)
                apply_service.followup_snooze(app, 3)
                app.refresh_from_db()
                self.assertEqual(app.follow_up_date, today + timedelta(days=3))

    def test_the_dashboard_counts_deadline_days_and_greets_by_the_persons_clock(self):
        with at_instant():
            for owner, days, hello in ((self.dhaka, 0, "Good evening"), (self.la, 1, "Good afternoon")):
                self.client.force_login(owner)
                data = self.client.get(f"{BASE}/dashboard").json()
                self.assertEqual(data["jobs"][0]["days_left"], days, owner.username)
                self.assertTrue(data["greeting"].startswith(hello), data["greeting"])
                self.assertEqual([f["company"] for f in data["followups"]], ["Due"] if owner == self.dhaka else [])
                self.assertTrue(self.client.get(f"{BASE}/me").json()["greeting"].startswith(hello))

    def test_the_checklist_says_how_many_days_in_the_persons_own_days(self):
        app = Application.objects.get(owner=self.la)
        with at_instant():
            texts = [i["text"] for i in apply_service.checklist(app, SiteConfig.for_user(self.la), [])]
        self.assertTrue(any("in 1 day" in t for t in texts), texts)

    def test_stats_this_week_uses_the_persons_day(self):
        with at_instant():
            self.assertEqual(stats.candidate_stats(self.dhaka)["as_of"], DHAKA_DAY.isoformat())
            self.assertEqual(stats.candidate_stats(self.la)["as_of"], LA_DAY.isoformat())
            self.assertEqual(self.client.get(f"{BASE}/stats").status_code, 401)  # signed out is still refused

    def test_people_with_a_blank_zone_see_exactly_what_they_saw_before(self):
        blank = person("blank")
        job(blank, company="Plain", deadline=timezone.localdate() + timedelta(days=2))
        self.client.force_login(blank)
        self.assertEqual(self.client.get(f"{BASE}/dashboard").json()["jobs"][0]["days_left"], 2)
        self.assertEqual(stats.candidate_stats(blank)["as_of"], timezone.localdate().isoformat())


class ProfileApi(TestCase):
    def setUp(self):
        cache.clear()
        self.u = person("zed")
        self.client.force_login(self.u)

    def put(self, **data):
        import json

        return self.client.put(f"{BASE}/profile", data=json.dumps(data), content_type="application/json")

    def test_it_is_read_and_written_through_the_profile_endpoints(self):
        data = self.client.get(f"{BASE}/profile").json()
        self.assertEqual(data["profile"]["timezone"], "")
        self.assertIn("Asia/Dhaka", data["choices"]["timezones"])
        self.assertEqual(data["site"]["timezone"], settings_zone())
        r = self.put(timezone="America/Los_Angeles")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["profile"]["timezone"], "America/Los_Angeles")
        self.assertEqual(UserProfile.objects.get(user=self.u).timezone, "America/Los_Angeles")

    def test_an_unknown_zone_is_a_plain_error_and_nothing_is_saved(self):
        r = self.put(timezone="Mars/Olympus")
        self.assertEqual(r.status_code, 400)
        self.assertIn("not a time zone we know", r.json()["error"])
        self.assertIn("timezone", r.json()["fields"])
        self.assertEqual(UserProfile.objects.get(user=self.u).timezone, "")

    def test_a_save_that_does_not_mention_it_keeps_it_and_blank_clears_it(self):
        self.put(timezone="Asia/Dhaka")
        self.put(about="Hello")
        self.assertEqual(UserProfile.objects.get(user=self.u).timezone, "Asia/Dhaka")
        self.put(timezone="")
        self.assertEqual(UserProfile.objects.get(user=self.u).timezone, "")

    def test_it_is_private_to_the_person(self):
        other = person("other")
        self.put(timezone="Asia/Tokyo")
        self.client.force_login(other)
        self.assertEqual(self.client.get(f"{BASE}/profile").json()["profile"]["timezone"], "")


class RequestsRunInTheirZone(TestCase):
    def setUp(self):
        cache.clear()

    def run_as(self, user):
        seen = {}

        def view(request):
            seen["zone"] = timezone.get_current_timezone_name()
            return "ok"

        request = RequestFactory().get("/")
        request.user = user
        middleware.PersonTimezoneMiddleware(view)(request)
        return seen["zone"], timezone.get_current_timezone_name()

    def test_a_signed_in_request_runs_in_the_persons_zone_and_is_reset_after(self):
        la = set_zone(person("la"), "America/Los_Angeles")
        inside, after = self.run_as(la)
        self.assertEqual(inside, "America/Los_Angeles")
        self.assertEqual(after, settings_zone())

    def test_blank_and_signed_out_use_the_sites_zone(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(self.run_as(person("blank"))[0], settings_zone())
        self.assertEqual(self.run_as(AnonymousUser())[0], settings_zone())

    def test_a_saved_change_applies_at_once_and_the_zone_costs_no_query_when_remembered(self):
        user = person("mover")
        self.assertEqual(self.run_as(user)[0], settings_zone())
        profile = UserProfile.for_user(user)
        profile.timezone = "Asia/Tokyo"
        profile.save()  # the signal forgets the remembered zone
        self.assertEqual(self.run_as(user)[0], "Asia/Tokyo")
        with self.assertNumQueries(0):
            self.run_as(user)

    def test_interview_times_people_type_are_in_their_own_zone(self):
        import json

        la = set_zone(person("la"), "America/Los_Angeles")
        app = job(la)
        self.client.force_login(la)
        r = self.client.post(f"{BASE}/interviews", data=json.dumps({"application": app.pk, "scheduled_at": "2026-11-03T10:00", "kind": "video"}), content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        item = la.interviews.get()
        self.assertEqual(item.scheduled_at, dt.datetime(2026, 11, 3, 18, 0, tzinfo=dt.timezone.utc))  # 10:00 in Los Angeles is 18:00 UTC
        self.assertEqual(self.client.get(f"{BASE}/interviews").json()["upcoming"][0]["scheduled_local"], "2026-11-03T10:00")


class FrontEndHasIt(SimpleTestCase):
    def test_the_dismissal_is_a_saved_preference(self):
        from tracker.services import preferences

        self.assertIn("tz_prompt_dismissed", preferences.BOOLEANS)
