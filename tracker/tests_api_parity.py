"""Parity gaps closed for the screens the new app took over: no API module may depend on a classic page that is going away, the classic wording
of the 429s is kept, and offers carry every amount the classic comparison showed."""
import json
import re
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings

from tracker.models import CoverLetter, CVVersion, JobSource, Offer, UserProfile
from tracker.tests_api import BASE, job, person
from tracker.tests_cv import MASTER

API_DIR = Path(__file__).resolve().parent / "api"
# classic addresses that stay (file downloads, print page, data export, allauth, privacy/terms); anything else would be an app screen
STAYS_CLASSIC = {
    "cv_download", "cv_print", "cover_download", "document_file", "export_data", "account_email", "account_change_password", "mfa_index",
    "socialaccount_connections", "privacy", "terms", "job_documents_zip",
}


def post(client, url, body=None):
    return client.post(url, data=json.dumps(body or {}), content_type="application/json")


class NoClassicDependence(TestCase):
    def test_api_modules_only_reverse_addresses_that_stay_classic(self):
        found = {}
        for path in API_DIR.glob("*.py"):
            if path.name == "routes.py":  # owned by the dashboard work
                continue
            for name in re.findall(r"reverse\(\s*[\"']([^\"']+)[\"']", path.read_text(encoding="utf-8")):
                found.setdefault(name, []).append(path.name)
        self.assertEqual({n: f for n, f in found.items() if n not in STAYS_CLASSIC}, {})

    def setUp(self):
        cache.clear()
        self.a = person("alice")
        UserProfile.objects.filter(user=self.a).update(profile_cv=MASTER)
        self.job = job(self.a, description="Backend engineer, C# and SQL Server, Docker.")
        self.client.force_login(self.a)

    def test_apply_and_cover_payloads_leave_the_in_app_links_to_the_front_end(self):
        version = CVVersion.objects.create(owner=self.a, kind="master", content=MASTER, approved=True)
        letter = CoverLetter.objects.create(owner=self.a, application=self.job, content="Hello", approved=True)
        apply_data = self.client.get(f"{BASE}/jobs/{self.job.pk}/apply").json()
        self.assertTrue(apply_data["versions"])
        for v in apply_data["versions"]:
            self.assertNotIn("open_url", v)
        self.assertEqual(apply_data["versions"][0]["id"], version.pk)
        for item in apply_data["cover_letters"]:
            self.assertNotIn("open_url", item)
        self.assertNotIn("apply_url", self.client.get(f"{BASE}/cover/{letter.pk}").json())

    def test_the_profile_offers_no_app_switch_any_more(self):
        data = self.client.get(f"{BASE}/profile").json()
        self.assertNotIn("use_new_app", data["profile"])
        self.assertNotIn("new_app_enabled", data["site"])
        self.assertNotIn("documents", data["account"]["classic"])


@override_settings(STILLOPEN_CVGEN_PER_HOUR=1)
class ClassicWording(TestCase):
    def setUp(self):
        cache.clear()
        self.a = person("alice")
        UserProfile.objects.filter(user=self.a).update(profile_cv=MASTER)
        self.job = job(self.a, description="Backend engineer, C# and SQL Server, Docker.")
        self.client.force_login(self.a)

    def test_tailoring_too_often_says_it_the_classic_way(self):
        post(self.client, f"{BASE}/jobs/{self.job.pk}/tailor", {"mode": "keywords"})
        r = post(self.client, f"{BASE}/jobs/{self.job.pk}/tailor", {"mode": "keywords"})
        self.assertEqual((r.status_code, r.json()["error"]), (429, "Too many CV requests this hour. Try again later."))

    def test_writing_a_letter_too_often_says_it_the_classic_way(self):
        post(self.client, f"{BASE}/jobs/{self.job.pk}/cover-letter", {"mode": "keywords"})
        r = post(self.client, f"{BASE}/jobs/{self.job.pk}/cover-letter", {"mode": "keywords"})
        self.assertEqual((r.status_code, r.json()["error"]), (429, "Too many requests this hour. Try again later."))

    def test_the_tailor_answer_carries_what_the_toast_needs(self):
        made = post(self.client, f"{BASE}/jobs/{self.job.pk}/tailor", {"mode": "keywords"}).json()
        self.assertEqual(set(made), {"id", "flagged", "flagged_count"})


class OfferLines(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        self.client.force_login(self.a)

    def offer(self, owner, company, base, status="open", **kw):
        return Offer.objects.create(owner=owner, application=job(owner, company=company), base=base, period="month", currency="USD", status=status, **kw)

    def test_every_amount_is_there_for_the_side_by_side_rows_and_declined_ones_drop_out(self):
        self.offer(self.a, "OpenCo", 1000, bonus=500, equity=100, other_benefits=50, signing=7)
        self.offer(self.a, "NoCo", 5000, status="declined")
        self.offer(self.b, "BobsOffer", 9000)
        data = self.client.get(f"{BASE}/offers").json()
        self.assertEqual(len(data["groups"]), 1)
        rows = data["groups"][0]["rows"]
        self.assertEqual([r["offer"]["job"]["company"] for r in rows], ["OpenCo"])
        offer = rows[0]["offer"]
        self.assertEqual(float(offer["yearly_base"]), 12000)
        self.assertEqual(float(offer["yearly_total"]), 12650)
        self.assertEqual((float(offer["bonus"]), float(offer["equity"]), float(offer["other_benefits"]), float(offer["signing"])), (500, 100, 50, 7))
        self.assertEqual(len(data["offers"]), 2)  # the declined one is still listed, just not compared


class OwnSourceInfo(TestCase):
    def setUp(self):
        cache.clear()
        self.a = person("alice")
        self.client.force_login(self.a)

    def test_adding_the_same_board_again_is_information_not_an_error(self):
        JobSource.objects.create(owner=self.a, name="Mine", connector="greenhouse", board_token="mine")
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=[]):
            r = post(self.client, f"{BASE}/sources", {"connector": "greenhouse", "board_token": "mine", "name": "Mine"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("already added", r.json()["info"])
        self.assertIsNone(r.json()["source"])
