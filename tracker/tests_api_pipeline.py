"""The new app's interviews, contacts, referrals, offers and insights: behaviour, field errors, isolation, redirects."""
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from tracker.models import Contact, Event, Interview, Offer, Referral, SiteConfig, UserProfile
from tracker.tests_api import BASE, job, person


def when(days=2):
    return (timezone.localtime() + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        self.job_a, self.job_b = job(self.a, company="AliceCo"), job(self.b, company="BobCo")
        self.client.force_login(self.a)

    def post(self, path, body):
        return self.client.post(f"{BASE}{path}", data=body, content_type="application/json")

    def patch(self, path, body):
        return self.client.patch(f"{BASE}{path}", data=body, content_type="application/json")

    def get(self, path):
        return self.client.get(f"{BASE}{path}").json()


class InterviewApi(Base):
    def add(self, **kw):
        body = {"application": self.job_a.pk, "scheduled_at": when(), "kind": "video", "where": "https://meet.example.com/x", "notes": "Ask about the team"}
        body.update(kw)
        return self.post("/interviews", body)

    def test_add_lists_and_notes_the_job(self):
        r = self.add()
        self.assertEqual(r.status_code, 200, r.content)
        data = self.get("/interviews")
        self.assertEqual(len(data["upcoming"]), 1)
        self.assertEqual(data["upcoming"][0]["job"]["company"], "AliceCo")
        self.assertEqual(data["past"], [])
        self.assertTrue(Event.objects.filter(application=self.job_a, kind="interview", text__contains="scheduled").exists())
        self.assertEqual([j["id"] for j in data["jobs"]], [self.job_a.pk])

    def test_bad_date_has_a_field_message(self):
        r = self.add(scheduled_at="soon")
        self.assertEqual(r.status_code, 400)
        self.assertIn("scheduled_at", r.json()["fields"])
        self.assertEqual(Interview.objects.count(), 0)

    def test_cannot_use_someone_elses_job(self):
        r = self.add(application=self.job_b.pk)
        self.assertEqual(r.status_code, 400)
        self.assertIn("application", r.json()["fields"])
        self.assertEqual(Interview.objects.count(), 0)

    def test_edit_keeps_what_is_not_sent_and_cannot_move_to_someone_elses_job(self):
        self.add()
        i = Interview.objects.get()
        self.assertEqual(self.patch(f"/interviews/{i.pk}", {"notes": "new notes"}).status_code, 200)
        i.refresh_from_db()
        self.assertEqual((i.notes, i.kind, i.application_id), ("new notes", "video", self.job_a.pk))
        self.assertEqual(self.patch(f"/interviews/{i.pk}", {"application": self.job_b.pk}).status_code, 400)
        i.refresh_from_db()
        self.assertEqual(i.application_id, self.job_a.pk)

    def test_outcome_moves_it_to_past_and_unknown_is_refused(self):
        self.add()
        i = Interview.objects.get()
        self.assertEqual(self.post(f"/interviews/{i.pk}/outcome", {"outcome": "bogus"}).status_code, 400)
        self.assertEqual(self.post(f"/interviews/{i.pk}/outcome", {"outcome": "passed"}).status_code, 200)
        data = self.get("/interviews")
        self.assertEqual((len(data["upcoming"]), len(data["past"])), (0, 1))
        self.assertTrue(Event.objects.filter(application=self.job_a, text__contains="Going well").exists())

    def test_delete_and_isolation(self):
        self.add()
        mine = Interview.objects.get()
        theirs = Interview.objects.create(owner=self.b, application=self.job_b, scheduled_at=timezone.now() + timedelta(days=1))
        self.assertNotIn("BobCo", str(self.get("/interviews")))
        self.assertEqual(self.client.delete(f"{BASE}/interviews/{theirs.pk}").status_code, 404)
        self.assertEqual(self.client.delete(f"{BASE}/interviews/{mine.pk}").status_code, 200)
        self.assertTrue(Interview.objects.filter(pk=theirs.pk).exists())

    @override_settings(STILLOPEN_MAX_PIPELINE=1)
    def test_limit_is_in_plain_words(self):
        self.assertEqual(self.add().status_code, 200)
        r = self.add()
        self.assertEqual(r.status_code, 400)
        self.assertIn("limit", r.json()["error"])


class ContactApi(Base):
    def test_contact_and_referral_flow(self):
        r = self.post("/contacts", {"name": "Sam", "company": "AliceCo", "email": "sam@example.com"})
        self.assertEqual(r.status_code, 200)
        c = Contact.objects.get()
        r = self.post("/referrals", {"contact": c.pk, "application": self.job_a.pk, "status": "thinking"})
        self.assertEqual(r.status_code, 200)
        rid = r.json()["id"]
        data = self.get("/contacts")
        self.assertEqual(data["contacts"][0]["referrals"][0]["job"]["company"], "AliceCo")
        self.assertEqual(self.post(f"/referrals/{rid}/status", {"status": "bogus"}).status_code, 400)
        self.assertEqual(self.post(f"/referrals/{rid}/status", {"status": "agreed"}).status_code, 200)
        self.assertEqual(Referral.objects.get().status, "agreed")
        self.assertTrue(Event.objects.filter(application=self.job_a, text__contains="Agreed").exists())
        self.assertEqual(self.patch(f"/contacts/{c.pk}", {"title": "Engineer"}).status_code, 200)
        c.refresh_from_db()
        self.assertEqual((c.title, c.name), ("Engineer", "Sam"))
        self.assertEqual(self.client.delete(f"{BASE}/referrals/{rid}").status_code, 200)
        self.assertEqual(self.client.delete(f"{BASE}/contacts/{c.pk}").status_code, 200)

    def test_field_errors(self):
        r = self.post("/contacts", {"name": "", "email": "nope"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("name", r.json()["fields"])
        self.assertIn("email", r.json()["fields"])

    def test_referral_cannot_use_someone_elses_job_or_contact(self):
        mine = Contact.objects.create(owner=self.a, name="Mine")
        theirs = Contact.objects.create(owner=self.b, name="Theirs")
        r = self.post("/referrals", {"contact": mine.pk, "application": self.job_b.pk, "status": "thinking"})
        self.assertEqual((r.status_code, "application" in r.json()["fields"]), (400, True))
        r = self.post("/referrals", {"contact": theirs.pk, "application": self.job_a.pk, "status": "thinking"})
        self.assertEqual((r.status_code, "contact" in r.json()["fields"]), (400, True))
        self.assertEqual(Referral.objects.count(), 0)

    def test_isolation(self):
        theirs = Contact.objects.create(owner=self.b, name="Secret Person")
        self.assertNotIn("Secret", str(self.get("/contacts")))
        self.assertEqual(self.client.delete(f"{BASE}/contacts/{theirs.pk}").status_code, 404)
        self.assertEqual(self.patch(f"/contacts/{theirs.pk}", {"name": "x"}).status_code, 404)


class OfferApi(Base):
    def add(self, **kw):
        body = {"application": self.job_a.pk, "base": "100000", "period": "year", "currency": "usd", "bonus": "10000"}
        body.update(kw)
        r = self.post("/offers", body)
        if not kw.get("expect_fail"):
            pass
        return r

    def test_compared_per_currency_never_converted_and_declined_dropped(self):
        self.assertEqual(self.add().status_code, 200)
        self.add(base="90000", bonus="0")
        self.add(base="5000", period="month", currency="MYR", bonus="0")
        self.add(base="999999", currency="USD", bonus="0")
        declined = Offer.objects.get(base="999999")
        self.assertEqual(self.post(f"/offers/{declined.pk}/status", {"status": "declined"}).status_code, 200)
        data = self.get("/offers")
        self.assertEqual([g["currency"] for g in data["groups"]], ["MYR", "USD"])
        usd = data["groups"][1]["rows"]
        self.assertEqual([r["offer"]["yearly_total"] for r in usd], ["110000.00", "90000.00"])
        self.assertEqual((usd[0]["best"], usd[0]["behind"], usd[1]["behind"]), (True, "0", "20000.00"))
        self.assertEqual(data["groups"][0]["rows"][0]["offer"]["yearly_total"], "60000.00")
        self.assertEqual(len(data["offers"]), 4)

    def test_validation_and_foreign_job(self):
        r = self.add(currency="dollars", base="-5")
        self.assertEqual(r.status_code, 400)
        self.assertTrue({"currency", "base"} <= set(r.json()["fields"]))
        r = self.add(application=self.job_b.pk)
        self.assertEqual((r.status_code, "application" in r.json()["fields"]), (400, True))
        self.assertEqual(Offer.objects.count(), 0)

    def test_edit_status_delete_and_isolation(self):
        self.add()
        o = Offer.objects.get()
        theirs = Offer.objects.create(owner=self.b, application=self.job_b, base=1, currency="USD")
        self.assertEqual(self.patch(f"/offers/{o.pk}", {"bonus": "500", "notes": "negotiate"}).status_code, 200)
        o.refresh_from_db()
        self.assertEqual((str(o.bonus), o.notes, str(o.base)), ("500.00", "negotiate", "100000.00"))
        self.assertEqual(self.post(f"/offers/{o.pk}/status", {"status": "bogus"}).status_code, 400)
        self.assertEqual(self.post(f"/offers/{theirs.pk}/status", {"status": "accepted"}).status_code, 404)
        self.assertEqual(self.client.delete(f"{BASE}/offers/{theirs.pk}").status_code, 404)
        self.assertEqual(self.client.delete(f"{BASE}/offers/{o.pk}").status_code, 200)
        self.assertTrue(Offer.objects.filter(pk=theirs.pk).exists())


class InsightsApi(Base):
    def test_numbers_are_mine_only(self):
        data = self.get("/insights")
        self.assertEqual((data["tracked"], data["applied"]), (1, 0))
        Interview.objects.create(owner=self.b, application=self.job_b, scheduled_at=timezone.now())
        self.assertEqual(self.get("/insights")["interviewed"], 0)


class ClassicRedirects(Base):
    def opt_in(self):
        config = SiteConfig.load()
        config.new_app_enabled = True
        config.save()
        profile = UserProfile.for_user(self.a)
        profile.use_new_app = True
        profile.save()

    def test_opted_in_people_land_in_the_new_app_and_classic_flag_bypasses(self):
        self.opt_in()
        for name in ("interviews", "contacts", "offers", "insights"):
            r = self.client.get(f"/{name}/")
            self.assertEqual((r.status_code, r["Location"]), (302, f"/app/{name}"), name)
            self.assertEqual(self.client.get(f"/{name}/?classic=1").status_code, 200)
        self.assertEqual(self.client.get("/interviews/?job=5")["Location"], "/app/interviews?job=5")

    def test_others_stay_on_the_classic_pages(self):
        self.assertEqual(self.client.get("/offers/").status_code, 200)
