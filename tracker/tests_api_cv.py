"""The CV and cover letter API: happy paths, validation, the fact-check approval gate, restricted delete, throttling, isolation, redirects."""
import json
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings

from tracker.models import CoverLetter, CVVersion, UserProfile
from tracker.services import ai
from tracker.tests_api import BASE, job, person
from tracker.tests_cv import MASTER


def post(client, url, body=None):
    return client.post(url, data=json.dumps(body or {}), content_type="application/json")


class CvApi(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        for u in (self.a, self.b):
            UserProfile.objects.filter(user=u).update(profile_cv=MASTER)
        self.job = job(self.a, description="Backend engineer, C# and SQL Server, Docker.")
        self.client.force_login(self.a)

    def tailor(self, mode="keywords"):
        return post(self.client, f"{BASE}/jobs/{self.job.pk}/tailor", {"mode": mode})

    def test_list_creates_the_master_and_shows_tailored_ones(self):
        data = self.client.get(f"{BASE}/cv").json()
        self.assertEqual(len(data["masters"]), 1)
        self.assertTrue(data["masters"][0]["current"])
        self.assertEqual(data["tailored"], [])
        made = self.tailor().json()
        data = self.client.get(f"{BASE}/cv").json()
        self.assertEqual([t["id"] for t in data["tailored"]], [made["id"]])
        self.assertEqual(data["tailored"][0]["job"]["company"], "Acme")

    def test_tailor_for_a_job_returns_the_new_cv(self):
        r = self.tailor()
        self.assertEqual(r.status_code, 200)
        version = CVVersion.objects.get(pk=r.json()["id"])
        self.assertEqual((version.kind, version.owner, version.application), ("tailored", self.a, self.job))
        detail = self.client.get(f"{BASE}/cv/{version.pk}").json()
        self.assertEqual(detail["content"], version.content)
        self.assertEqual(detail["check_report"], [])
        self.assertIsNotNone(detail["downloads"])
        self.assertTrue(detail["downloads"]["docx"].endswith("/download/docx/"))

    def test_a_failed_tailoring_says_why_and_saves_nothing(self):
        with mock.patch("tracker.services.cvgen.ai.complete", side_effect=ai.AIError("HTTP 401")):
            r = self.tailor("ai")
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.json()["error"])
        self.assertFalse(CVVersion.objects.filter(kind="tailored").exists())

    def test_tailoring_is_throttled_like_the_classic_page(self):
        with override_settings(STILLOPEN_CVGEN_PER_HOUR=1):
            self.assertEqual(self.tailor().status_code, 200)
            r = self.tailor()
        self.assertEqual(r.status_code, 429)
        self.assertEqual(CVVersion.objects.filter(kind="tailored").count(), 1)

    def flagged_version(self):
        master = CVVersion.objects.create(owner=self.a, kind="master", content=MASTER, approved=True)
        return CVVersion.objects.create(
            owner=self.a, kind="tailored", application=self.job, parent=master, content="I led 500 engineers.", label="Flagged",
            check_report=[{"kind": "number", "text": "500", "line": 1}],
        )

    def test_a_flagged_version_stays_locked_until_the_person_approves_it(self):
        v = self.flagged_version()
        detail = self.client.get(f"{BASE}/cv/{v.pk}").json()
        self.assertTrue(detail["flagged"])
        self.assertFalse(detail["exportable"])
        self.assertIsNone(detail["downloads"])
        self.assertEqual(detail["check_report"][0]["text"], "500")
        self.assertEqual(self.client.get(f"/cv/{v.pk}/download/md/").status_code, 404)
        self.assertEqual(self.client.get(f"/cv/{v.pk}/print/").status_code, 404)
        r = post(self.client, f"{BASE}/cv/{v.pk}/approve")
        self.assertTrue(r.json()["exportable"])
        self.assertEqual(self.client.get(f"/cv/{v.pk}/download/md/").status_code, 200)
        self.assertIsNotNone(self.client.get(f"{BASE}/cv/{v.pk}").json()["downloads"])

    def test_editing_a_tailored_cv_makes_a_new_checked_version(self):
        v = self.flagged_version()
        r = post(self.client, f"{BASE}/cv/{v.pk}/edit", {"content": "I led a team of 4 engineers.", "label": "Honest"})
        new = CVVersion.objects.get(pk=r.json()["id"])
        self.assertTrue(r.json()["changed"])
        self.assertNotEqual(new.pk, v.pk)
        self.assertEqual((new.parent, new.label), (v, "Honest"))
        v.refresh_from_db()
        self.assertEqual(v.content, "I led 500 engineers.")  # the old version never changes
        again = post(self.client, f"{BASE}/cv/{new.pk}/edit", {"content": new.content})
        self.assertFalse(again.json()["changed"])

    def test_editing_a_master_updates_the_current_cv_and_empty_text_is_refused(self):
        master = self.client.get(f"{BASE}/cv").json()["masters"][0]
        r = post(self.client, f"{BASE}/cv/{master['id']}/edit", {"content": MASTER + "\n- One more line."})
        self.assertEqual(r.status_code, 200)
        self.assertIn("One more line", UserProfile.objects.get(user=self.a).profile_cv)
        bad = post(self.client, f"{BASE}/cv/{master['id']}/edit", {"content": "   "})
        self.assertEqual(bad.status_code, 400)
        self.assertIn("empty", bad.json()["error"])

    def test_diff_defaults_to_the_parent_and_accepts_another_version(self):
        v = self.flagged_version()
        data = self.client.get(f"{BASE}/cv/{v.pk}/diff").json()
        self.assertEqual(data["other"]["id"], v.parent_id)
        tags = {row["tag"] for row in data["rows"]}
        self.assertTrue({"del", "add"} <= tags)
        self.assertNotIn(v.pk, [c["id"] for c in data["choices"]])
        same = self.client.get(f"{BASE}/cv/{v.parent_id}/diff").json()  # a master with nothing before it
        self.assertEqual(same["rows"], [])
        self.assertIsNone(same["other"])
        self.assertEqual(self.client.get(f"{BASE}/cv/{v.pk}/diff?against={v.parent_id}").json()["other"]["id"], v.parent_id)

    def test_diff_against_someone_elses_version_is_a_404(self):
        v = self.flagged_version()
        theirs = CVVersion.objects.create(owner=self.b, kind="master", content="x")
        self.assertEqual(self.client.get(f"{BASE}/cv/{v.pk}/diff?against={theirs.pk}").status_code, 404)

    def test_restore_adds_a_new_master_and_only_masters_can_be_restored(self):
        first = CVVersion.objects.create(owner=self.a, kind="master", content="# Old CV", label="Old", approved=True)
        CVVersion.objects.create(owner=self.a, kind="master", content="# New CV", label="New", approved=True)
        r = post(self.client, f"{BASE}/cv/{first.pk}/restore")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(CVVersion.objects.get(pk=r.json()["id"]).content, "# Old CV")
        self.assertEqual(UserProfile.objects.get(user=self.a).profile_cv, "# Old CV")
        self.assertEqual(CVVersion.objects.filter(owner=self.a, kind="master").count(), 3)
        tailored = self.flagged_version()
        self.assertEqual(post(self.client, f"{BASE}/cv/{tailored.pk}/restore").status_code, 400)

    def test_delete_a_tailored_version_but_never_a_master_or_one_that_was_sent(self):
        v = self.flagged_version()
        self.assertEqual(self.client.delete(f"{BASE}/cv/{v.parent_id}").status_code, 400)
        self.assertTrue(CVVersion.objects.filter(pk=v.parent_id).exists())
        self.job.applied_cv = v
        self.job.save()
        r = self.client.delete(f"{BASE}/cv/{v.pk}")
        self.assertEqual(r.status_code, 400)
        self.assertIn("recorded as sent", r.json()["error"])
        self.assertTrue(CVVersion.objects.filter(pk=v.pk).exists())
        self.job.applied_cv = None
        self.job.save()
        self.assertEqual(self.client.delete(f"{BASE}/cv/{v.pk}").status_code, 200)
        self.assertFalse(CVVersion.objects.filter(pk=v.pk).exists())

    def test_nothing_of_anyone_elses_is_reachable(self):
        mine = self.flagged_version()
        self.client.force_login(self.b)
        self.assertEqual(self.client.get(f"{BASE}/cv").json()["tailored"], [])
        self.assertEqual(self.client.get(f"{BASE}/cv/{mine.pk}").status_code, 404)
        self.assertEqual(self.tailor().status_code, 404)
        self.assertEqual(post(self.client, f"{BASE}/cv/{mine.pk}/approve").status_code, 404)
        mine.refresh_from_db()
        self.assertFalse(mine.approved)


class CoverApi(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        for u in (self.a, self.b):
            UserProfile.objects.filter(user=u).update(profile_cv=MASTER)
        self.job = job(self.a, description="Backend engineer, C# and SQL Server, Docker.")
        self.client.force_login(self.a)

    def write(self, mode="keywords"):
        return post(self.client, f"{BASE}/jobs/{self.job.pk}/cover-letter", {"mode": mode})

    def test_write_and_read_a_free_letter(self):
        made = self.write().json()
        detail = self.client.get(f"{BASE}/cover/{made['id']}").json()
        self.assertIn("Acme", detail["content"])
        self.assertEqual(detail["check_report"], [])
        self.assertTrue(detail["exportable"])
        self.assertTrue(detail["downloads"]["txt"].endswith("/download/txt/"))
        self.assertEqual(detail["job"]["company"], "Acme")

    def test_an_invented_claim_is_flagged_and_locked_until_approved(self):
        with mock.patch("tracker.services.coverletter.ai.complete", return_value="Dear hiring team,\n\nI led 500 engineers at Initech.\n\nKind regards,\n[Your name]"):
            made = self.write("ai").json()
        self.assertTrue(made["flagged"])
        detail = self.client.get(f"{BASE}/cover/{made['id']}").json()
        self.assertFalse(detail["exportable"])
        self.assertIsNone(detail["downloads"])
        self.assertEqual(self.client.get(f"/cover/{made['id']}/download/txt/").status_code, 404)
        self.assertTrue(post(self.client, f"{BASE}/cover/{made['id']}/approve").json()["exportable"])
        self.assertEqual(self.client.get(f"/cover/{made['id']}/download/txt/").status_code, 200)

    def test_saving_checks_again_and_withdraws_approval(self):
        made = self.write().json()
        post(self.client, f"{BASE}/cover/{made['id']}/approve")
        letter = CoverLetter.objects.get(pk=made["id"])
        r = post(self.client, f"{BASE}/cover/{letter.pk}/save", {"content": letter.content + "\nI have 25 years of Rust."})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual((data["source"], data["approved"], data["exportable"]), ("manual", False, False))
        self.assertTrue(data["flagged"])
        self.assertEqual(post(self.client, f"{BASE}/cover/{letter.pk}/save", {"content": "  "}).status_code, 400)

    def test_delete(self):
        made = self.write().json()
        self.assertEqual(self.client.delete(f"{BASE}/cover/{made['id']}").status_code, 200)
        self.assertEqual(self.client.get(f"{BASE}/cover/{made['id']}").status_code, 404)

    def test_writing_is_throttled_and_failures_are_plain(self):
        with mock.patch("tracker.services.coverletter.ai.complete", side_effect=ai.AIError("HTTP 401")):
            r = self.write("ai")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(CoverLetter.objects.exists())
        with override_settings(STILLOPEN_CVGEN_PER_HOUR=1):
            cache.clear()
            self.assertEqual(self.write().status_code, 200)
            self.assertEqual(self.write().status_code, 429)

    def test_isolation(self):
        letter = CoverLetter.objects.create(owner=self.a, application=self.job, content="Hello")
        self.client.force_login(self.b)
        self.assertEqual(self.client.get(f"{BASE}/cover/{letter.pk}").status_code, 404)
        self.assertEqual(post(self.client, f"{BASE}/cover/{letter.pk}/save", {"content": "x"}).status_code, 404)
        self.assertEqual(self.client.delete(f"{BASE}/cover/{letter.pk}").status_code, 404)
        self.assertEqual(self.write().status_code, 404)
        letter.refresh_from_db()
        self.assertEqual(letter.content, "Hello")
