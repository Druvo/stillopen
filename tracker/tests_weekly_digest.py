"""The weekly digest email: off by default at two levels (site-wide, then per-person), one plain summary a week."""
import json
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from tracker.models import Interview, Offer, SiteConfig, UserProfile
from tracker.services import pipeline
from tracker.tests_apply import job, person
from tracker.tests_cv import PW

User = get_user_model()


class WeeklyCounts(TestCase):
    def setUp(self):
        self.u = person("jane")

    def test_counts_only_the_given_week(self):
        monday = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
        sunday = monday + timedelta(days=6)
        last_week = monday - timedelta(days=1)
        in_week = job(self.u, company="A", applied_date=monday)
        job(self.u, company="B", applied_date=last_week)  # outside the window
        Interview.objects.create(owner=self.u, application=in_week, scheduled_at=timezone.make_aware(timezone.datetime(monday.year, monday.month, monday.day, 10)))
        Offer.objects.create(owner=self.u, application=in_week, base=Decimal("1"), currency="USD")
        counts = pipeline.weekly_counts(self.u, monday, sunday)
        self.assertEqual((counts["applied"], counts["interviews"], counts["offers"]), (1, 1, 1))

    def test_due_now_is_a_current_count_not_week_bounded(self):
        app = job(self.u, follow_up_date=timezone.localdate() - timedelta(days=3))
        app.status.is_terminal = False
        app.status.save()
        monday = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
        counts = pipeline.weekly_counts(self.u, monday, monday + timedelta(days=6))
        self.assertEqual(counts["due_now"], 1)


class SendWeeklyDigest(TestCase):
    def setUp(self):
        from allauth.account.models import EmailAddress

        self.u = person("jane")
        EmailAddress.objects.create(user=self.u, email=self.u.email, verified=True, primary=True)

    def test_nothing_sent_when_nothing_happened_and_nothing_due(self):
        self.assertFalse(pipeline.send_weekly_digest(self.u))
        self.assertEqual(mail.outbox, [])

    def test_sends_a_plain_summary_when_something_happened(self):
        job(self.u, applied_date=timezone.localdate())
        self.assertTrue(pipeline.send_weekly_digest(self.u))
        self.assertEqual(mail.outbox[0].to, [self.u.email])
        self.assertIn("1 application", mail.outbox[0].body)

    def test_nothing_sent_without_a_verified_address(self):
        from allauth.account.models import EmailAddress

        EmailAddress.objects.filter(user=self.u).update(verified=False)
        job(self.u, applied_date=timezone.localdate())
        self.assertFalse(pipeline.send_weekly_digest(self.u))


class WeeklyDigestCommand(TestCase):
    def setUp(self):
        from allauth.account.models import EmailAddress

        self.EmailAddress = EmailAddress

    def person(self, name, digest=True, verified=True):
        u = User.objects.create_user(name, email=f"{name}@example.com", password=PW)
        UserProfile.objects.filter(user=u).update(weekly_digest_enabled=digest)
        if verified:
            self.EmailAddress.objects.create(user=u, email=u.email, verified=True, primary=True)
        return u

    def run_cmd(self, **kw):
        SiteConfig.objects.filter(pk=1).update(weekly_digest_site_enabled=True)
        call_command("send_weekly_digest", stdout=mock.MagicMock(), **kw)
        return mail.outbox

    def test_off_by_default_sends_nothing(self):
        ann = self.person("ann")
        job(ann, applied_date=timezone.localdate())
        call_command("send_weekly_digest", stdout=mock.MagicMock())
        self.assertEqual(mail.outbox, [])

    def test_emails_only_people_who_opted_in(self):
        ann, bob = self.person("ann"), self.person("bob", digest=False)
        job(ann, applied_date=timezone.localdate())
        job(bob, applied_date=timezone.localdate())
        outbox = self.run_cmd()
        self.assertEqual(len(outbox), 1)
        self.assertEqual(outbox[0].to, [ann.email])

    def test_a_second_run_the_same_week_sends_nothing_more(self):
        ann = self.person("ann")
        job(ann, applied_date=timezone.localdate())
        self.run_cmd()
        self.run_cmd()
        self.assertEqual(len(mail.outbox), 1)

    def test_the_choice_is_saved_from_the_profile(self):
        u = self.person("ann", digest=False)
        UserProfile.objects.filter(user=u).update(onboarding_done=True, target_roles="Backend Engineer")
        self.client.login(username="ann", password=PW)
        self.assertFalse(self.client.get("/api/v1/profile").json()["profile"]["weekly_digest_enabled"])
        r = self.client.put("/api/v1/profile", data=json.dumps({"target_roles": "Backend Engineer", "weekly_digest_enabled": True}), content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(UserProfile.objects.get(user=u).weekly_digest_enabled)
