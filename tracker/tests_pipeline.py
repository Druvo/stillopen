"""Interviews, contacts and referrals, offers: behaviour, validation, strict per-person isolation."""
import io
import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tracker.models import Contact, Interview, Offer, Referral, SiteConfig
from tracker.services import pipeline
from tracker.tests_apply import job, person
from tracker.tests_cv import PW
from tracker.services.pipeline import comparison

User = get_user_model()


def call(client, method, path, body=None):
    """A call to the app's JSON API."""
    if method in ("get", "delete"):
        return getattr(client, method)(f"/api/v1{path}")
    return getattr(client, method)(f"/api/v1{path}", data=json.dumps(body or {}), content_type="application/json")


def when(days=2):
    return (timezone.localtime() + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")


class InterviewTests(TestCase):
    """The screens run on the JSON API (full rules in tests_api_pipeline); these pin what the API must keep doing."""

    def setUp(self):
        self.u = person("jane")
        self.app = job(self.u)
        self.client.login(username="jane", password=PW)

    def add(self, **kw):
        data = {"application": self.app.pk, "scheduled_at": when(), "kind": "video", "where": "https://meet.example.com/x", "notes": "Ask about the team"}
        data.update(kw)
        return call(self.client, "post", "/interviews", data)

    def test_add_logs_an_event_and_is_coming_up(self):
        self.add()
        self.assertEqual(Interview.objects.filter(owner=self.u).count(), 1)
        self.assertTrue(self.app.events.filter(kind="interview", text__contains="scheduled").exists())
        self.assertEqual(len(call(self.client, "get", "/dashboard").json()["upcoming_interviews"]), 1)

    def test_cancelled_or_past_do_not_show_as_coming_up(self):
        self.add()
        Interview.objects.update(outcome="cancelled")
        self.assertEqual(call(self.client, "get", "/dashboard").json()["upcoming_interviews"], [])

    def test_bad_date_is_refused_and_an_unknown_outcome_changes_nothing(self):
        self.add(scheduled_at="soon")
        self.assertEqual(Interview.objects.count(), 0)
        self.add()
        i = Interview.objects.get()
        call(self.client, "post", f"/interviews/{i.pk}/outcome", {"outcome": "passed"})
        call(self.client, "post", f"/interviews/{i.pk}/outcome", {"outcome": "bogus"})
        i.refresh_from_db()
        self.assertEqual(i.outcome, "passed")

    @override_settings(STILLOPEN_MAX_PIPELINE=1)
    def test_cap(self):
        self.add()
        self.add()
        self.assertEqual(Interview.objects.count(), 1)


class ContactTests(TestCase):
    def setUp(self):
        self.u = person("jane")
        self.app = job(self.u)
        self.client.login(username="jane", password=PW)

    def test_contact_then_referral_flow(self):
        call(self.client, "post", "/contacts", {"name": "Sam Lee", "company": "Globex", "link": "https://example.com/sam"})
        c = Contact.objects.get()
        call(self.client, "post", "/referrals", {"contact": c.pk, "application": self.app.pk, "status": "asked", "note": "Coffee on Friday"})
        r = Referral.objects.get()
        self.assertEqual((r.owner, r.status), (self.u, "asked"))
        call(self.client, "post", f"/referrals/{r.pk}/status", {"status": "agreed"})
        r.refresh_from_db()
        self.assertEqual(r.status, "agreed")
        self.assertTrue(self.app.events.filter(text__contains="Sam Lee").exists())

    def test_javascript_links_are_refused(self):
        call(self.client, "post", "/contacts", {"name": "Eve", "link": "javascript:alert(1)"})
        self.assertEqual(Contact.objects.count(), 0)

    def test_deleting_a_contact_removes_their_referrals(self):
        c = Contact.objects.create(owner=self.u, name="Sam")
        Referral.objects.create(owner=self.u, contact=c, application=self.app)
        self.client.delete(f"/api/v1/contacts/{c.pk}")
        self.assertEqual(Referral.objects.count(), 0)


class OfferTests(TestCase):
    def setUp(self):
        self.u = person("jane")
        self.a, self.b = job(self.u, company="Acme"), job(self.u, company="Globex")
        self.client.login(username="jane", password=PW)

    def offer(self, app, **kw):
        fields = {"owner": self.u, "application": app, "base": Decimal("100000"), "currency": "USD"}
        fields.update(kw)
        return Offer.objects.create(**fields)

    def test_totals(self):
        o = self.offer(self.a, base=Decimal("5000"), period="month", bonus=Decimal("6000"), equity=Decimal("10000"), other_benefits=Decimal("2000"), signing=Decimal("3000"))
        self.assertEqual(o.yearly_base, Decimal("60000"))
        self.assertEqual(o.yearly_total, Decimal("78000"))
        self.assertEqual(o.first_year_total, Decimal("81000"))

    def test_comparison_groups_by_currency_ranks_and_drops_declined(self):
        hi = self.offer(self.a, base=Decimal("120000"))
        lo = self.offer(self.b, base=Decimal("100000"))
        self.offer(self.b, base=Decimal("999999"), status="declined")
        other = self.offer(self.a, base=Decimal("9000000"), currency="BDT")
        groups = comparison([hi, lo, other])
        self.assertEqual([g["currency"] for g in groups], ["BDT", "USD"])
        usd = groups[1]["rows"]
        self.assertEqual([r["offer"] for r in usd], [hi, lo])
        self.assertTrue(usd[0]["best"])
        self.assertEqual(usd[1]["behind"], Decimal("20000"))
        self.assertFalse(groups[0]["rows"][0]["best"])  # alone in its currency: nothing to beat

    def test_form_normalises_currency_and_rejects_nonsense(self):
        base = {"application": self.a.pk, "base": "50000", "period": "year", "bonus": "0", "equity": "0", "other_benefits": "0", "signing": "0"}
        call(self.client, "post", "/offers", {**base, "currency": "myr"})
        self.assertEqual(Offer.objects.get().currency, "MYR")
        call(self.client, "post", "/offers", {**base, "currency": "dollars"})
        call(self.client, "post", "/offers", {**base, "currency": "USD", "base": "-5"})
        self.assertEqual(Offer.objects.count(), 1)

    def test_the_offers_screen_compares_per_currency(self):
        self.offer(self.a, base=Decimal("120000"))
        self.offer(self.b, base=Decimal("100000"))
        groups = call(self.client, "get", "/offers").json()["groups"]
        self.assertEqual([g["currency"] for g in groups], ["USD"])
        self.assertTrue(groups[0]["rows"][0]["best"])

    def test_status_update(self):
        o = self.offer(self.a)
        call(self.client, "post", f"/offers/{o.pk}/status", {"status": "accepted"})
        o.refresh_from_db()
        self.assertEqual(o.status, "accepted")


class PipelineIsolation(TestCase):
    def setUp(self):
        self.a, self.b = person("alice"), person("bob")
        self.aapp, self.bapp = job(self.a), job(self.b, company="Initech")
        self.iv = Interview.objects.create(owner=self.a, application=self.aapp, scheduled_at=timezone.now() + timedelta(days=1))
        self.contact = Contact.objects.create(owner=self.a, name="Alice's friend")
        self.ref = Referral.objects.create(owner=self.a, contact=self.contact, application=self.aapp)
        self.offer = Offer.objects.create(owner=self.a, application=self.aapp, base=Decimal("1"), currency="USD")
        self.client.login(username="bob", password=PW)

    def test_other_person_cannot_act_on_any_row(self):
        self.assertEqual(self.client.delete(f"/api/v1/interviews/{self.iv.pk}").status_code, 404)
        self.assertEqual(call(self.client, "post", f"/interviews/{self.iv.pk}/outcome", {"outcome": "passed"}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/v1/contacts/{self.contact.pk}").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/v1/referrals/{self.ref.pk}").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/v1/offers/{self.offer.pk}").status_code, 404)
        self.assertEqual(call(self.client, "post", f"/offers/{self.offer.pk}/status", {"status": "accepted"}).status_code, 404)
        for model in (Interview, Contact, Referral, Offer):
            self.assertEqual(model.objects.filter(owner=self.a).count(), 1)

    def test_lists_show_only_my_rows(self):
        self.assertNotIn("Alice's friend", json.dumps(call(self.client, "get", "/contacts").json()))
        self.assertNotIn("Globex", json.dumps(call(self.client, "get", "/interviews").json()))
        self.assertNotIn("Globex", json.dumps(call(self.client, "get", "/offers").json()))

    def test_cannot_attach_to_someone_elses_job_or_contact(self):
        call(self.client, "post", "/interviews", {"application": self.aapp.pk, "scheduled_at": when(), "kind": "video"})
        call(self.client, "post", "/offers", {"application": self.aapp.pk, "base": "1", "period": "year", "currency": "USD", "bonus": "0", "equity": "0", "other_benefits": "0", "signing": "0"})
        mine = Contact.objects.create(owner=self.b, name="Bobs friend")
        call(self.client, "post", "/referrals", {"contact": self.contact.pk, "application": self.bapp.pk, "status": "asked"})
        call(self.client, "post", "/referrals", {"contact": mine.pk, "application": self.aapp.pk, "status": "asked"})
        self.assertEqual(Interview.objects.filter(owner=self.b).count(), 0)
        self.assertEqual(Offer.objects.filter(owner=self.b).count(), 0)
        self.assertEqual(Referral.objects.filter(owner=self.b).count(), 0)

    def test_export_has_only_my_data_and_account_delete_cascades(self):
        self.client.force_login(self.a)
        data = json.loads(self.client.get(reverse("export_data")).content)
        self.assertEqual(len(data["interviews"]), 1)
        self.assertEqual(data["contacts"][0]["referrals"][0]["status"], "thinking")
        self.assertEqual(data["offers"][0]["currency"], "USD")
        self.a.delete()
        for model in (Interview, Contact, Referral, Offer):
            self.assertEqual(model.objects.count(), 0)


class ReminderTests(TestCase):
    def setUp(self):
        from allauth.account.models import EmailAddress

        self.u = person("jane")
        EmailAddress.objects.create(user=self.u, email=self.u.email, verified=True, primary=True)
        self.app = job(self.u)
        SiteConfig.objects.filter(pk=1).update(followup_emails_enabled=True)

    def interview(self, hours, **kw):
        return Interview.objects.create(owner=self.u, application=self.app, scheduled_at=timezone.now() + timedelta(hours=hours), **kw)

    def run_cmd(self):
        from django.core.management import call_command

        call_command("send_interview_reminders", stdout=io.StringIO())
        return mail.outbox

    def test_soon_interview_gets_one_email_only_once(self):
        i = self.interview(5, where="Room 4", notes="Bring laptop")
        outbox = self.run_cmd()
        self.assertEqual(len(outbox), 1)
        self.assertIn("Room 4", outbox[0].body)
        self.assertIn("Bring laptop", outbox[0].body)
        i.refresh_from_db()
        self.assertIsNotNone(i.reminded_at)
        self.run_cmd()
        self.assertEqual(len(mail.outbox), 1)

    def test_far_past_and_cancelled_get_nothing(self):
        self.interview(72)
        self.interview(-3)
        self.interview(5, outcome="cancelled")
        self.assertEqual(self.run_cmd(), [])

    def test_off_switch_and_unverified_address(self):
        self.interview(5)
        SiteConfig.objects.filter(pk=1).update(followup_emails_enabled=False)
        self.assertEqual(self.run_cmd(), [])
        SiteConfig.objects.filter(pk=1).update(followup_emails_enabled=True)
        from allauth.account.models import EmailAddress

        EmailAddress.objects.update(verified=False)
        self.assertEqual(self.run_cmd(), [])
        self.assertIsNone(Interview.objects.get().reminded_at)

    def test_never_emails_someone_about_another_persons_interview(self):
        from allauth.account.models import EmailAddress

        bob = person("bob")
        EmailAddress.objects.create(user=bob, email=bob.email, verified=True, primary=True)
        self.interview(5)
        outbox = self.run_cmd()
        self.assertEqual([m.to for m in outbox], [[self.u.email]])


class InsightsTests(TestCase):
    def setUp(self):
        self.u = person("jane")
        self.client.login(username="jane", password=PW)

    def test_nothing_tracked_gives_zeros(self):
        data = call(self.client, "get", "/insights").json()
        self.assertEqual((data["tracked"], data["applied"]), (0, 0))

    def test_funnel_counts_and_median(self):
        today = timezone.localdate()
        a = job(self.u, company="A", applied_date=today - timedelta(days=10), applied_channel="site")
        b = job(self.u, company="B", applied_date=today - timedelta(days=4), applied_channel="site")
        job(self.u, company="C", applied_date=today - timedelta(days=2), applied_channel="referral")
        job(self.u, company="Unapplied")
        Interview.objects.create(owner=self.u, application=a, scheduled_at=timezone.now() - timedelta(days=4))  # 6 days after applying
        Interview.objects.create(owner=self.u, application=b, scheduled_at=timezone.now())  # 4 days after
        Offer.objects.create(owner=self.u, application=a, base=Decimal("1"), currency="USD")
        f = pipeline.funnel(self.u)
        self.assertEqual((f["tracked"], f["applied"], f["interviewed"], f["offered"]), (4, 3, 2, 1))
        self.assertEqual(f["interview_rate"], 67)
        self.assertEqual(f["median_days_to_interview"], 5)
        site = next(r for r in f["channels"] if r["label"] == "Company site or job board")
        self.assertEqual((site["applied"], site["interviews"], site["offers"]), (2, 2, 1))
        self.assertEqual(call(self.client, "get", "/insights").json()["interviewed"], 2)

    def test_only_my_numbers(self):
        bob = person("bob")
        job(bob, applied_date=timezone.localdate())
        self.assertEqual(pipeline.funnel(self.u)["applied"], 0)

    def test_by_score_groups_by_match_band_and_counts_interviews(self):
        today = timezone.localdate()
        strong = job(self.u, company="A", applied_date=today, score=4.5)  # 90%, Strong
        job(self.u, company="B", applied_date=today, score=4.5)  # 90%, Strong, no interview
        stretch = job(self.u, company="C", applied_date=today, score=1.0)  # 20%, A stretch
        job(self.u, company="D", applied_date=today)  # never scored
        Interview.objects.create(owner=self.u, application=strong, scheduled_at=timezone.now())
        Interview.objects.create(owner=self.u, application=stretch, scheduled_at=timezone.now())
        rows = pipeline.funnel(self.u)["by_score"]
        self.assertEqual([r["label"] for r in rows], ["Strong", "A stretch", "Not scored"])
        strong_row = rows[0]
        self.assertEqual((strong_row["applied"], strong_row["interviews"], strong_row["interview_rate"]), (2, 1, 50))
        stretch_row = rows[1]
        self.assertEqual((stretch_row["applied"], stretch_row["interviews"], stretch_row["interview_rate"]), (1, 1, 100))
        self.assertEqual(rows[2]["applied"], 1)

    def test_by_score_empty_when_nothing_applied(self):
        self.assertEqual(pipeline.funnel(self.u)["by_score"], [])
