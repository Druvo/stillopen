"""Dashboard and Insights visuals: funnel periods, activity, goals and streaks, calendar, "Worth a look next", and their isolation."""
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from tracker.models import Application, Interview, Offer, Status, UserProfile
from tracker.services import dashviz, preferences, stats

User = get_user_model()
PW = "correct-horse-battery-staple"
TODAY = date(2026, 10, 25)


def person(name):
    return User.objects.create_user(name, email=f"{name}@example.com", password=PW)


def aware(day, hour=12):
    return timezone.make_aware(datetime(day.year, day.month, day.day, hour))


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        self.applied = Status.objects.get(name="Applied")
        self.evaluated = Status.objects.get(name="Evaluated")

    def job(self, owner=None, **kw):
        fields = {"owner": owner or self.a, "company": "Acme", "role": "Dev", "status": self.applied, "found_date": TODAY - timedelta(days=100)}
        fields.update(kw)
        return Application.objects.create(**fields)

    def numbers(self, user=None):
        return stats.candidate_stats(user or self.a, TODAY)


class Funnel(Base):
    def test_period_boundaries(self):
        self.job(applied_date=TODAY)  # in all three
        self.job(applied_date=TODAY - timedelta(days=29))  # last day of "30"
        self.job(applied_date=TODAY - timedelta(days=30))  # in 90 and all, not 30
        self.job(applied_date=TODAY - timedelta(days=89))
        self.job(applied_date=TODAY - timedelta(days=90))  # all only
        f = self.numbers()["funnel"]
        sent = {k: f[k]["stages"][0]["count"] for k in f}
        self.assertEqual(sent, {"30": 2, "90": 4, "all": 5})

    def test_stages_never_grow(self):
        a = self.job(applied_date=TODAY)
        Interview.objects.create(owner=self.a, application=a, scheduled_at=aware(TODAY))
        b = self.job(applied_date=TODAY)
        Offer.objects.create(owner=self.a, application=b, base=1)
        self.job(applied_date=TODAY, status=Status.objects.get(name="Responded"))
        self.job(applied_date=TODAY)
        stages = self.numbers()["funnel"]["30"]["stages"]
        self.assertEqual([s["count"] for s in stages], [4, 3, 2, 1])

    def test_unapplied_jobs_and_no_applied_date(self):
        self.job(status=self.evaluated)
        self.job()  # applied status, no date: all time only
        f = self.numbers()["funnel"]
        self.assertEqual((f["30"]["stages"][0]["count"], f["all"]["stages"][0]["count"]), (0, 1))

    def test_only_own_jobs(self):
        self.job(owner=self.b, applied_date=TODAY)
        self.assertEqual(self.numbers()["funnel"]["all"]["stages"][0]["count"], 0)


class Activity(Base):
    def test_counts_per_day_and_empty(self):
        self.assertEqual(self.numbers()["activity"]["days"], {})
        a = self.job(applied_date=TODAY)
        self.job(applied_date=TODAY)
        self.job(applied_date=TODAY - timedelta(days=400))  # outside the year
        Interview.objects.create(owner=self.a, application=a, scheduled_at=aware(TODAY - timedelta(days=2)))
        Interview.objects.create(owner=self.a, application=a, scheduled_at=aware(TODAY - timedelta(days=3)), outcome="cancelled")
        act = self.numbers()["activity"]
        self.assertEqual(act["days"][TODAY.isoformat()], {"applied": 2, "interviews": 0})
        self.assertEqual(act["days"][(TODAY - timedelta(days=2)).isoformat()], {"applied": 0, "interviews": 1})
        self.assertEqual((act["total_applied"], act["total_interviews"]), (2, 1))

    def test_interview_day_is_in_the_persons_timezone(self):
        UserProfile.for_user(self.a)
        UserProfile.objects.filter(user=self.a).update(timezone="Asia/Dhaka")
        a = self.job()
        # 20:00 UTC on the 24th is 02:00 on the 25th in Dhaka
        Interview.objects.create(owner=self.a, application=a, scheduled_at=datetime(2026, 10, 24, 20, tzinfo=dt_timezone.utc))
        self.assertIn("2026-10-25", self.numbers()["activity"]["days"])


class Goals(Base):
    def test_off_by_default(self):
        self.job(applied_date=TODAY)
        self.assertIsNone(self.numbers()["goals"])

    def test_streaks(self):
        days = {TODAY - timedelta(days=n) for n in (0, 1, 2, 5, 6, 7, 8)}
        self.assertEqual(dashviz.streaks(days, TODAY), (3, 4))
        self.assertEqual(dashviz.streaks({TODAY - timedelta(days=1)}, TODAY), (1, 1))  # today is not over yet
        self.assertEqual(dashviz.streaks({TODAY - timedelta(days=2)}, TODAY), (0, 1))
        self.assertEqual(dashviz.streaks(set(), TODAY), (0, 0))

    def test_progress_and_month_line(self):
        preferences.update(UserProfile.for_user(self.a), {"goal_daily": 2, "goal_weekly": 5})
        self.job(applied_date=TODAY)
        self.job(applied_date=TODAY - timedelta(days=1))
        self.job(applied_date=TODAY - timedelta(days=9))
        g = self.numbers()["goals"]
        self.assertEqual((g["today"], g["week"], g["current_streak"], g["daily_target"], g["weekly_target"]), (1, 2, 2, 2, 5))
        self.assertEqual(g["month"]["applied"], 3)
        self.assertIn("October", g["month"]["text"])
        self.assertNotIn("miss", g["explain"].lower())

    def test_settings_are_validated(self):
        profile = UserProfile.for_user(self.a)
        for bad in ({"goal_daily": -1}, {"goal_daily": 51}, {"goal_weekly": "3"}, {"goal_weekly": True}, {"quiet_days": 2}, {"quiet_days": 31}, {"insights_period": "7"}):
            with self.assertRaises(preferences.PreferenceError, msg=bad):
                preferences.update(profile, bad)
        out = preferences.update(profile, {"quiet_days": 3, "goal_daily": 0, "insights_period": "all"})
        self.assertEqual((out["quiet_days"], out["insights_period"]), (3, "all"))
        self.assertEqual(preferences.normalize({"quiet_days": "x", "goal_daily": 999})["quiet_days"], 10)
        self.assertEqual(preferences.normalize({})["goal_daily"], 0)


class Calendar(Base):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.a)

    def test_month_has_every_kind_and_marks_today(self):
        a = self.job(deadline=date(2026, 10, 28), follow_up_date=date(2026, 10, 27))
        Interview.objects.create(owner=self.a, application=a, scheduled_at=aware(date(2026, 10, 26), 10))
        Offer.objects.create(owner=self.a, application=a, base=1, deadline=date(2026, 10, 30))
        self.job(deadline=date(2026, 11, 2))
        data = dashviz.month_view(self.a, date(2026, 10, 1), TODAY, timezone.get_current_timezone())
        kinds = {k: [i["kind"] for i in v] for k, v in data["days"].items()}
        self.assertEqual(kinds, {"2026-10-26": ["interview"], "2026-10-27": ["followup"], "2026-10-28": ["deadline"], "2026-10-30": ["offer"]})
        self.assertEqual((data["today"], data["weekday_of_first"], data["label"]), ("2026-10-25", 3, "October 2026"))
        self.assertEqual(len(data["week_ahead"]), 4)

    def test_api_and_bad_month(self):
        self.assertEqual(self.client.get("/api/v1/stats/calendar?month=2026-10").status_code, 200)
        for bad in ("2026-13", "oct", "1999-01", "2026-1"):
            self.assertEqual(self.client.get(f"/api/v1/stats/calendar?month={bad}").status_code, 400, bad)
        self.client.logout()
        self.assertEqual(self.client.get("/api/v1/stats/calendar").status_code, 401)

    def test_never_shows_someone_elses_dates(self):
        mine = self.job(deadline=date.today())
        theirs = self.job(owner=self.b, deadline=date.today())
        Interview.objects.create(owner=self.b, application=theirs, scheduled_at=timezone.now())
        data = self.client.get("/api/v1/stats/calendar").json()
        ids = {i["job_id"] for items in data["days"].values() for i in items} | {i["job_id"] for i in data["week_ahead"]}
        self.assertLessEqual(ids, {mine.pk})

    def test_terminal_jobs_are_left_out(self):
        self.job(status=Status.objects.get(name="Rejected"), deadline=date(2026, 10, 28), follow_up_date=date(2026, 10, 28))
        self.assertEqual(dashviz.month_view(self.a, date(2026, 10, 1), TODAY, timezone.get_current_timezone())["days"], {})


class Worth(Base):
    def test_order_caps_and_reasons(self):
        apps = []
        for n in range(4):
            a = self.job(company=f"Q{n}", applied_date=TODAY - timedelta(days=12 + n))
            apps.append(a)
        fresh = self.job(company="Fresh", applied_date=TODAY - timedelta(days=2))
        Offer.objects.create(owner=self.a, application=fresh, base=1, deadline=TODAY + timedelta(days=3))
        due = self.job(company="Due", follow_up_date=TODAY - timedelta(days=2), applied_date=TODAY - timedelta(days=20))
        coming = [{"kind": "interview", "date": TODAY.isoformat(), "when": aware(TODAY, 15).isoformat(), "label": "Phone screen", "company": "Zed", "role": "Dev", "job_id": 999}]
        rows = list(Application.objects.filter(owner=self.a).select_related("status").prefetch_related("interviews", "offers"))
        out = dashviz.worth_a_look(rows, [due], coming, [], 10, TODAY)
        self.assertEqual([i["kind"] for i in out], ["interview", "offer", "followup", "quiet", "quiet", "quiet"])
        self.assertEqual(len(out), 6)
        self.assertIn("today", out[0]["reason"])
        self.assertEqual(out[3]["label"], "Q3, Dev")  # quietest first (15 days), the follow-up job is not repeated as quiet
        self.assertEqual(dashviz.worth_a_look(rows, [due], coming, [], 14, TODAY)[3]["label"], "Q3, Dev")
        self.assertEqual([i["kind"] for i in dashviz.worth_a_look(rows, [], [], [], 30, TODAY)], ["offer"])

    def test_dashboard_carries_it_and_the_setting_applies(self):
        self.client.force_login(self.a)
        self.job(applied_date=timezone.localdate() - timedelta(days=11))
        self.assertEqual([i["kind"] for i in self.client.get("/api/v1/dashboard").json()["worth_a_look"]], ["quiet"])
        preferences.update(UserProfile.for_user(self.a), {"quiet_days": 12})
        self.assertEqual(self.client.get("/api/v1/dashboard").json()["worth_a_look"], [])

    def test_dashboard_never_lists_other_peoples_jobs(self):
        self.client.force_login(self.a)
        self.job(owner=self.b, applied_date=timezone.localdate() - timedelta(days=20))
        self.assertEqual(self.client.get("/api/v1/dashboard").json()["worth_a_look"], [])

    def test_no_queries_per_job(self):
        self.client.force_login(self.a)
        self.client.get("/api/v1/dashboard")

        def add(n):
            for i in range(n):
                a = self.job(company=f"C{i}-{Application.objects.count()}", applied_date=timezone.localdate() - timedelta(days=15))
                Interview.objects.create(owner=self.a, application=a, scheduled_at=timezone.now() + timedelta(days=1))
                Offer.objects.create(owner=self.a, application=a, base=1)

        add(3)
        self.client.get("/api/v1/dashboard")
        with CaptureQueriesContext(connection) as few:
            self.client.get("/api/v1/dashboard")
        add(20)
        with CaptureQueriesContext(connection) as many:
            self.client.get("/api/v1/dashboard")
        self.assertLessEqual(len(many), len(few) + 2)


class Cost(Base):
    def test_stats_stay_cheap(self):
        for i in range(40):
            a = self.job(role=f"R{i}", applied_date=TODAY - timedelta(days=i))
            Interview.objects.create(owner=self.a, application=a, scheduled_at=aware(TODAY))
        with CaptureQueriesContext(connection) as ctx:
            stats.candidate_stats(self.a, TODAY)
        self.assertLess(len(ctx), 30, len(ctx))
