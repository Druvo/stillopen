"""Interviews, contacts and referrals, offers: behaviour, validation, strict per-person isolation."""
import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tracker.models import Contact, Interview, Offer, Referral
from tracker.tests_apply import job, person
from tracker.tests_cv import PW
from tracker.views_pipeline import comparison

User = get_user_model()


def when(days=2):
    return (timezone.localtime() + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")


class InterviewTests(TestCase):
    def setUp(self):
        self.u = person("jane")
        self.app = job(self.u)
        self.client.login(username="jane", password=PW)

    def add(self, **kw):
        data = {"application": self.app.pk, "scheduled_at": when(), "kind": "video", "where": "https://meet.example.com/x", "notes": "Ask about the team"}
        data.update(kw)
        return self.client.post(reverse("interviews"), data)

    def test_add_logs_an_event_and_shows_on_the_dashboard(self):
        self.add()
        self.assertEqual(Interview.objects.filter(owner=self.u).count(), 1)
        self.assertTrue(self.app.events.filter(kind="interview", text__contains="scheduled").exists())
        self.assertContains(self.client.get(reverse("dashboard")), "Coming up")
        self.assertContains(self.client.get(reverse("interviews")), "Ask about the team")

    def test_bad_date_is_refused(self):
        self.add(scheduled_at="soon")
        self.assertEqual(Interview.objects.count(), 0)

    def test_outcome_and_delete(self):
        self.add()
        i = Interview.objects.get()
        self.client.post(reverse("interview_action", args=[i.pk, "outcome"]), {"outcome": "passed"})
        i.refresh_from_db()
        self.assertEqual(i.outcome, "passed")
        self.client.post(reverse("interview_action", args=[i.pk, "outcome"]), {"outcome": "bogus"})
        i.refresh_from_db()
        self.assertEqual(i.outcome, "passed")
        self.client.post(reverse("interview_action", args=[i.pk, "delete"]))
        self.assertEqual(Interview.objects.count(), 0)

    def test_cancelled_or_past_do_not_show_as_coming_up(self):
        self.add()
        Interview.objects.update(outcome="cancelled")
        self.assertNotContains(self.client.get(reverse("dashboard")), "Coming up")

    def test_get_on_actions_is_not_allowed(self):
        self.add()
        i = Interview.objects.get()
        self.assertEqual(self.client.get(reverse("interview_action", args=[i.pk, "delete"])).status_code, 405)

    def test_unknown_action_is_404(self):
        self.add()
        i = Interview.objects.get()
        self.assertEqual(self.client.post(reverse("interview_action", args=[i.pk, "explode"])).status_code, 404)

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
        self.client.post(reverse("contacts"), {"which": "contact", "name": "Sam Lee", "company": "Globex", "link": "https://example.com/sam"})
        c = Contact.objects.get()
        self.client.post(reverse("contacts"), {"which": "referral", "contact": c.pk, "application": self.app.pk, "status": "asked", "note": "Coffee on Friday"})
        r = Referral.objects.get()
        self.assertEqual((r.owner, r.status), (self.u, "asked"))
        page = self.client.get(reverse("contacts"))
        self.assertContains(page, "Sam Lee")
        self.assertContains(page, "Coffee on Friday")
        self.client.post(reverse("referral_action", args=[r.pk, "status"]), {"status": "agreed"})
        r.refresh_from_db()
        self.assertEqual(r.status, "agreed")
        self.assertTrue(self.app.events.filter(text__contains="Sam Lee").exists())

    def test_javascript_links_are_refused(self):
        self.client.post(reverse("contacts"), {"which": "contact", "name": "Eve", "link": "javascript:alert(1)"})
        self.assertEqual(Contact.objects.count(), 0)

    def test_deleting_a_contact_removes_their_referrals(self):
        c = Contact.objects.create(owner=self.u, name="Sam")
        Referral.objects.create(owner=self.u, contact=c, application=self.app)
        self.client.post(reverse("contact_delete", args=[c.pk]))
        self.assertEqual(Referral.objects.count(), 0)

    def test_contact_html_is_escaped(self):
        Contact.objects.create(owner=self.u, name="<script>alert(1)</script>")
        self.assertNotContains(self.client.get(reverse("contacts")), "<script>alert(1)</script>")


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
        self.client.post(reverse("offers"), {**base, "currency": "myr"})
        self.assertEqual(Offer.objects.get().currency, "MYR")
        self.client.post(reverse("offers"), {**base, "currency": "dollars"})
        self.client.post(reverse("offers"), {**base, "currency": "USD", "base": "-5"})
        self.assertEqual(Offer.objects.count(), 1)

    def test_page_renders_comparison(self):
        self.offer(self.a, base=Decimal("120000"))
        self.offer(self.b, base=Decimal("100000"))
        page = self.client.get(reverse("offers"))
        self.assertContains(page, "In USD")
        self.assertContains(page, "highest")
        self.assertContains(page, "20,000 less")

    def test_status_update(self):
        o = self.offer(self.a)
        self.client.post(reverse("offer_action", args=[o.pk, "status"]), {"status": "accepted"})
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
        post = self.client.post
        self.assertEqual(post(reverse("interview_action", args=[self.iv.pk, "delete"])).status_code, 404)
        self.assertEqual(post(reverse("interview_action", args=[self.iv.pk, "outcome"]), {"outcome": "passed"}).status_code, 404)
        self.assertEqual(post(reverse("contact_delete", args=[self.contact.pk])).status_code, 404)
        self.assertEqual(post(reverse("referral_action", args=[self.ref.pk, "delete"])).status_code, 404)
        self.assertEqual(post(reverse("offer_action", args=[self.offer.pk, "delete"])).status_code, 404)
        self.assertEqual(post(reverse("offer_action", args=[self.offer.pk, "status"]), {"status": "accepted"}).status_code, 404)
        for model in (Interview, Contact, Referral, Offer):
            self.assertEqual(model.objects.filter(owner=self.a).count(), 1)

    def test_lists_show_only_my_rows(self):
        self.assertNotContains(self.client.get(reverse("contacts")), "Alice's friend")
        self.assertNotContains(self.client.get(reverse("interviews")), "Globex")
        self.assertNotContains(self.client.get(reverse("offers")), "Globex")

    def test_cannot_attach_to_someone_elses_job_or_contact(self):
        post = self.client.post
        post(reverse("interviews"), {"application": self.aapp.pk, "scheduled_at": when(), "kind": "video"})
        post(reverse("offers"), {"application": self.aapp.pk, "base": "1", "period": "year", "currency": "USD", "bonus": "0", "equity": "0", "other_benefits": "0", "signing": "0"})
        mine = Contact.objects.create(owner=self.b, name="Bobs friend")
        post(reverse("contacts"), {"which": "referral", "contact": self.contact.pk, "application": self.bapp.pk, "status": "asked"})
        post(reverse("contacts"), {"which": "referral", "contact": mine.pk, "application": self.aapp.pk, "status": "asked"})
        self.assertEqual(Interview.objects.filter(owner=self.b).count(), 0)
        self.assertEqual(Offer.objects.filter(owner=self.b).count(), 0)
        self.assertEqual(Referral.objects.filter(owner=self.b).count(), 0)

    def test_login_required(self):
        self.client.logout()
        for name in ("interviews", "contacts", "offers"):
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 302)
            self.assertIn("/accounts/login/", r["Location"])

    def test_export_has_only_my_data_and_account_delete_cascades(self):
        self.client.force_login(self.a)
        data = json.loads(self.client.get(reverse("export_data")).content)
        self.assertEqual(len(data["interviews"]), 1)
        self.assertEqual(data["contacts"][0]["referrals"][0]["status"], "thinking")
        self.assertEqual(data["offers"][0]["currency"], "USD")
        self.a.delete()
        for model in (Interview, Contact, Referral, Offer):
            self.assertEqual(model.objects.count(), 0)
