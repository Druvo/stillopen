"""`GET /api/v1/sources/coverage` ("why is my country empty?") and the staff flag that asks for a Jooble or Adzuna key."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from tracker.models import JobSource, Posting, SearchArea, SiteConfig, UserProfile
from tracker.services import coverage

User = get_user_model()
BASE = "/api/v1"


def make(name, roles="Backend Engineer", staff=False):
    u = User.objects.create_user(name, email=f"{name}@example.com", password="pw-12345-abc", is_staff=staff)
    UserProfile.objects.filter(user=u).update(target_roles=roles, onboarding_done=True)
    return u


def posting(source, n, country="", remote=False, prefix="p"):
    for i in range(n):
        Posting.objects.create(source=source, url=f"https://x.test/{source.pk}/{prefix}/{country or 'none'}/{i}", title=f"Dev {i}",
                               title_key=f"{source.name} :: dev {prefix}{i}", company=source.name, country=country, remote=remote)


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.alice, self.bob = make("alice"), make("bob")
        self.board = JobSource.objects.create(name="Acme", connector="greenhouse", board_token="acme")
        self.client.force_login(self.alice)

    def get(self):
        r = self.client.get(f"{BASE}/sources/coverage")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def area(self, name, place="Pakistan"):
        return SearchArea.objects.create(owner=name, place=place, allow_remote=True)


class CoverageApi(Base):
    def test_signed_out_is_refused(self):
        self.client.logout()
        self.assertEqual(self.client.get(f"{BASE}/sources/coverage").status_code, 401)

    def test_no_areas_says_so(self):
        data = self.get()
        self.assertEqual((data["has_areas"], data["areas"], data["empty_areas"]), (False, [], 0))

    def test_an_empty_country_gets_a_plain_tip_naming_the_next_step(self):
        self.area(self.alice, "Pakistan")
        a = self.get()["areas"][0]
        self.assertEqual((a["label"], a["postings"], a["boards"], a["level"]), ("Pakistan", 0, 0, "none"))
        self.assertTrue(a["tip"].startswith("Nothing lists jobs in Pakistan yet."))
        self.assertIn("Jooble", a["tip"])
        self.assertIn("careers page", a["tip"])
        self.assertIn("Add job", a["tip"])
        self.assertIn("Ask the site owner", a["tip"])

    def test_counts_postings_by_country_and_region_for_the_last_30_days_only(self):
        posting(self.board, 20, "MY")
        posting(self.board, 3, "SG")
        old = Posting.objects.filter(country="MY").first()
        Posting.objects.filter(pk=old.pk).update(last_seen_at="2020-01-01T00:00:00Z")
        self.area(self.alice, "Malaysia")
        self.area(self.alice, "Southeast Asia")
        my, sea = self.get()["areas"]
        self.assertEqual((my["postings"], my["boards"], my["level"], my["tip"]), (19, 1, "ok", ""))
        self.assertEqual(sea["postings"], 22)

    def test_a_thin_place_names_the_count(self):
        posting(self.board, 4, "PK")
        self.area(self.alice, "Pakistan")
        a = self.get()["areas"][0]
        self.assertEqual(a["level"], "thin")
        self.assertTrue(a["tip"].startswith("Only 4 jobs listed in Pakistan so far."))

    def test_anywhere_counts_remote_postings(self):
        posting(self.board, 2, "", remote=True)
        self.area(self.alice, "Anywhere")
        a = self.get()["areas"][0]
        self.assertEqual((a["label"], a["postings"]), ("Anywhere (remote)", 2))

    def test_an_unrecognised_place_is_left_unknown_not_guessed(self):
        self.area(self.alice, "Atlantis")
        a = self.get()["areas"][0]
        self.assertEqual((a["known"], a["level"], a["tip"]), (False, "unknown", ""))

    def test_country_searches_that_apply_show_whether_their_key_is_there(self):
        JobSource.objects.create(name="Jooble Pakistan", connector="jooble", board_token="pk")
        JobSource.objects.create(name="Adzuna India", connector="adzuna", board_token="in")
        self.area(self.alice, "Pakistan")
        self.area(self.alice, "India")
        pk, india = self.get()["areas"]
        self.assertEqual([(s["connector"], s["ready"], s["reason"]) for s in pk["searches"]], [("jooble", False, "needs_key")])
        self.assertEqual([(s["connector"], s["reason"]) for s in india["searches"]], [("adzuna", "needs_key")])
        self.assertEqual((pk["searches_ready"], pk["searches_waiting"]), (0, 1))
        self.assertIn("Jooble covers Pakistan but needs a free key", pk["tip"])
        SiteConfig.objects.filter(pk=1).update(jooble_api_key="k")
        pk = self.get()["areas"][0]
        self.assertEqual((pk["searches_ready"], pk["searches"][0]["ready"]), (1, True))
        self.assertIn("runs with your next job search", pk["tip"])

    def test_without_roles_the_tip_asks_for_them(self):
        UserProfile.objects.filter(user=self.alice).update(target_roles="")
        JobSource.objects.create(name="JobTech", connector="jobtech", board_token="se")
        self.area(self.alice, "Sweden")
        a = self.get()["areas"][0]
        self.assertEqual(a["searches"][0]["reason"], "needs_roles")
        self.assertIn("roles you want", a["tip"])

    def test_staff_get_an_instruction_not_a_request_to_someone_else(self):
        self.alice.is_staff = True
        self.alice.save()
        JobSource.objects.create(name="Jooble Pakistan", connector="jooble", board_token="pk")
        self.area(self.alice, "Pakistan")
        tip = self.get()["areas"][0]["tip"]
        self.assertIn("Site configuration", tip)
        self.assertNotIn("Ask the site owner", tip)

    def test_another_persons_own_board_never_counts_for_me(self):
        mine = JobSource.objects.create(name="Bob Co", connector="greenhouse", board_token="bobco", owner=self.bob)
        posting(mine, 30, "PK")
        self.area(self.alice, "Pakistan")
        self.area(self.bob, "Pakistan")
        self.assertEqual(self.get()["areas"][0]["postings"], 0)
        self.client.force_login(self.bob)
        self.assertEqual(self.get()["areas"][0]["postings"], 30)

    def test_it_does_not_show_other_peoples_areas_or_keys(self):
        self.area(self.bob, "Kenya")
        SiteConfig.objects.filter(pk=1).update(jooble_api_key="sekret-jooble")
        data = self.get()
        self.assertEqual(data["areas"], [])
        self.assertNotIn("sekret-jooble", str(data))
        self.assertEqual(data["keys"], {"jooble": True, "adzuna": False})

    def test_counts_are_cached_and_the_query_count_does_not_grow_with_areas(self):
        for place in ("Pakistan", "India", "Egypt", "Kenya", "Nigeria", "Brazil"):
            self.area(self.alice, place)
        self.get()
        with CaptureQueriesContext(connection) as warm:
            self.get()
        posting(self.board, 5, "PK")  # not seen until the cache lapses
        self.assertEqual(self.get()["areas"][0]["postings"], 0)
        cache.delete(f"coverage-counts:{self.alice.pk}")
        self.assertEqual(self.get()["areas"][0]["postings"], 5)
        self.assertLess(len(warm), 25)


class TipWording(TestCase):
    def test_well_covered_has_no_tip(self):
        self.assertEqual(coverage.tip_for("Malaysia", 40, [], False, True), "")

    def test_no_connector_at_all(self):
        tip = coverage.tip_for("Bhutan", 0, [], False, True)
        self.assertIn("No job site we can search covers Bhutan", tip)
        self.assertIn("Adzuna or Jooble key", tip)


class StaffBannerFlag(TestCase):
    def test_flag_is_set_until_either_key_exists_and_is_staff_only(self):
        staff, user = make("boss", staff=True), make("pat")
        self.client.force_login(staff)
        self.assertTrue(self.client.get(f"{BASE}/me").json()["no_search_keys"])
        SiteConfig.objects.filter(pk=1).update(jooble_api_key="k")
        self.assertFalse(self.client.get(f"{BASE}/me").json()["no_search_keys"])
        SiteConfig.objects.filter(pk=1).update(jooble_api_key="", adzuna_app_id="id")
        self.assertTrue(self.client.get(f"{BASE}/me").json()["no_search_keys"])  # an id alone is not a working key
        config = SiteConfig.load()
        config.set_adzuna_app_key("key")
        config.save()
        self.assertFalse(self.client.get(f"{BASE}/me").json()["no_search_keys"])
        self.client.force_login(user)
        self.assertFalse(self.client.get(f"{BASE}/me").json()["no_search_keys"])
