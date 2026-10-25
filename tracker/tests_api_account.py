"""The account area of the JSON API: profile, search areas, AI settings (write-only keys), own job boards, assistant tokens, the welcome
questions and deleting the account. Each rule is the classic page's rule, so these tests also pin that the two stay the same."""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from tracker.models import AIUsageEvent, ApiToken, Application, JobSource, SearchArea, SiteConfig, UserProfile
from tracker.services.netguard import FetchError
from tracker.tests_api import BASE, job, person

User = get_user_model()
CV = "Backend engineer with ten years of Python, Django and PostgreSQL. Led teams, shipped payments systems."
SECRET = "sk-test-SECRET-key-value-12345"


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        self.client.force_login(self.a)

    def get(self, path):
        return self.client.get(f"{BASE}{path}")

    def send(self, method, path, body=None):
        return getattr(self.client, method)(f"{BASE}{path}", data=json.dumps(body if body is not None else {}), content_type="application/json")

    def put(self, path, body):
        return self.send("put", path, body)

    def post(self, path, body=None):
        return self.send("post", path, body)


class ProfileApi(Base):
    def test_get_has_the_profile_areas_and_account_and_no_secrets(self):
        SearchArea.objects.create(owner=self.a, place="Malaysia", allow_onsite=True)
        data = self.get("/profile").json()
        self.assertEqual(data["account"]["username"], "alice")
        self.assertEqual([a["place"] for a in data["areas"]], ["Malaysia"])
        self.assertIn("full_time", [c["value"] for c in data["choices"]["employment_types"]])
        self.assertTrue(data["account"]["can_delete"])
        self.assertNotIn("password", json.dumps({**data, "account": {k: v for k, v in data["account"].items() if k != "classic"}}).lower())
        self.assertNotIn("key", " ".join(data["profile"]))

    def test_saving_changes_the_profile_and_keeps_the_cv_history(self):
        r = self.put("/profile", {"target_roles": "Backend Engineer", "home_country": "Bangladesh", "profile_cv": CV, "employment_types": ["full_time"]})
        self.assertEqual(r.status_code, 200, r.content)
        profile = UserProfile.objects.get(user=self.a)
        self.assertEqual((profile.target_roles, profile.home_country, profile.employment_types), ("Backend Engineer", "BD", ["full_time"]))
        self.assertEqual(r.json()["profile"]["home_country"], "Bangladesh")
        self.assertEqual(self.a.cv_versions.count(), 1)

    def test_a_partial_save_does_not_blank_the_rest(self):
        UserProfile.objects.filter(user=self.a).update(target_roles="Keep me", profile_cv=CV, scan_digest_enabled=True)
        self.assertEqual(self.put("/profile", {"about": "New"}).status_code, 200)
        profile = UserProfile.objects.get(user=self.a)
        self.assertEqual((profile.target_roles, profile.profile_cv, profile.scan_digest_enabled, profile.about), ("Keep me", CV, True, "New"))

    def test_a_bad_country_is_refused_with_the_same_words_as_the_classic_page(self):
        r = self.put("/profile", {"home_country": "Narnia"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Not recognised as one country", r.json()["error"])
        self.assertIn("home_country", r.json()["fields"])

    def test_a_cv_file_is_read_into_the_text_and_not_kept(self):
        upload = SimpleUploadedFile("cv.txt", CV.encode(), content_type="text/plain")
        r = self.client.post(f"{BASE}/profile", {"about": "x", "cv_file": upload})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(UserProfile.objects.get(user=self.a).profile_cv, CV)

    def test_a_cv_file_of_the_wrong_kind_is_refused(self):
        upload = SimpleUploadedFile("cv.exe", b"MZ", content_type="application/octet-stream")
        r = self.client.post(f"{BASE}/profile", {"cv_file": upload})
        self.assertEqual(r.status_code, 400)
        self.assertIn("cv_file", r.json()["fields"])

    def test_someone_elses_profile_is_never_touched(self):
        self.put("/profile", {"target_roles": "Mine"})
        self.assertEqual(UserProfile.for_user(self.b).target_roles, "")

    def test_the_old_new_app_switch_is_gone(self):
        before = UserProfile.objects.get(user=self.a).use_new_app
        self.put("/profile", {"use_new_app": not before})
        self.assertEqual(UserProfile.objects.get(user=self.a).use_new_app, before)
        self.assertNotIn("use_new_app", self.get("/profile").json()["profile"])
        self.assertNotIn("new_app_enabled", self.get("/profile").json()["site"])

    def test_the_document_count_leaves_out_the_cv(self):
        self.put("/profile", {"profile_cv": CV})
        self.assertEqual(self.get("/profile").json()["account"]["counts"]["documents"], 0)


class SearchAreaApi(Base):
    def add(self, **kw):
        return self.post("/profile/areas", {"place": "Malaysia", "allow_onsite": True, **kw})

    def test_add_change_and_remove(self):
        r = self.add(city="Kuala Lumpur")
        self.assertEqual(r.status_code, 200, r.content)
        area_id = r.json()["area"]["id"]
        self.assertEqual(SearchArea.objects.get(pk=area_id).owner, self.a)
        r = self.send("patch", f"/profile/areas/{area_id}", {"min_salary": 8000, "salary_currency": "usd"})
        self.assertEqual(r.status_code, 200, r.content)
        area = SearchArea.objects.get(pk=area_id)
        self.assertEqual((area.min_salary, area.salary_currency, area.place, area.allow_onsite), (8000, "USD", "Malaysia", True))
        self.assertEqual(self.send("delete", f"/profile/areas/{area_id}").status_code, 200)
        self.assertFalse(SearchArea.objects.filter(pk=area_id).exists())

    def test_a_place_must_allow_some_kind_of_work(self):
        r = self.post("/profile/areas", {"place": "Malaysia"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("at least one of remote, hybrid or on-site", r.json()["error"])

    def test_pay_needs_a_currency(self):
        r = self.add(min_salary=5000)
        self.assertEqual(r.status_code, 400)
        self.assertIn("salary_currency", r.json()["fields"])

    def test_a_place_we_do_not_recognise_is_kept_with_a_warning(self):
        r = self.add(place="Zzyzx Basin")
        self.assertEqual(r.status_code, 200)
        self.assertIn("not a place we recognise", r.json()["warning"])

    def test_at_most_twenty(self):
        for n in range(20):
            SearchArea.objects.create(owner=self.a, place=f"P{n}", allow_remote=True)
        r = self.add()
        self.assertEqual(r.status_code, 400)
        self.assertIn("at most 20", r.json()["error"])

    def test_another_persons_area_is_a_404(self):
        theirs = SearchArea.objects.create(owner=self.b, place="Gulf", allow_remote=True)
        self.assertEqual(self.send("patch", f"/profile/areas/{theirs.pk}", {"city": "x"}).status_code, 404)
        self.assertEqual(self.send("delete", f"/profile/areas/{theirs.pk}").status_code, 404)
        self.assertTrue(SearchArea.objects.filter(pk=theirs.pk, city="").exists())


class AiSettingsApi(Base):
    def test_a_key_is_write_only(self):
        r = self.put("/ai-settings", {"ai_provider": "openai", "ai_model": "gpt-4o-mini", "ai_api_key": SECRET, "rag_embedding_key": SECRET + "-rag"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertNotIn(SECRET, r.content.decode())
        data = self.get("/ai-settings")
        self.assertNotIn(SECRET, data.content.decode())
        self.assertNotIn("sk-test", data.content.decode())
        self.assertTrue(data.json()["has_key"] and data.json()["has_rag_key"])
        profile = UserProfile.objects.get(user=self.a)
        self.assertNotIn(SECRET, profile.ai_key_encrypted)  # stored encrypted
        self.assertEqual(profile.effective_ai_key, SECRET)
        self.assertNotIn(SECRET, self.get("/profile").content.decode())

    def test_a_blank_key_keeps_the_saved_one_and_only_the_clear_box_removes_it(self):
        self.put("/ai-settings", {"ai_provider": "openai", "ai_api_key": SECRET})
        saved = UserProfile.objects.get(user=self.a).ai_key_encrypted
        self.put("/ai-settings", {"ai_api_key": "", "ai_model": "other"})
        self.assertEqual(UserProfile.objects.get(user=self.a).ai_key_encrypted, saved)
        self.put("/ai-settings", {"clear_ai_key": True})
        self.assertEqual(UserProfile.objects.get(user=self.a).ai_key_encrypted, "")
        self.assertFalse(self.get("/ai-settings").json()["has_key"])

    def test_an_error_never_echoes_the_key(self):
        r = self.put("/ai-settings", {"ai_api_key": SECRET, "ai_timeout": 5})
        self.assertEqual(r.status_code, 400)
        self.assertNotIn(SECRET, r.content.decode())
        self.assertIn("ai_timeout", r.json()["fields"])
        self.assertEqual(UserProfile.objects.get(user=self.a).ai_key_encrypted, "")

    def test_ordinary_people_cannot_point_the_server_at_a_local_or_private_address(self):
        for url in ("http://127.0.0.1:11434/v1", "http://localhost/v1", "http://10.0.0.5/v1", "http://169.254.169.254/latest"):
            r = self.put("/ai-settings", {"ai_provider": "openai", "ai_base_url": url})
            self.assertEqual(r.status_code, 400, url)
            self.assertIn("ai_base_url", r.json()["fields"])
        r = self.put("/ai-settings", {"rag_embedding_base_url": "http://127.0.0.1:1234/v1"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(UserProfile.objects.get(user=self.a).ai_base_url, "")

    def test_ordinary_people_cannot_choose_a_provider_that_runs_commands_on_the_server(self):
        for provider in ("claude_cli", "agent_sdk"):
            self.assertEqual(self.put("/ai-settings", {"ai_provider": provider}).status_code, 400)
        self.assertNotIn("claude_cli", [p["value"] for p in self.get("/ai-settings").json()["providers"]])

    def test_staff_can_use_local_urls_and_see_the_local_presets(self):
        staff = User.objects.create_user("boss", email="b@example.com", password="x" * 12, is_staff=True)
        self.client.force_login(staff)
        r = self.put("/ai-settings", {"ai_provider": "openai", "ai_base_url": "http://127.0.0.1:11434/v1"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("ollama", [p["key"] for p in self.get("/ai-settings").json()["presets"]])
        self.assertIn("claude_cli", [p["value"] for p in self.get("/ai-settings").json()["providers"]])

    def test_ordinary_people_do_not_get_the_local_presets(self):
        presets = self.get("/ai-settings").json()["presets"]
        self.assertTrue(presets)
        self.assertEqual({p["key"] for p in presets} & {"ollama", "lmstudio"}, set())
        self.assertTrue(all(p["base_url"].startswith("https://") or p["base_url"] == "" for p in presets))

    def test_usage_this_month_is_the_persons_own(self):
        AIUsageEvent.objects.create(owner=self.a, provider="openai", purpose="evaluate", input_tokens=100, output_tokens=50, cost_usd="0.0100")
        AIUsageEvent.objects.create(owner=self.b, provider="openai", purpose="evaluate", input_tokens=9999, output_tokens=1, cost_usd="5")
        usage = self.get("/ai-settings").json()["usage"]
        self.assertEqual((usage["calls"], usage["total_tokens"], usage["cost_usd"]), (1, 150, 0.01))

    def test_no_usage_says_zero_calls(self):
        self.assertEqual(self.get("/ai-settings").json()["usage"]["calls"], 0)

    def test_the_settings_belong_to_the_signed_in_person(self):
        self.put("/ai-settings", {"ai_provider": "openai", "ai_api_key": SECRET})
        self.assertEqual(UserProfile.for_user(self.b).ai_provider, "none")
        self.client.force_login(self.b)
        self.assertFalse(self.get("/ai-settings").json()["has_key"])


@override_settings(STILLOPEN_MAX_OWN_SOURCES=3, STILLOPEN_SOURCE_ADDS_PER_HOUR=50)
class SourcesApi(Base):
    FETCH = "tracker.services.scan.fetch_greenhouse"

    def add(self, token="acme", connector="greenhouse", **kw):
        return self.post("/sources", {"connector": connector, "board_token": token, **kw})

    def test_add_reads_the_board_once_and_saves_it_for_the_person(self):
        with mock.patch(self.FETCH, return_value=[{}, {}]) as fetch:
            r = self.add()
        self.assertEqual(r.status_code, 200, r.content)
        fetch.assert_called_once()
        self.assertEqual(r.json()["openings"], 2)
        source = JobSource.objects.get(owner=self.a)
        self.assertEqual((source.connector, source.board_token, source.name), ("greenhouse", "acme", "acme"))
        self.assertEqual([s["board_token"] for s in self.get("/sources").json()["mine"]], ["acme"])

    def test_a_pasted_careers_page_address_is_only_parsed(self):
        with mock.patch(self.FETCH, return_value=[]), mock.patch("tracker.services.scan.safe_get") as get:
            r = self.add(token="https://boards.greenhouse.io/acme/jobs/123")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(JobSource.objects.get(owner=self.a).board_token, "acme")
        get.assert_not_called()

    def test_a_token_with_dots_or_slashes_is_refused_and_nothing_is_fetched(self):
        with mock.patch(self.FETCH) as fetch:
            for token in ("evil.com/x", "../etc", "a b", "-lead", "http://example.com/acme"):
                r = self.add(token=token)
                self.assertEqual(r.status_code, 400, token)
                self.assertIn("board_token", r.json()["fields"])
            fetch.assert_not_called()
        self.assertFalse(JobSource.objects.filter(owner=self.a).exists())

    def test_an_unknown_connector_is_refused(self):
        self.assertEqual(self.add(connector="jooble").status_code, 400)
        self.assertEqual(self.add(connector="remoteok").status_code, 400)

    def test_a_board_that_cannot_be_read_is_not_saved(self):
        with mock.patch(self.FETCH, side_effect=FetchError("HTTP 404")):
            r = self.add()
        self.assertEqual(r.status_code, 400)
        self.assertIn("could not read jobs", r.json()["error"])
        self.assertFalse(JobSource.objects.filter(owner=self.a).exists())

    def test_the_cap(self):
        with mock.patch(self.FETCH, return_value=[]):
            for n in range(3):
                self.assertEqual(self.add(token=f"co{n}").status_code, 200)
            r = self.add(token="co9")
        self.assertEqual(r.status_code, 400)
        self.assertIn("up to 3", r.json()["error"])

    @override_settings(STILLOPEN_SOURCE_ADDS_PER_HOUR=1)
    def test_the_hourly_limit_is_a_429(self):
        with mock.patch(self.FETCH, return_value=[]):
            self.assertEqual(self.add(token="one").status_code, 200)
            r = self.add(token="two")
        self.assertEqual(r.status_code, 429)
        self.assertEqual(JobSource.objects.filter(owner=self.a).count(), 1)

    def test_adding_the_same_board_twice_or_a_site_wide_one_adds_nothing(self):
        JobSource.objects.create(name="Shared", connector="lever", board_token="shared")
        with mock.patch(self.FETCH, return_value=[]), mock.patch("tracker.services.scan.fetch_lever", return_value=[]):
            self.assertEqual(self.add().status_code, 200)
            first = self.add()
            self.assertEqual(first.status_code, 200)
            self.assertIn("already added", first.json()["info"])  # plain information, not an error
            second = self.add(token="shared", connector="lever")
            self.assertEqual(second.status_code, 200)
            self.assertIn("already part of every search", second.json()["info"])
        self.assertEqual(JobSource.objects.filter(owner=self.a).count(), 1)

    def test_pause_resume_and_remove(self):
        source = JobSource.objects.create(owner=self.a, name="Mine", connector="greenhouse", board_token="mine")
        self.assertFalse(self.post(f"/sources/{source.pk}/toggle").json()["source"]["enabled"])
        self.assertTrue(self.post(f"/sources/{source.pk}/toggle").json()["source"]["enabled"])
        self.assertEqual(self.send("delete", f"/sources/{source.pk}").status_code, 200)
        self.assertFalse(JobSource.objects.filter(pk=source.pk).exists())

    def test_other_peoples_and_site_wide_boards_are_a_404_and_not_listed(self):
        theirs = JobSource.objects.create(owner=self.b, name="Theirs", connector="greenhouse", board_token="theirs")
        shared = JobSource.objects.create(name="Shared board", connector="lever", board_token="sharedboard")
        for source in (theirs, shared):
            self.assertEqual(self.post(f"/sources/{source.pk}/toggle").status_code, 404)
            self.assertEqual(self.send("delete", f"/sources/{source.pk}").status_code, 404)
            self.assertTrue(JobSource.objects.filter(pk=source.pk, enabled=True).exists())
        data = self.get("/sources").json()
        self.assertEqual(data["mine"], [])
        self.assertNotIn("Theirs", json.dumps(data))
        self.assertIn("Shared board", data["shared"])


class AssistantApi(Base):
    def setUp(self):
        super().setUp()
        SiteConfig.objects.update(mcp_remote_enabled=True)

    def make(self, **kw):
        return self.post("/assistant/tokens", {"name": "Laptop", **kw})

    def test_switched_off_is_a_404(self):
        SiteConfig.objects.update(mcp_remote_enabled=False)
        self.assertEqual(self.get("/assistant").status_code, 404)
        self.assertEqual(self.make().status_code, 404)

    def test_the_raw_token_is_shown_once_and_only_a_hash_is_kept(self):
        r = self.make(access="write", expires=30)
        self.assertEqual(r.status_code, 200, r.content)
        raw = r.json()["token"]
        self.assertTrue(raw.startswith("so_"))
        self.assertEqual(r["Cache-Control"], "no-store")
        record = ApiToken.objects.get(owner=self.a)
        self.assertTrue(record.can_write)
        self.assertNotIn(raw, record.token_hash)
        self.assertIsNotNone(ApiToken.lookup(raw))
        listing = self.get("/assistant")
        self.assertNotIn(raw, listing.content.decode())
        self.assertEqual(listing.json()["tokens"][0]["hint"], raw[:8])
        self.assertNotIn(raw, self.get("/profile").content.decode())
        self.assertNotIn("token", [k for t in listing.json()["tokens"] for k in t])

    def test_read_only_and_ninety_days_are_the_defaults(self):
        self.make(access="nonsense", expires=7)
        record = ApiToken.objects.get(owner=self.a)
        self.assertFalse(record.can_write)
        self.assertGreater((record.expires_at - record.created_at).days, 88)

    @override_settings(STILLOPEN_MAX_API_TOKENS=2)
    def test_the_cap_counts_active_tokens_only(self):
        self.assertEqual(self.make().status_code, 200)
        self.assertEqual(self.make().status_code, 200)
        r = self.make()
        self.assertEqual(r.status_code, 400)
        self.assertIn("already have 2 active tokens", r.json()["error"])
        first = ApiToken.objects.filter(owner=self.a).first()
        self.post(f"/assistant/tokens/{first.pk}/revoke")
        self.assertEqual(self.make().status_code, 200)

    @override_settings(STILLOPEN_TOKEN_ISSUES_PER_HOUR=1)
    def test_the_hourly_limit_is_a_429(self):
        self.assertEqual(self.make().status_code, 200)
        self.assertEqual(self.make().status_code, 429)

    def test_revoking_stops_the_token_straight_away(self):
        raw = self.make().json()["token"]
        token = ApiToken.objects.get(owner=self.a)
        r = self.post(f"/assistant/tokens/{token.pk}/revoke")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["token"]["state"], "Revoked")
        self.assertIsNone(ApiToken.lookup(raw))

    def test_someone_elses_token_is_a_404_and_stays_usable(self):
        record, raw = ApiToken.issue(self.b, "Theirs")
        self.assertEqual(self.post(f"/assistant/tokens/{record.pk}/revoke").status_code, 404)
        self.assertIsNotNone(ApiToken.lookup(raw))
        self.assertEqual(self.get("/assistant").json()["tokens"], [])


class WelcomeApi(Base):
    def setUp(self):
        super().setUp()
        self.client.force_login(person("sam"))
        self.sam = User.objects.get(username="sam")

    def test_the_answers_fill_the_profile_and_make_search_areas(self):
        r = self.post("/welcome", {"target_roles": "Backend Engineer", "home_country": "Bangladesh", "profile_cv": CV, "open_remote": True, "other_places": "Malaysia"})
        self.assertEqual(r.status_code, 200, r.content)
        profile = UserProfile.objects.get(user=self.sam)
        self.assertTrue(profile.onboarding_done)
        self.assertEqual((profile.target_roles, profile.home_country), ("Backend Engineer", "BD"))
        self.assertEqual(sorted(self.sam.search_areas.values_list("place", flat=True)), ["Anywhere", "Bangladesh", "Malaysia"])

    def test_a_bad_country_keeps_the_person_on_the_page(self):
        r = self.post("/welcome", {"target_roles": "x", "home_country": "Narnia", "profile_cv": CV})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Not recognised as one country", r.json()["error"])
        self.assertFalse(UserProfile.objects.get(user=self.sam).onboarding_done)

    def test_existing_search_areas_are_never_replaced(self):
        SearchArea.objects.create(owner=self.sam, place="Gulf", allow_onsite=True)
        self.post("/welcome", {"target_roles": "x", "home_country": "Bangladesh", "profile_cv": CV})
        self.assertEqual(list(self.sam.search_areas.values_list("place", flat=True)), ["Gulf"])

    def test_skipping_is_remembered(self):
        self.assertFalse(self.get("/welcome").json()["done"])
        self.assertEqual(self.post("/welcome/skip").status_code, 200)
        self.assertTrue(self.get("/welcome").json()["done"])


class DeleteAccountApi(Base):
    def test_the_typed_username_must_match_exactly(self):
        for confirm in ("", "Alice", "bob", "alicex"):
            r = self.post("/account/delete", {"confirm": confirm})
            self.assertEqual(r.status_code, 400, confirm)
        self.assertTrue(User.objects.filter(pk=self.a.pk).exists())

    def test_deleting_removes_the_person_and_everything_of_theirs_and_ends_the_session(self):
        mine = job(self.a)
        theirs = job(self.b)
        SearchArea.objects.create(owner=self.a, place="Gulf", allow_remote=True)
        ApiToken.issue(self.a, "x")
        JobSource.objects.create(owner=self.a, name="m", connector="greenhouse", board_token="m")
        r = self.post("/account/delete", {"confirm": "alice"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(User.objects.filter(pk=self.a.pk).exists())
        self.assertFalse(Application.objects.filter(pk=mine.pk).exists())
        self.assertFalse(ApiToken.objects.filter(owner_id=self.a.pk).exists())
        self.assertFalse(SearchArea.objects.filter(owner_id=self.a.pk).exists())
        self.assertFalse(JobSource.objects.filter(owner_id=self.a.pk).exists())
        self.assertTrue(Application.objects.filter(pk=theirs.pk).exists())
        self.assertEqual(self.get("/me").status_code, 401)

    def test_site_admins_cannot_delete_themselves_here(self):
        staff = User.objects.create_user("boss", email="b@example.com", password="x" * 12, is_staff=True)
        self.client.force_login(staff)
        r = self.post("/account/delete", {"confirm": "boss"})
        self.assertEqual(r.status_code, 400)
        self.assertTrue(User.objects.filter(pk=staff.pk).exists())
        self.assertFalse(self.get("/profile").json()["account"]["can_delete"])


class ClassicRedirects(Base):
    def setUp(self):
        super().setUp()
        SiteConfig.objects.update(new_app_enabled=True, mcp_remote_enabled=True)
        UserProfile.objects.filter(user=self.a).update(use_new_app=True)

    PAGES = {"profile": "/app/profile", "profile_ai": "/app/profile/ai", "assistant": "/app/profile/assistant", "sources": "/app/sources", "welcome": "/app/welcome"}

    def test_opted_in_people_land_on_the_new_screens(self):
        from django.urls import reverse

        for name, target in self.PAGES.items():
            r = self.client.get(reverse(name))
            self.assertRedirects(r, target, fetch_redirect_response=False, msg_prefix=name)

    def test_classic_one_bypasses(self):
        from django.urls import reverse

        for name in self.PAGES:
            self.assertEqual(self.client.get(reverse(name) + "?classic=1").status_code, 200, name)

    def test_everyone_else_keeps_the_classic_pages(self):
        from django.urls import reverse

        UserProfile.objects.filter(user=self.a).update(use_new_app=False)
        for name in self.PAGES:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_classic_posts_still_work_for_opted_in_people(self):
        from django.urls import reverse

        r = self.client.post(reverse("profile"), {"about": "hello"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(UserProfile.objects.get(user=self.a).about, "hello")
