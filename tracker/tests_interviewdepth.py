"""Interview and company depth: hiring-process timeline, interviewers, "this came up", question bank, company pages (isolation included)."""
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from tracker.models import BankQuestion, CameUp, CompanyNote, Contact, Interview, InterviewPrep, PrepPlan, PrepQuestion, PrepTopic, Status
from tracker.services import interviewdepth
from tracker.tests_api import BASE, job, person


def when(days=2):
    return (timezone.localtime() + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        self.job_a = job(self.a, company="Acme Ltd")
        self.job_b = job(self.b, company="Acme Ltd")
        self.client.force_login(self.a)

    def call(self, method, path, body=None):
        return getattr(self.client, method)(f"{BASE}{path}", data=body, content_type="application/json")

    def stage(self, **kw):
        body = {"application": self.job_a.pk, "scheduled_at": when(), "kind": "video"}
        body.update(kw)
        return self.call("post", "/interviews", body)


class Timeline(Base):
    def test_summary_and_order(self):
        self.assertIn("No stages", self.call("get", f"/jobs/{self.job_a.pk}/process").json()["summary"])
        self.stage(scheduled_at=when(5), kind="onsite")
        self.stage(scheduled_at=when(1), kind="phone")
        self.stage(scheduled_at=when(3), kind="takehome", custom_label="")
        first = Interview.objects.get(kind="phone")
        self.call("post", f"/interviews/{first.pk}/outcome", {"outcome": "passed"})
        data = self.call("get", f"/jobs/{self.job_a.pk}/process").json()
        self.assertEqual([s["kind"] for s in data["stages"]], ["phone", "takehome", "onsite"])
        self.assertEqual(data["summary"], "Round 1 of 3, passed")

    def test_cancelled_not_counted_and_noshow(self):
        self.stage(kind="phone")
        self.stage(kind="technical", scheduled_at=when(3))
        a, b = Interview.objects.order_by("scheduled_at")
        self.call("post", f"/interviews/{a.pk}/outcome", {"outcome": "passed"})
        self.assertEqual(self.call("post", f"/interviews/{b.pk}/outcome", {"outcome": "noshow"}).status_code, 200)
        self.assertEqual(self.call("get", f"/jobs/{self.job_a.pk}/process").json()["summary"], "Round 2 of 2, did not happen (no-show)")
        self.call("post", f"/interviews/{b.pk}/outcome", {"outcome": "cancelled"})
        self.assertEqual(self.call("get", f"/jobs/{self.job_a.pk}/process").json()["summary"], "Round 1 of 1, passed")

    def test_custom_stage_name(self):
        self.stage(kind="other", custom_label="Meet the CEO")
        self.assertEqual(self.call("get", f"/jobs/{self.job_a.pk}/process").json()["stages"][0]["name"], "Meet the CEO")

    def test_outcome_suggests_but_never_changes_status(self):
        self.stage()
        item = Interview.objects.get()
        before = self.job_a.status_id
        r = self.call("post", f"/interviews/{item.pk}/outcome", {"outcome": "rejected"}).json()
        self.assertEqual(r["suggest_status"]["name"], "Rejected")
        self.job_a.refresh_from_db()
        self.assertEqual(self.job_a.status_id, before)
        self.assertIsNone(self.call("post", f"/interviews/{item.pk}/outcome", {"outcome": "done"}).json()["suggest_status"])

    def test_process_isolation(self):
        self.assertEqual(self.call("get", f"/jobs/{self.job_b.pk}/process").status_code, 404)


class Interviewers(Base):
    def test_link_contacts_and_show_on_contact(self):
        c = Contact.objects.create(owner=self.a, name="Sam", company="Acme Ltd")
        r = self.stage(contacts=[c.pk])
        self.assertEqual(r.status_code, 200, r.content)
        item = Interview.objects.get()
        self.assertEqual(list(item.contacts.all()), [c])
        data = self.call("get", f"/jobs/{self.job_a.pk}/process").json()
        self.assertEqual(data["stages"][0]["interviewers"][0]["name"], "Sam")
        page = self.call("get", "/contacts").json()["contacts"][0]
        self.assertIn("Acme Ltd", page["interviewed_you_for"][0]["label"])
        # an edit that does not mention contacts keeps them
        self.call("patch", f"/interviews/{item.pk}", {"notes": "x"})
        self.assertEqual(item.contacts.count(), 1)
        self.call("patch", f"/interviews/{item.pk}", {"contacts": []})
        self.assertEqual(item.contacts.count(), 0)

    def test_someone_elses_contact_refused(self):
        theirs = Contact.objects.create(owner=self.b, name="Eve")
        r = self.stage(contacts=[theirs.pk])
        self.assertEqual(r.status_code, 400)
        self.assertIn("contacts", r.json()["fields"])
        self.assertEqual(Interview.objects.count(), 0)

    def test_malformed_contacts(self):
        self.assertEqual(self.stage(contacts="abc").status_code, 400)
        self.assertEqual(self.stage(contacts=[{"x": 1}]).status_code, 400)


class CameUpTicks(Base):
    def setUp(self):
        super().setUp()
        InterviewPrep.objects.create(owner=self.a, application=self.job_a, content={"groups": [
            {"key": "behavioural", "questions": [{"id": "behavioural-1", "question": "Q1"}, {"id": "behavioural-2", "question": "Q2"}]},
        ]})
        self.plan = PrepPlan.objects.create(owner=self.a, application=self.job_a, title="P", status="active")
        topic = PrepTopic.objects.create(plan=self.plan, slug="t", title="T")
        self.q = [PrepQuestion.objects.create(plan=self.plan, topic=topic, prompt=f"Q{n}", choices=["a"], correct=[0], sources=[]) for n in range(3)]

    def test_job_tally(self):
        r = self.call("post", f"/jobs/{self.job_a.pk}/came-up", {"key": "behavioural-1", "value": True}).json()
        self.assertEqual((r["came_up"], r["total"], r["text"]), (1, 2, "1 of 2 came up"))
        self.call("post", f"/jobs/{self.job_a.pk}/came-up", {"key": "behavioural-1", "value": True})
        self.assertEqual(CameUp.objects.count(), 1)
        r = self.call("post", f"/jobs/{self.job_a.pk}/came-up", {"key": "behavioural-1", "value": False}).json()
        self.assertEqual(r["came_up"], 0)
        self.assertIn("None of the 2", r["text"])

    def test_job_unknown_key_refused(self):
        self.assertEqual(self.call("post", f"/jobs/{self.job_a.pk}/came-up", {"key": "nope", "value": True}).status_code, 400)
        self.assertEqual(self.call("post", f"/jobs/{self.job_a.pk}/came-up", {"key": 5}).status_code, 422)

    def test_plan_tally(self):
        r = self.call("post", f"/prep/questions/{self.q[0].pk}/came-up", {"value": True}).json()
        self.assertEqual((r["came_up"], r["total"]), (1, 3))
        self.assertEqual(self.call("get", f"/prep/plans/{self.plan.pk}/came-up").json()["ticked"], [self.q[0].pk])

    def test_isolation(self):
        self.client.force_login(self.b)
        self.assertEqual(self.call("post", f"/prep/questions/{self.q[0].pk}/came-up", {"value": True}).status_code, 404)
        self.assertEqual(self.call("get", f"/prep/plans/{self.plan.pk}/came-up").status_code, 404)
        self.assertEqual(self.call("post", f"/jobs/{self.job_a.pk}/came-up", {"key": "behavioural-1", "value": True}).status_code, 404)
        self.assertEqual(CameUp.objects.count(), 0)


class Bank(Base):
    def test_create_search_filter_tags(self):
        r = self.call("post", "/bank", {"question": "Why us?", "answer": "Because <b>x</b>", "tags": ["Python", " python ", "sql"]})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["tags"], ["python", "sql"])
        self.call("post", "/bank", {"question": "Describe a conflict", "tags": ["people"]})
        data = self.call("get", "/bank?tag=sql").json()
        self.assertEqual([q["question"] for q in data["questions"]], ["Why us?"])
        self.assertEqual(data["tags"], ["people", "python", "sql"])
        self.assertEqual(len(self.call("get", "/bank?q=CONFLICT").json()["questions"]), 1)
        self.assertEqual(self.call("get", "/bank?q=zzz").json()["questions"], [])

    def test_caps_and_malformed(self):
        for body in (
            {"question": ""}, {"question": "x" * 401}, {"question": "ok", "tags": ["a"] * 1 + [f"t{i}" for i in range(5)]},
            {"question": "ok", "tags": ["y" * 31]}, {"question": "ok", "tags": [1]}, {"question": "ok", "tags": {"a": 1}},
            {"question": "ok", "answer": "a" * 4001}, {"question": "ok", "interview_ids": "1"}, {"question": "ok", "job_ids": [True]},
        ):
            self.assertEqual(self.call("post", "/bank", body).status_code, 400, body)
        self.assertEqual(BankQuestion.objects.count(), 0)

    def test_links_must_be_own_and_delete_asks(self):
        self.stage()
        item = Interview.objects.get()
        theirs = Interview.objects.create(owner=self.b, application=self.job_b, scheduled_at=timezone.now())
        self.assertEqual(self.call("post", "/bank", {"question": "Q", "interview_ids": [theirs.pk]}).status_code, 400)
        self.assertEqual(self.call("post", "/bank", {"question": "Q", "job_ids": [self.job_b.pk]}).status_code, 400)
        self.assertEqual(BankQuestion.objects.count(), 0)
        r = self.call("post", "/bank", {"question": "Q", "interview_ids": [item.pk], "job_ids": [self.job_a.pk]}).json()
        self.assertTrue(r["linked"])
        self.assertEqual(self.call("delete", f"/bank/{r['id']}").status_code, 409)
        self.assertEqual(BankQuestion.objects.count(), 1)
        self.assertEqual(self.call("delete", f"/bank/{r['id']}?confirm=true").status_code, 200)
        self.assertEqual(BankQuestion.objects.count(), 0)

    def test_unlinked_deletes_without_asking_and_edit(self):
        r = self.call("post", "/bank", {"question": "Q"}).json()
        self.assertEqual(self.call("patch", f"/bank/{r['id']}", {"answer": "mine"}).json()["answer"], "mine")
        self.assertEqual(self.call("delete", f"/bank/{r['id']}").status_code, 200)

    def test_isolation(self):
        mine = BankQuestion.objects.create(owner=self.a, question="Q")
        self.client.force_login(self.b)
        self.assertEqual(self.call("get", "/bank").json()["questions"], [])
        self.assertEqual(self.call("patch", f"/bank/{mine.pk}", {"answer": "x"}).status_code, 404)
        self.assertEqual(self.call("delete", f"/bank/{mine.pk}").status_code, 404)


class Companies(Base):
    def test_case_insensitive_aggregate(self):
        job(self.a, company="ACME ltd", role="Other")
        Contact.objects.create(owner=self.a, name="Sam", company="acme  LTD")
        self.stage()
        rows = self.call("get", "/companies").json()["companies"]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["jobs"], rows[0]["contacts"]), (2, 1))
        page = self.call("get", "/companies/page?key=Acme%20Ltd").json()
        self.assertEqual((len(page["jobs"]), len(page["contacts"]), len(page["interviews"])), (2, 1, 1))

    def test_notes_links_watch(self):
        r = self.call("patch", "/companies/page?key=acme ltd", {"notes": "<script>x</script>", "website": "https://acme.example.com", "watched": True})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["watched"])
        self.assertEqual(self.call("get", "/companies").json()["companies"][0]["watched"], True)
        self.assertEqual(CompanyNote.objects.filter(owner=self.a).count(), 1)

    def test_links_validated_never_fetched(self):
        with mock.patch("requests.get") as get, mock.patch("requests.sessions.Session.request") as req:
            for bad in ("http://acme.example.com", "javascript:alert(1)", "https://u:p@x.example.com", "https://a b.com", "ftp://x", "https://" + "a" * 300):
                self.assertEqual(self.call("patch", "/companies/page?key=acme ltd", {"careers": bad}).status_code, 400, bad)
            self.assertEqual(self.call("patch", "/companies/page?key=acme ltd", {"linkedin": "https://www.linkedin.com/company/acme"}).status_code, 200)
            self.assertFalse(get.called or req.called)
        self.assertEqual(CompanyNote.objects.get().careers, "")

    def test_notes_cap_and_unknown_company(self):
        self.assertEqual(self.call("patch", "/companies/page?key=acme ltd", {"notes": "x" * 4001}).status_code, 400)
        self.assertEqual(self.call("patch", "/companies/page?key=nobody", {"notes": "x"}).status_code, 404)
        self.assertEqual(self.call("get", "/companies/page?key=").status_code, 404)

    def test_isolation(self):
        job(self.b, company="OnlyBob")
        Contact.objects.create(owner=self.b, name="Bobs", company="OnlyBob")
        self.assertEqual(self.call("get", "/companies/page?key=onlybob").status_code, 404)
        self.assertEqual(self.call("patch", "/companies/page?key=onlybob", {"watched": True}).status_code, 404)
        names = [c["name"] for c in self.call("get", "/companies").json()["companies"]]
        self.assertEqual(names, ["Acme Ltd"])
        # the same name for two people never shares notes
        interviewdepth.save_company(self.b, "acme ltd", "Acme Ltd", {"notes": "bob private"})
        self.assertEqual(self.call("get", "/companies/page?key=acme ltd").json()["notes"], "")


class Helpers(TestCase):
    def test_clean_link_and_tags(self):
        self.assertEqual(interviewdepth.clean_link(None), "")
        self.assertEqual(interviewdepth.clean_tags("a, B ,a"), ["a", "b"])
        with self.assertRaises(ValueError):
            interviewdepth.clean_link("https://")

    def test_status_exists_for_suggestions(self):
        self.assertTrue(Status.objects.filter(name="Rejected").exists())
