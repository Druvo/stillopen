"""The candidate's own numbers: counted from their own jobs only, plain counts, nothing predicted."""
from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from tracker.models import Application, Insight, Interview, JobSource, Posting, PrepPlan, ScoreBand, SiteConfig, Status, UserProfile
from tracker.services import stats

User = get_user_model()
PW = "correct-horse-battery-staple"
TODAY = date(2026, 10, 25)


def person(name):
    return User.objects.create_user(name, email=f"{name}@example.com", password=PW)


def aware(day, hour=12):
    return timezone.make_aware(datetime(day.year, day.month, day.day, hour))


class Counts(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        self.evaluated = Status.objects.get(name="Evaluated")
        self.applied = Status.objects.get(name="Applied")
        self.top = ScoreBand.objects.order_by("-min_percent").first()

    def job(self, owner=None, **kw):
        fields = {"owner": owner or self.a, "company": "Acme", "role": "Dev", "status": self.evaluated, "found_date": TODAY}
        fields.update(kw)
        return Application.objects.create(**fields)

    def test_nothing_yet_is_all_zero_and_says_so(self):
        data = stats.candidate_stats(self.a, TODAY)
        self.assertFalse(data["has_jobs"])
        self.assertEqual(data["week"]["found"], 0)
        self.assertIsNone(data["match"]["average"])
        self.assertIsNone(data["applied"]["reply_rate"])
        self.assertEqual(data["sources"], [])
        self.assertEqual(len(data["weekly"]), 8)

    def test_this_week_counts_the_last_seven_days_including_today(self):
        self.job(found_date=TODAY)
        self.job(found_date=TODAY - timedelta(days=6))
        self.job(found_date=TODAY - timedelta(days=7))  # one day too old
        self.job(ai_evaluated_at=aware(TODAY - timedelta(days=2)), found_date=TODAY - timedelta(days=30))
        self.job(applied_date=TODAY - timedelta(days=1), status=self.applied, found_date=TODAY - timedelta(days=30))
        week = stats.candidate_stats(self.a, TODAY)["week"]
        self.assertEqual((week["found"], week["checked"], week["applied"]), (2, 1, 1))

    def test_deadlines_follow_ups_went_cold_and_interviews(self):
        cfg = SiteConfig.for_user(self.a)
        self.job(deadline=TODAY + timedelta(days=cfg.urgent_days))
        self.job(deadline=TODAY + timedelta(days=cfg.urgent_days + 5))
        self.job(deadline=TODAY - timedelta(days=1))  # already past: not "closing soon"
        due = self.job(applied_date=TODAY - timedelta(days=9), status=self.applied, follow_up_date=TODAY)
        self.job(live_state="expired", live_checked_at=aware(TODAY - timedelta(days=1)))
        self.job(live_state="expired", live_checked_at=aware(TODAY - timedelta(days=20)))
        Interview.objects.create(owner=self.a, application=due, scheduled_at=timezone.now() + timedelta(days=3), kind="phone")
        Interview.objects.create(owner=self.a, application=due, scheduled_at=timezone.now() + timedelta(days=40), kind="phone")
        week = stats.candidate_stats(self.a, TODAY)["week"]
        self.assertEqual((week["closing_soon"], week["followups_due"], week["went_cold"], week["interviews_soon"]), (1, 1, 1, 1))

    def test_weekly_windows_end_today_and_split_the_activity(self):
        self.job(found_date=TODAY)
        self.job(found_date=TODAY - timedelta(days=8))
        self.job(applied_date=TODAY - timedelta(days=15), status=self.applied, found_date=TODAY - timedelta(days=60))
        weekly = stats.candidate_stats(self.a, TODAY)["weekly"]
        self.assertEqual(weekly[-1]["start"], (TODAY - timedelta(days=6)).isoformat())
        self.assertEqual([w["found"] for w in weekly[-3:]], [0, 1, 1])
        self.assertEqual(weekly[-3]["applied"], 1)

    def test_match_bands_averages_and_the_share_of_strong_matches_among_applications(self):
        scale = SiteConfig.for_user(self.a).score_scale
        strong = self.job(score=scale * 0.9, applied_date=TODAY, status=self.applied)
        self.job(score=scale * 0.3, applied_date=TODAY, status=self.applied)
        self.job(score=scale * 0.6)
        self.job()  # not checked yet
        match = stats.candidate_stats(self.a, TODAY)["match"]
        self.assertEqual(match["not_checked"], 1)
        self.assertEqual(sum(b["count"] for b in match["bands"]) + match["not_checked"], 4)
        self.assertEqual(match["average"], round((90 + 30 + 60) / 3))
        self.assertEqual(match["average_applied"], 60)
        self.assertEqual(match["strong_share_applied"], 50 if strong.match_percent(scale) >= self.top.min_percent else 0)
        self.assertEqual(match["top_band"], self.top.label)

    def test_replies_waiting_and_how_long(self):
        replied = self.job(applied_date=TODAY - timedelta(days=20), status=self.applied)
        Interview.objects.create(owner=self.a, application=replied, scheduled_at=timezone.now() + timedelta(days=2), kind="phone")
        old = self.job(company="Slow Co", applied_date=TODAY - timedelta(days=30), status=self.applied)
        self.job(applied_date=TODAY - timedelta(days=10), status=self.applied)
        self.job(applied_date=TODAY - timedelta(days=2), status=self.applied)  # too recent to count as "waiting longest"
        data = stats.candidate_stats(self.a, TODAY)
        self.assertEqual(data["applied"], {"count": 4, "reply_rate": 25})
        self.assertEqual(data["waiting"]["count"], 3)
        self.assertEqual(data["waiting"]["median_days"], 10)
        self.assertEqual([r["days"] for r in data["waiting"]["longest"]], [30, 10])
        self.assertEqual(data["waiting"]["longest"][0]["id"], old.pk)

    def test_where_jobs_come_from_and_what_they_lead_to(self):
        source = JobSource.objects.create(name="Acme Careers", connector="greenhouse", board_token="acme", enabled=True)
        posting = Posting.objects.create(source=source, url="https://x.example/1", title="Dev", company="Acme", title_key="dev")
        self.job(posting=posting)
        applied = self.job(posting=posting, applied_date=TODAY, status=self.applied)
        Interview.objects.create(owner=self.a, application=applied, scheduled_at=timezone.now() + timedelta(days=2), kind="phone")
        self.job()
        rows = {r["label"]: r for r in stats.candidate_stats(self.a, TODAY)["sources"]}
        self.assertEqual(rows["Acme Careers"], {"label": "Acme Careers", "found": 2, "applied": 1, "interviews": 1})
        self.assertEqual(rows["Added by you"]["found"], 1)

    def test_work_kinds_and_countries(self):
        self.job(arrangement="remote", country="MY")
        self.job(arrangement="remote", country="MY")
        self.job(arrangement="hybrid", country="BD")
        self.job()
        data = stats.candidate_stats(self.a, TODAY)
        self.assertEqual({w["kind"]: w["count"] for w in data["work"]}, {"remote": 2, "hybrid": 1, "unknown": 1})
        self.assertEqual(data["countries"][0], {"name": "Malaysia", "count": 2})

    def test_skills_that_keep_coming_up_need_at_least_two_jobs(self):
        for i in range(3):
            app = self.job()
            Insight.objects.create(application=app, kind="gap", text="Your CV doesn't mention: Kubernetes")
            Insight.objects.create(application=app, kind="strength", text="Python")
        other = self.job()
        Insight.objects.create(application=other, kind="gap", text="Your CV doesn't mention: Terraform")
        Insight.objects.create(application=other, kind="gap", text="Seems to want someone on call at night")  # free text: not counted
        skills = stats.candidate_stats(self.a, TODAY)["skills"]
        self.assertEqual(skills["gaps"], [{"term": "kubernetes", "jobs": 3}])
        self.assertEqual(skills["strengths"], [{"term": "python", "jobs": 3}])

    def test_the_market_counts_postings_that_match_the_roles_this_week_and_last(self):
        UserProfile.objects.filter(user=self.a).update(target_roles="Backend Engineer")
        source = JobSource.objects.create(name="Board", connector="greenhouse", board_token="b", enabled=True)
        now = timezone.now()
        for i, (title, age) in enumerate([("Senior Backend Engineer", 1), ("Backend Developer", 3), ("Backend Engineer", 9), ("Chef", 2)]):
            posting = Posting.objects.create(source=source, url=f"https://x.example/{i}", title=title, company="Acme", title_key=f"k{i}")
            Posting.objects.filter(pk=posting.pk).update(first_seen_at=now - timedelta(days=age))
        market = stats.candidate_stats(self.a, TODAY)["market"]
        self.assertEqual((market["this_week"], market["last_week"], market["roles"]), (2, 1, ["Backend Engineer"]))

    def test_the_market_is_absent_when_the_person_has_named_no_role(self):
        self.assertIsNone(stats.candidate_stats(self.a, TODAY)["market"])

    def test_prep_progress_only_when_prep_is_on(self):
        self.assertEqual(stats.candidate_stats(self.a, TODAY)["prep"], {"active_plans": 0, "lessons_done": 0, "lessons_total": 0, "streak": 0})
        SiteConfig.objects.update(prep_enabled=False)
        self.assertIsNone(stats.candidate_stats(self.a, TODAY)["prep"])

    def test_nobody_elses_jobs_are_ever_counted(self):
        self.job(owner=self.b, found_date=TODAY, applied_date=TODAY, status=self.applied, company="SecretCo", arrangement="remote", country="BD")
        Insight.objects.create(application=self.job(owner=self.b), kind="gap", text="Your CV doesn't mention: Secret")
        data = stats.candidate_stats(self.a, TODAY)
        self.assertFalse(data["has_jobs"])
        self.assertEqual((data["week"]["found"], data["applied"]["count"], data["work"], data["countries"], data["skills"]), (0, 0, [], [], {"gaps": [], "strengths": []}))
        self.assertNotIn("SecretCo", str(data))


class StatsEndpoint(TestCase):
    def setUp(self):
        cache.clear()
        self.a = person("alice")
        self.client.force_login(self.a)

    def test_it_answers_with_every_section(self):
        data = self.client.get("/api/v1/stats").json()
        for key in ("as_of", "has_jobs", "week", "weekly", "match", "applied", "sources", "work", "countries", "waiting", "skills", "prep", "market"):
            self.assertIn(key, data)

    def test_signed_out_is_refused(self):
        self.client.logout()
        self.assertEqual(self.client.get("/api/v1/stats").status_code, 401)

    def test_it_is_cheap_however_many_jobs_there_are(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        status = Status.objects.get(name="Evaluated")
        for i in range(60):
            app = Application.objects.create(owner=self.a, company="Acme", role=f"R{i}", status=status, found_date=timezone.localdate())
            Insight.objects.create(application=app, kind="gap", text="Your CV doesn't mention: Kubernetes")
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.client.get("/api/v1/stats").status_code, 200)
        self.assertLess(len(ctx), 30, len(ctx))
