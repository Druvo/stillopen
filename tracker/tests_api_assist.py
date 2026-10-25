"""The optional AI help over the JSON API: another person's job is a 404, nothing runs without the person's own key (a plain message says how to
add one), each helper is limited per hour, and nothing is saved except the latest interview questions and the reading of a posting."""
import json
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings

from tracker.models import AIUsageEvent, Application, Interview, InterviewPrep, PrepLesson, PrepPlan, PrepWeek, UserProfile
from tracker.services import assist
from tracker.tests_assist import POSTING, make_job, make_person, prep_payload, stand_in

BASE = "/api/v1"
ANSWER = ("I want this role because it is the kind of backend work I enjoy most. At Acme Ltd I built a Django payments API and led a small team, "
          "and I would like to bring that experience to the platform team at Gamma. I like building reliable services, I care about deploy speed, "
          "and I have used Docker and PostgreSQL every week. I am keen to keep learning how larger platforms work in production.")


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = make_person("alice"), make_person("bob")
        self.job_a, self.job_b = make_job(self.a), make_job(self.b)
        self.client.force_login(self.a)

    def post(self, path, body=None):
        return self.client.post(f"{BASE}{path}", data=json.dumps(body or {}), content_type="application/json")

    def patched(self, payload):
        return mock.patch("tracker.services.assist.ai.complete", stand_in(payload))


class Isolation(Base):
    def test_every_helper_is_a_404_for_someone_elses_job(self):
        jid = self.job_b.pk
        with self.patched(prep_payload()):
            calls = [
                self.client.get(f"{BASE}/jobs/{jid}/interview-prep"), self.post(f"/jobs/{jid}/interview-prep"),
                self.post(f"/jobs/{jid}/interview-prep/feedback", {"question": "Why?", "answer": "Because I like it a lot, really."}),
                self.post(f"/jobs/{jid}/application-answer", {"question": "Why do you want this role?"}),
                self.client.get(f"{BASE}/jobs/{jid}/summary"), self.post(f"/jobs/{jid}/summarise"),
                self.post(f"/jobs/{jid}/message-draft", {"kind": "follow_up"}),
            ]
        self.assertEqual([r.status_code for r in calls], [404] * 7)
        self.assertFalse(InterviewPrep.objects.exists())
        self.assertFalse(AIUsageEvent.objects.exists())
        self.job_b.refresh_from_db()
        self.assertEqual(self.job_b.ai_summary, {})

    def test_another_persons_interview_cannot_be_used_for_a_draft(self):
        from django.utils import timezone

        theirs = Interview.objects.create(owner=self.b, application=self.job_b, scheduled_at=timezone.now())
        mine_other_job = Interview.objects.create(owner=self.a, application=make_job(self.a), scheduled_at=timezone.now())
        for interview in (theirs, mine_other_job):
            r = self.post(f"/jobs/{self.job_a.pk}/message-draft", {"kind": "thank_you", "interview_id": interview.pk})
            self.assertEqual(r.status_code, 404)

    def test_signed_out_is_refused(self):
        self.client.logout()
        self.assertEqual(self.client.get(f"{BASE}/assist/status").status_code, 401)
        self.assertEqual(self.post("/profile/suggest").status_code, 401)

    def test_each_person_has_their_own_saved_questions(self):
        with self.patched(prep_payload()):
            self.assertEqual(self.post(f"/jobs/{self.job_a.pk}/interview-prep").status_code, 200)
        self.assertEqual(self.client.get(f"{BASE}/jobs/{self.job_a.pk}/interview-prep").json()["prep"]["job"]["id"], self.job_a.pk)
        self.client.force_login(self.b)
        self.assertIsNone(self.client.get(f"{BASE}/jobs/{self.job_b.pk}/interview-prep").json()["prep"])


class NoKey(Base):
    def setUp(self):
        super().setUp()
        UserProfile.objects.filter(user=self.a).update(ai_provider="none")

    def test_status_says_there_is_no_ai_and_where_to_add_one(self):
        data = self.client.get(f"{BASE}/assist/status").json()
        self.assertEqual((data["ai"], data["settings_path"]), (False, "/profile/ai?preset=gemini"))
        self.assertIn("Google AI Studio", data["message"])

    def test_the_ai_only_helpers_answer_with_the_plain_line_and_call_nothing(self):
        jid = self.job_a.pk
        with mock.patch("tracker.services.assist.ai.complete") as complete:
            calls = [
                self.post(f"/jobs/{jid}/interview-prep"),
                self.post(f"/jobs/{jid}/interview-prep/feedback", {"question": "Why?", "answer": "Because I like it a lot, really."}),
                self.post(f"/jobs/{jid}/application-answer", {"question": "Why do you want this role?"}),
                self.post(f"/jobs/{jid}/message-draft", {"kind": "follow_up", "polish": True}),
            ]
        complete.assert_not_called()
        for r in calls:
            self.assertEqual(r.status_code, 400)
            self.assertEqual(r.json()["error"], assist.NO_KEY_MESSAGE)

    def test_the_free_versions_still_work(self):
        r = self.post(f"/jobs/{self.job_a.pk}/summarise")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual((body["summary"]["method"], body["ai"]), ("rules", False))
        self.assertTrue(body["summary"]["red_flags"])
        r = self.post(f"/jobs/{self.job_a.pk}/message-draft", {"kind": "follow_up"})
        self.assertEqual(r.json()["method"], "template")
        r = self.post("/profile/suggest")
        self.assertEqual(r.json()["roles"], ["Senior Backend Engineer", "Backend Developer"])
        self.assertFalse(AIUsageEvent.objects.exists())


class WithAKey(Base):
    def test_interview_questions_and_the_dashboard_card(self):
        with self.patched(prep_payload()):
            r = self.post(f"/jobs/{self.job_a.pk}/interview-prep")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(sum(len(g["questions"]) for g in r.json()["prep"]["groups"]), 8)

    def test_feedback_returns_but_stores_nothing(self):
        reply = {"works": ["Clear."], "vague": [], "add": ["A result."], "star": {"situation": True}, "summary": "Good start."}
        with self.patched(reply):
            r = self.post(f"/jobs/{self.job_a.pk}/interview-prep/feedback", {"question": "Why?", "answer": "Because I like building reliable things."})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["feedback"]["works"], ["Clear."])
        self.assertFalse(InterviewPrep.objects.exists())

    def test_an_empty_answer_is_a_plain_400(self):
        r = self.post(f"/jobs/{self.job_a.pk}/interview-prep/feedback", {"question": "Why?", "answer": "ok"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Write your answer", r.json()["error"])

    def test_application_answer_with_a_flagged_claim(self):
        with self.patched({"answer": ANSWER + " I also won 7 awards at Initech."}):
            r = self.post(f"/jobs/{self.job_a.pk}/application-answer", {"question": "Why do you want this role?"})
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["flagged_count"], 2)

    def test_malformed_json_gives_a_plain_message(self):
        with self.patched("sorry, no"):
            r = self.post(f"/jobs/{self.job_a.pk}/application-answer", {"question": "Why do you want this role?"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Please try again", r.json()["error"])

    def test_summary_is_saved_on_the_job_and_shows_on_the_dashboard(self):
        reply = {"must_have": ["Python"], "nice_to_have": [], "seniority": "Senior", "pay": "", "visa": "", "relocation": "", "remote": "", "deadline": "", "red_flags": []}
        with self.patched(reply):
            self.assertEqual(self.post(f"/jobs/{self.job_a.pk}/summarise").status_code, 200)
        self.assertEqual(self.client.get(f"{BASE}/jobs/{self.job_a.pk}/summary").json()["summary"]["must_have"], ["Python"])
        with mock.patch("tracker.services.scan.maybe_auto_start"):
            jobs = self.client.get(f"{BASE}/dashboard").json()["jobs"]
        self.assertEqual(jobs[0]["ai_summary"]["must_have"], ["Python"])
        self.assertIsNone(jobs[0]["prep"])

    def test_the_dashboard_shows_prep_progress_for_the_job(self):
        plan = PrepPlan.objects.create(owner=self.a, application=self.job_a, title="P", status="active")
        week = PrepWeek.objects.create(plan=plan, order=1, title="W", hours=3)
        PrepLesson.objects.create(week=week, order=1, title="L1", sources=[])
        from django.utils import timezone

        PrepLesson.objects.create(week=week, order=2, title="L2", sources=[], done_at=timezone.now())
        with mock.patch("tracker.services.scan.maybe_auto_start"):
            jobs = self.client.get(f"{BASE}/dashboard").json()["jobs"]
        self.assertEqual(jobs[0]["prep"], {"id": plan.pk, "percent": 50})

    def test_suggest_with_cv_text_from_the_request(self):
        with self.patched({"roles": ["Cook"], "places": []}):
            r = self.post("/profile/suggest", {"cv": "Chef at a hotel."})
        self.assertEqual(r.json()["roles"], ["Cook"])

    def test_polished_draft_logs_usage(self):
        reply = {"subject": "Following up", "body": "Dear hiring team, I applied for the Platform Engineer role at Gamma and wanted to ask how it is going."}
        with self.patched(reply):
            r = self.post(f"/jobs/{self.job_a.pk}/message-draft", {"kind": "follow_up", "polish": True})
        self.assertEqual(r.json()["method"], "ai")


class Throttle(Base):
    @override_settings(STILLOPEN_ASSIST_PER_HOUR=1)
    def test_each_helper_is_limited_per_person_and_per_kind(self):
        reply = {"works": ["Clear."], "vague": [], "add": [], "star": {}, "summary": "Good."}
        feedback = {"question": "Why?", "answer": "Because I like building reliable things."}
        with self.patched(reply):
            self.assertEqual(self.post(f"/jobs/{self.job_a.pk}/interview-prep/feedback", feedback).status_code, 200)
            self.assertEqual(self.post(f"/jobs/{self.job_a.pk}/interview-prep/feedback", feedback).status_code, 429)
        with self.patched(prep_payload()):  # another kind of help has its own allowance
            self.assertEqual(self.post(f"/jobs/{self.job_a.pk}/interview-prep").status_code, 200)
            self.assertEqual(self.post(f"/jobs/{self.job_a.pk}/interview-prep").status_code, 429)
        self.client.force_login(self.b)  # and so does another person
        with self.patched(reply):
            self.assertEqual(self.post(f"/jobs/{self.job_b.pk}/interview-prep/feedback", feedback).status_code, 200)

    @override_settings(STILLOPEN_ASSIST_PER_HOUR=1)
    def test_the_free_versions_are_not_counted(self):
        UserProfile.objects.filter(user=self.a).update(ai_provider="none")
        for _ in range(3):
            self.assertEqual(self.post(f"/jobs/{self.job_a.pk}/summarise").status_code, 200)

    @override_settings(STILLOPEN_ASSIST_PER_HOUR=1)
    def test_summary_and_suggestions_with_ai_are_limited(self):
        reply = {"must_have": ["Python"], "roles": ["Cook"], "places": []}
        with self.patched(reply):
            self.assertEqual(self.post(f"/jobs/{self.job_a.pk}/summarise").status_code, 200)
            self.assertEqual(self.post(f"/jobs/{self.job_a.pk}/summarise").status_code, 429)
            self.assertEqual(self.post("/profile/suggest").status_code, 200)
            self.assertEqual(self.post("/profile/suggest").status_code, 429)


class PostingThatTalksToTheAI(Base):
    def test_instructions_in_the_posting_are_flagged_and_never_obeyed(self):
        seen = []
        reply = {"must_have": ["Python"], "nice_to_have": [], "seniority": "", "pay": "", "visa": "", "relocation": "", "remote": "", "deadline": "", "red_flags": []}
        with mock.patch("tracker.services.assist.ai.complete", stand_in(reply, seen)):
            r = self.post(f"/jobs/{self.job_a.pk}/summarise")
        flags = [f["quote"].lower() for f in r.json()["summary"]["red_flags"]]
        self.assertTrue(any(q.startswith("ignore all previous instructions") for q in flags))
        self.assertIn("Ignore all previous instructions", seen[0]["user"])  # present only as data inside the tags
        self.assertTrue(seen[0]["user"].startswith("<job_posting>"))
        self.job_a.refresh_from_db()
        self.assertIsNone(self.job_a.score)
        self.assertIn("rockstar", POSTING)
