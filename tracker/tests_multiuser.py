"""Hosted-service behaviour: every person sees and changes only their own data."""
import json
import re
import tempfile
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from tracker.models import (
    AIUsageEvent, Application, Document, DocumentKind, Event, JobSource, KnowledgeSource, LivenessRun, ScanRun,
    SiteConfig, Status, UserProfile,
)
from tracker.services import ai, claim, jobtext, knowledge, scan, who

User = get_user_model()
PW = "correct-horse-battery-staple"
CV = "Backend engineer. C#, SQL Server, REST APIs, Docker."
JD = "We need a backend engineer with C#, SQL Server and Docker experience. " * 6


def user(name, staff=False, **profile):
    u = User.objects.create_user(name, email=f"{name}@example.com", password=PW, is_staff=staff)
    if profile:
        UserProfile.objects.filter(user=u).update(**profile)
    return u


def job(owner, **kw):
    fields = {"owner": owner, "company": "Acme", "role": "Dev", "status": Status.objects.get(name="Evaluated")}
    fields.update(kw)
    return Application.objects.create(**fields)


def api(client, method, path, body=None, **extra):
    """A call to the app's JSON API (`/api/v1`). `body` is sent as JSON."""
    if body is None and method in ("get", "delete"):
        return getattr(client, method)(f"/api/v1{path}", **extra)
    return getattr(client, method)(f"/api/v1{path}", data=json.dumps(body or {}), content_type="application/json", **extra)


def signed_in(client) -> bool:
    return client.get("/api/v1/me").status_code == 200


class Isolation(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = user("alice", profile_cv=CV), user("bob", profile_cv=CV)
        self.job_a = job(self.a, company="AliceCo", description=JD, summary="alice summary")
        self.job_b = job(self.b, company="BobCo", description=JD, summary="bob summary")
        self.client.force_login(self.a)

    def test_dashboard_shows_only_my_jobs(self):
        data = api(self.client, "get", "/dashboard").json()
        self.assertEqual([j["company"] for j in data["jobs"]], ["AliceCo"])
        self.assertNotIn("BobCo", json.dumps(data))
        self.assertNotIn("bob summary", json.dumps(data))

    def test_cannot_act_on_someone_elses_job(self):
        applied = Status.objects.get(name="Applied")
        self.assertEqual(api(self.client, "patch", f"/jobs/{self.job_b.pk}/status", {"status": applied.pk}).status_code, 404)
        self.assertEqual(api(self.client, "post", f"/jobs/{self.job_b.pk}/evaluate").status_code, 404)
        self.job_b.refresh_from_db()
        self.assertEqual(self.job_b.status.name, "Evaluated")
        self.assertIsNone(self.job_b.score)

    def test_cannot_read_or_push_someone_elses_document(self):
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            doc = Document(application=self.job_b, kind=DocumentKind.objects.get(name="CV"), title="bob cv")
            doc.file.save("bob.pdf", ContentFile(b"%PDF-1.4 bob"), save=True)
            self.assertEqual(self.client.get(reverse("document_file", args=[doc.pk])).status_code, 404)

    def test_cannot_touch_someone_elses_knowledge(self):
        src = KnowledgeSource.objects.create(owner=self.b, title="Bob notes", text="private")
        self.assertEqual(api(self.client, "post", f"/documents/{src.pk}/toggle").status_code, 404)
        self.assertEqual(api(self.client, "delete", f"/documents/{src.pk}").status_code, 404)
        self.assertTrue(KnowledgeSource.objects.filter(pk=src.pk, enabled=True).exists())
        self.assertNotIn("Bob notes", json.dumps(api(self.client, "get", "/documents").json()))

    def test_export_contains_only_my_data_and_no_secrets(self):
        UserProfile.objects.get(user=self.a).set_ai_key("sk-alice-secret")
        profile = UserProfile.objects.get(user=self.a)
        profile.set_ai_key("sk-alice-secret")
        profile.set_rag_key("emb-alice-secret")
        profile.save()
        text = self.client.get(reverse("export_data")).content.decode()
        data = json.loads(text)
        self.assertEqual([a["company"] for a in data["applications"]], ["AliceCo"])
        self.assertNotIn("BobCo", text)
        self.assertNotIn("bob@example.com", text)
        self.assertNotIn("sk-alice-secret", text)
        self.assertNotIn("emb-alice-secret", text)
        self.assertNotIn("encrypted", text.lower())
        self.assertEqual(data["account"]["username"], "alice")

    def test_liveness_runs_are_per_person(self):
        LivenessRun.objects.create(owner=self.b, total=9, done=4, running=True)
        data = api(self.client, "get", "/liveness/status").json()
        self.assertEqual(data["total"], 0)  # Bob's run is not Alice's

    def test_scan_runs_and_results_are_per_person(self):
        JobSource.objects.create(name="Acme", connector="greenhouse", board_token="acme", enabled=True)
        other_run = ScanRun.objects.create(owner=self.b, total=9, done=4, running=True)
        data = api(self.client, "get", "/scan/status").json()
        self.assertEqual(data["total"], 0)  # Bob's run is not Alice's
        with mock.patch("tracker.services.scan.fetch_greenhouse") as fetch:
            fetch.return_value = [{"title": "Senior Backend Engineer", "url": "https://x.test/1", "location": ""}]
            scan.start_run(self.a, background=False)
        self.assertFalse(Application.objects.filter(owner=self.b, company="Acme").exists())
        other_run.refresh_from_db()
        self.assertEqual(other_run.added, 0)  # Alice's scan never touched Bob's run or data

    def test_anonymous_visitors_reach_nothing_private(self):
        self.client.logout()
        for path in ("/app/", "/profile/export/", "/document/1/", "/cv/1/print/", "/cv/1/download/md/", "/cover/1/download/txt/"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 302, path)
            self.assertIn("/accounts/login/", r["Location"])
        for path in ("/me", "/dashboard", "/scan/status", "/postings", "/profile", "/ai-settings", "/documents", "/cv", "/interviews", "/offers"):
            self.assertEqual(api(self.client, "get", path).status_code, 401, path)
        for path in (f"/jobs/{self.job_a.pk}/evaluate", "/liveness", "/scan", "/account/delete", "/import", "/postings/1/add"):
            self.assertEqual(api(self.client, "post", path).status_code, 401, path)
        self.assertEqual(api(self.client, "patch", f"/jobs/{self.job_a.pk}/status", {"status": 1}).status_code, 401)

    def test_all_postings_never_shows_someone_elses_tracked_status(self):
        from tracker.models import JobSource, Posting
        from tracker.services import scan

        src = JobSource.objects.create(name="Acme", connector="greenhouse", board_token="acme", enabled=True)
        p = scan.record_sighting(src, "Backend Engineer", "https://x.test/shared", "Remote", company="Acme")
        job(self.b, url="https://x.test/shared", role="Backend Engineer")  # Bob tracked it
        data = api(self.client, "get", "/postings").json()  # Alice, who hasn't
        self.assertEqual(len(data["postings"]), 1)
        self.assertFalse(data["postings"][0]["tracked"])
        self.assertIsNone(data["postings"][0]["job_id"])


class StaffOnly(TestCase):
    def test_server_features_are_admin_only(self):
        normal = user("normal")
        self.client.force_login(normal)
        r = api(self.client, "post", "/import")
        self.assertEqual(r.status_code, 403)
        doc_app = job(normal)
        doc = Document.objects.create(application=doc_app, kind=DocumentKind.objects.get(name="CV"), title="x", source_path="/x")
        self.assertEqual(api(self.client, "post", f"/documents/files/{doc.pk}/paperless").status_code, 403)
        self.assertEqual(self.client.get("/admin/").status_code, 302)  # sent to the admin login, not in

    def test_dashboard_hides_server_features_from_normal_users(self):
        SiteConfig.objects.filter(pk=1).update(careerops_path="/srv/careerops", paperless_enabled=True, paperless_url="http://p.test")
        self.client.force_login(user("normal"))
        data = api(self.client, "get", "/dashboard").json()
        self.assertFalse(data["can_import"])
        self.assertFalse(data["paperless_on"])
        self.assertEqual(data["paperless_url"], "")
        self.assertNotIn("/srv/careerops", json.dumps(data))
        self.assertFalse(api(self.client, "get", "/me").json()["is_staff"])
        self.client.force_login(user("boss", staff=True))
        data = api(self.client, "get", "/dashboard").json()
        self.assertTrue(data["can_import"])
        self.assertTrue(api(self.client, "get", "/me").json()["is_staff"])

    def test_ai_quick_setup_local_presets_are_admin_only(self):
        self.client.force_login(user("boss2staff", staff=True))
        keys = {p["key"] for p in api(self.client, "get", "/ai-settings").json()["presets"]}
        self.assertTrue({"ollama", "lmstudio"} <= keys)


class PerUserConfig(TestCase):
    def test_overlay_and_read_only(self):
        u = user("zed", profile_cv="ZED CV", ai_provider="openai", rag_top_k=3, target_roles="Backend Engineer", remote_preference="remote")
        config = SiteConfig.for_user(u)
        self.assertEqual(config.profile_cv, "ZED CV")
        self.assertEqual(config.ai_provider, "openai")
        self.assertEqual(config.rag_top_k, 3)
        self.assertIn("Target roles: Backend Engineer", config.profile_preferences)
        self.assertIn("Remote only", config.profile_preferences)
        with self.assertRaises(RuntimeError):
            config.save()  # would overwrite the site's one SiteConfig row with one person's values
        self.assertNotEqual(SiteConfig.load().profile_cv, "ZED CV")

    def test_ordinary_users_are_restricted_admins_are_not(self):
        SiteConfig.objects.filter(pk=1).update(careerops_path="/srv/careerops", liveness_mode="node")
        normal = user("n", ai_provider="claude_cli")
        boss = user("b", staff=True, ai_provider="claude_cli")
        c = SiteConfig.for_user(normal)
        self.assertTrue(c.restricted)
        self.assertEqual(c.ai_provider, "none")  # cannot run commands on the server
        self.assertEqual((c.careerops_path, c.liveness_mode), ("", "http"))
        c2 = SiteConfig.for_user(boss)
        self.assertFalse(c2.restricted)
        self.assertEqual((c2.ai_provider, c2.careerops_path, c2.liveness_mode), ("claude_cli", "/srv/careerops", "node"))

    def test_two_people_keep_their_own_settings(self):
        a, b = user("a", profile_cv="A CV", rag_top_k=2), user("b", profile_cv="B CV", rag_top_k=9)
        self.assertEqual((SiteConfig.for_user(a).profile_cv, SiteConfig.for_user(a).rag_top_k), ("A CV", 2))
        self.assertEqual((SiteConfig.for_user(b).profile_cv, SiteConfig.for_user(b).rag_top_k), ("B CV", 9))

    def test_encrypted_keys_are_per_person(self):
        a, b = user("ka"), user("kb")
        pa = UserProfile.for_user(a)
        pa.set_ai_key("sk-only-alice")
        pa.save()
        self.assertEqual(SiteConfig.for_user(a).effective_ai_key, "sk-only-alice")
        self.assertEqual(SiteConfig.for_user(b).effective_ai_key, "")


class ServerSideRequestForgery(TestCase):
    def setUp(self):
        self.u = user("ssrf", profile_cv=CV)

    def config(self, **fields):
        UserProfile.objects.filter(user=self.u).update(**fields)
        return SiteConfig.for_user(self.u)

    def test_openai_compatible_blocks_private_addresses(self):
        for base in ["http://127.0.0.1:11434/v1", "http://localhost:8000/v1", "http://169.254.169.254/latest", "http://10.0.0.5/v1"]:
            config = self.config(ai_provider="openai", ai_base_url=base)
            with mock.patch("tracker.services.ai.requests.post") as post:
                with self.assertRaisesMessage(ai.AIError, "Blocked"):
                    ai._openai("s", "u", config)
                post.assert_not_called()

    def test_custom_http_blocks_private_addresses(self):
        config = self.config(
            ai_provider="custom_http", ai_base_url="http://169.254.169.254/latest/meta-data/",
            ai_custom_body='{"p": "{{prompt}}"}', ai_custom_response_path="x",
        )
        with mock.patch("tracker.services.ai.requests.post") as post:
            with self.assertRaisesMessage(ai.AIError, "Blocked"):
                ai._custom_http("s", "u", config)
            post.assert_not_called()

    def test_embeddings_block_private_addresses(self):
        config = self.config(rag_mode="embeddings", rag_embedding_base_url="http://127.0.0.1:11434/v1", rag_embedding_model="m")
        with mock.patch("tracker.services.knowledge.requests.post") as post:
            with self.assertRaises(knowledge.KnowledgeError):
                knowledge.embed_texts(["x"], config)
            post.assert_not_called()

    def test_admins_may_use_a_local_model(self):
        boss = user("boss2", staff=True, profile_cv=CV)
        UserProfile.objects.filter(user=boss).update(ai_provider="openai", ai_base_url="http://127.0.0.1:11434/v1", ai_model="m")
        config = SiteConfig.for_user(boss)
        reply = mock.Mock(status_code=200, json=lambda: {"choices": [{"message": {"content": "ok"}}]})
        with mock.patch("tracker.services.ai.requests.post", return_value=reply) as post:
            self.assertEqual(ai._openai("s", "u", config), "ok")
        self.assertEqual(post.call_args.args[0], "http://127.0.0.1:11434/v1/chat/completions")

    def test_ai_posts_never_follow_redirects(self):
        config = self.config(ai_provider="openai", ai_base_url="https://api.example.test/v1", ai_model="m")
        config.set_ai_key("k")
        reply = mock.Mock(status_code=200, json=lambda: {"choices": [{"message": {"content": "ok"}}]})
        with mock.patch("tracker.services.netguard.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]), \
             mock.patch("tracker.services.ai.requests.post", return_value=reply) as post:
            ai._openai("s", "u", config)
        self.assertIs(post.call_args.kwargs["allow_redirects"], False)

    def test_job_description_fetch_is_guarded(self):
        from tracker.services.jobtext import FetchError, fetch_description

        with self.assertRaises(FetchError):
            fetch_description("http://169.254.169.254/latest/meta-data/", SiteConfig.for_user(self.u))


class ProfilePages(TestCase):
    """Profile and AI settings are saved through the app's API (more rules in tests_api_account)."""

    def setUp(self):
        self.u = user("pat")
        self.client.force_login(self.u)

    def next_step(self):
        return api(self.client, "get", "/dashboard").json()["next_step"]

    def test_the_app_nudges_until_the_profile_is_complete(self):
        self.assertIn("Finish your profile", self.next_step()["headline"])
        api(self.client, "put", "/profile", {"target_roles": "Backend Engineer", "profile_cv": CV})
        step = self.next_step()
        self.assertFalse(step and "Finish your profile" in step["headline"])

    def test_the_nudge_names_exactly_what_is_missing(self):
        self.assertIn("the roles you want and your CV", self.next_step()["body"])
        api(self.client, "put", "/profile", {"target_roles": "Backend Engineer"})
        step = self.next_step()
        self.assertIn("Finish your profile", step["headline"])
        self.assertIn("your CV", step["body"])
        self.assertNotIn("the roles you want", step["body"])
        api(self.client, "put", "/profile", {"target_roles": "Backend Engineer", "profile_cv": CV})
        step = self.next_step()
        self.assertFalse(step and "Finish your profile" in step["headline"])

    def test_profile_saves_roles_and_cv(self):
        r = api(self.client, "put", "/profile", {
            "target_roles": "Backend Engineer\nSolutions Architect",
            "salary_floor": "100,000 BDT/month", "deal_breakers": "On-call", "about": "8 years", "profile_cv": CV,
        })
        self.assertEqual(r.status_code, 200, r.content)
        api(self.client, "post", "/profile/areas", {"place": "Anywhere", "allow_remote": True, "salary_period": "month"})
        p = UserProfile.objects.get(user=self.u)
        self.assertEqual(p.target_roles, "Backend Engineer\nSolutions Architect")
        text = p.preferences_text()
        for expected in ["Backend Engineer; Solutions Architect", "Anywhere: remote", "100,000 BDT/month", "On-call", "8 years"]:
            self.assertIn(expected, text)
        self.assertTrue(p.is_complete)
        self.assertEqual(api(self.client, "get", "/profile").json()["profile"]["target_roles"], "Backend Engineer\nSolutions Architect")

    def test_cv_upload_fills_the_cv_text_and_keeps_no_file(self):
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            r = self.client.post("/api/v1/profile", {
                "target_roles": "Dev", "profile_cv": "",
                "cv_file": SimpleUploadedFile("cv.txt", b"Uploaded CV about Rust and Go."),
            })
            self.assertEqual(r.status_code, 200, r.content)
            import os
            self.assertEqual(os.listdir(media), [])  # only the text is stored
        self.assertIn("Rust and Go", UserProfile.objects.get(user=self.u).profile_cv)

    def test_bad_cv_upload_is_rejected_with_a_reason(self):
        r = self.client.post("/api/v1/profile", {
            "target_roles": "Dev", "profile_cv": "",
            "cv_file": SimpleUploadedFile("cv.exe", b"MZ"),
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn("Upload a .txt, .md or .pdf file", r.json()["error"])

    def test_ai_settings_never_show_a_saved_key(self):
        r = api(self.client, "put", "/ai-settings", {"ai_provider": "anthropic", "ai_api_key": "sk-ant-visible-secret"})
        self.assertEqual(r.status_code, 200, r.content)
        profile = UserProfile.objects.get(user=self.u)
        self.assertNotIn("visible-secret", profile.ai_key_encrypted)
        self.assertEqual(profile.effective_ai_key, "sk-ant-visible-secret")
        text = api(self.client, "get", "/ai-settings").content.decode()
        self.assertNotIn("visible-secret", text)
        self.assertNotIn("visible-secret", r.content.decode())
        self.assertTrue(api(self.client, "get", "/ai-settings").json()["has_key"])

    def test_ai_settings_show_no_usage_yet_then_this_months_total(self):
        self.assertEqual(api(self.client, "get", "/ai-settings").json()["usage"]["calls"], 0)
        AIUsageEvent.objects.create(owner=self.u, provider="anthropic", purpose="evaluate", input_tokens=1000, output_tokens=200, cost_usd="0.0180", cost_is_estimate=True)
        usage = api(self.client, "get", "/ai-settings").json()["usage"]
        self.assertEqual((usage["calls"], usage["total_tokens"], usage["cost_usd"]), (1, 1200, 0.018))
        other = User.objects.create_user("otherAiUser", password=PW)
        AIUsageEvent.objects.create(owner=other, provider="anthropic", purpose="evaluate", input_tokens=99999, output_tokens=99999)
        self.assertEqual(api(self.client, "get", "/ai-settings").json()["usage"]["calls"], 1)  # the other person's usage never shows up here

    def _ai_put(self, **extra):
        data = {"ai_provider": "openai", "ai_model": "m"}
        data.update(extra)
        return api(self.client, "put", "/ai-settings", data)

    def test_ordinary_users_cannot_pick_server_side_providers_or_private_urls(self):
        for provider in ("claude_cli", "agent_sdk"):
            self.assertEqual(self._ai_put(ai_provider=provider).status_code, 400)  # form error, not saved
        for url in ["http://127.0.0.1:11434/v1", "http://169.254.169.254/", "http://localhost/v1", "ftp://x.test"]:
            self.assertEqual(self._ai_put(ai_base_url=url).status_code, 400, url)
        self.assertEqual(self._ai_put(rag_embedding_base_url="http://10.1.2.3/v1").status_code, 400)
        self.assertEqual(UserProfile.objects.get(user=self.u).ai_provider, "none")

    def test_settings_are_bounded(self):
        for field, value in [("ai_timeout", 100000), ("ai_max_input_chars", 99999999), ("rag_top_k", 500), ("rag_chunk_chars", 5)]:
            self.assertEqual(self._ai_put(**{field: value}).status_code, 400, field)

    def test_admins_can_pick_local_providers(self):
        self.client.force_login(user("root", staff=True))
        self.assertEqual(self._ai_put(ai_provider="claude_cli").status_code, 200)
        self.assertEqual(self._ai_put(ai_base_url="http://127.0.0.1:11434/v1").status_code, 200)


class AddingJobsAndDocuments(TestCase):
    def setUp(self):
        self.u = user("quinn", profile_cv=CV)
        self.client.force_login(self.u)

    def test_add_job_belongs_to_me_and_defaults_to_the_first_open_status(self):
        r = api(self.client, "post", "/jobs", {"company": "Globex", "role": "Backend", "url": "https://jobs.example.com/1", "description": JD})
        self.assertEqual(r.status_code, 200, r.content)
        app = Application.objects.get(company="Globex")
        self.assertEqual(app.owner, self.u)
        self.assertEqual(app.status.name, "Saved")
        self.assertTrue(app.events.exists())
        self.assertEqual([j["company"] for j in api(self.client, "get", "/dashboard").json()["jobs"]], ["Globex"])

    def test_add_job_validation(self):
        self.assertEqual(api(self.client, "post", "/jobs", {"company": "", "role": ""}).status_code, 400)
        self.assertEqual(api(self.client, "post", "/jobs", {"company": "A", "role": "B", "url": "javascript:alert(1)"}).status_code, 400)
        self.assertEqual(api(self.client, "post", "/jobs", {"company": "A", "role": "B", "description": "x" * 30001}).status_code, 400)
        self.assertFalse(Application.objects.filter(owner=self.u).exists())

    @override_settings(STILLOPEN_MAX_APPLICATIONS=2)
    def test_job_quota(self):
        for i in range(2):
            job(self.u, company=f"J{i}")
        r = api(self.client, "post", "/jobs", {"company": "Third", "role": "R"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("limit of 2", r.json()["error"])
        self.assertFalse(Application.objects.filter(company="Third").exists())

    @mock.patch("tracker.services.netguard.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))])
    @mock.patch("tracker.services.netguard.requests.get")
    def test_quickadd_reads_the_link_and_saves_nothing(self, get, _dns):
        get.return_value = mock.Mock(
            status_code=200, is_redirect=False, headers={},
            text="<html><head><title>Backend Engineer at Globex</title></head><body><p>" + "Real job text. " * 30 + "</p></body></html>",
        )
        r = api(self.client, "post", "/quickadd", {"url": "https://jobs.example.com/1"})
        self.assertEqual(r.json()["ok"], True)
        self.assertIn("Globex", json.dumps(r.json()))
        self.assertIn("Real job text", json.dumps(r.json()))
        self.assertFalse(Application.objects.filter(owner=self.u).exists())  # the person still reviews and submits the form

    def test_quickadd_requires_a_url_and_is_throttled(self):
        self.assertEqual(api(self.client, "post", "/quickadd", {}).status_code // 100, 4)
        with override_settings(STILLOPEN_QUICKADD_PER_HOUR=1):
            cache.clear()
            with mock.patch("tracker.api.jobs.tracking.fetch_prefill", side_effect=jobtext.FetchError("nope")):
                self.assertEqual(api(self.client, "post", "/quickadd", {"url": "https://x.example.com"}).status_code, 400)
                self.assertEqual(api(self.client, "post", "/quickadd", {"url": "https://x.example.com"}).status_code, 429)

    def test_knowledge_add_toggle_delete_and_no_file_kept(self):
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            r = self.client.post("/api/v1/documents", {
                "title": "Projects", "kind": "project", "text": "",
                "file": SimpleUploadedFile("notes.md", b"# Projects\nBuilt a Kubernetes platform with Helm."),
            })
            self.assertEqual(r.status_code, 200, r.content)
            import os
            self.assertEqual(os.listdir(media), [])
        src = KnowledgeSource.objects.get(owner=self.u, title="Projects")
        self.assertIn("Kubernetes", src.text)
        self.assertFalse(src.file)
        self.assertGreaterEqual(src.chunks.count(), 1)
        api(self.client, "post", f"/documents/{src.pk}/toggle")
        src.refresh_from_db()
        self.assertFalse(src.enabled)
        self.assertEqual(src.chunks.count(), 0)  # hidden sources contribute nothing
        api(self.client, "delete", f"/documents/{src.pk}")
        self.assertFalse(KnowledgeSource.objects.filter(pk=src.pk).exists())

    @override_settings(STILLOPEN_MAX_KNOWLEDGE=1)
    def test_knowledge_quota_and_empty_rejection(self):
        self.assertEqual(api(self.client, "post", "/documents", {"title": "Empty", "kind": "other", "text": ""}).status_code, 400)
        api(self.client, "post", "/documents", {"title": "One", "kind": "other", "text": "something"})
        r = api(self.client, "post", "/documents", {"title": "Two", "kind": "other", "text": "more"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("limit of 1", r.json()["error"])
        self.assertEqual(KnowledgeSource.objects.filter(owner=self.u, key=None).count(), 1)


class AccountDeletion(TestCase):
    def test_deleting_my_account_removes_my_data_files_and_nothing_else(self):
        me, other = user("leaver", profile_cv=CV), user("stayer", profile_cv=CV)
        mine, theirs = job(me, company="MineCo"), job(other, company="TheirsCo")
        KnowledgeSource.objects.create(owner=me, title="mine", text="x")
        KnowledgeSource.objects.create(owner=other, title="theirs", text="y")
        Event.objects.create(application=mine, text="note")
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            doc = Document(application=mine, kind=DocumentKind.objects.get(name="CV"), title="cv")
            doc.file.save("leaver.pdf", ContentFile(b"%PDF-1.4"), save=True)
            path = doc.file.path
            import os
            self.assertTrue(os.path.exists(path))
            self.client.force_login(me)
            api(self.client, "post", "/account/delete", {"confirm": "wrong"})
            self.assertTrue(User.objects.filter(username="leaver").exists())  # needs the exact username
            r = api(self.client, "post", "/account/delete", {"confirm": "leaver"})
            self.assertEqual(r.status_code, 200)
            self.assertFalse(os.path.exists(path))  # the stored file is deleted too
        self.assertFalse(User.objects.filter(username="leaver").exists())
        self.assertFalse(Application.objects.filter(company="MineCo").exists())
        self.assertFalse(KnowledgeSource.objects.filter(title="mine").exists())
        self.assertFalse(UserProfile.objects.filter(user_id=me.pk).exists())
        self.assertTrue(Application.objects.filter(pk=theirs.pk).exists())
        self.assertTrue(KnowledgeSource.objects.filter(title="theirs").exists())
        self.assertEqual(api(self.client, "get", "/me").status_code, 401)  # logged out

    def test_admin_accounts_cannot_delete_themselves_here(self):
        boss = user("boss3", staff=True)
        self.client.force_login(boss)
        api(self.client, "post", "/account/delete", {"confirm": "boss3"})
        self.assertTrue(User.objects.filter(username="boss3").exists())

    def test_get_does_not_delete(self):
        me = user("careful")
        self.client.force_login(me)
        self.assertEqual(api(self.client, "get", "/account/delete").status_code, 405)
        self.assertTrue(User.objects.filter(username="careful").exists())


class Throttling(TestCase):
    def setUp(self):
        cache.clear()

    @override_settings(STILLOPEN_EVALS_PER_HOUR=2)
    def test_evaluations_are_rate_limited_per_person(self):
        a, b = user("ta", profile_cv=CV), user("tb", profile_cv=CV)
        ja = job(a, description=JD)
        jb = job(b, description=JD)
        self.client.force_login(a)
        codes = [api(self.client, "post", f"/jobs/{ja.pk}/evaluate").status_code for _ in range(3)]
        self.assertEqual(codes[2], 429)
        self.assertNotEqual(codes[0], 429)
        self.client.force_login(b)  # Alice's limit does not use up Bob's
        self.assertNotEqual(api(self.client, "post", f"/jobs/{jb.pk}/evaluate").status_code, 429)


@override_settings(STILLOPEN_SIGNUP_MIN_SECONDS=0, ACCOUNT_RATE_LIMITS={"signup": "1000/m/ip"})
class Registration(TestCase):
    def signup(self, name="newbie", email="newbie@example.com"):
        return self.client.post(reverse("account_signup"), {"email": email, "username": name, "password1": PW, "password2": PW})

    def test_closed_by_default(self):
        r = self.client.get(reverse("account_signup"))
        self.assertContains(r, "Sign Up Closed")
        self.assertFalse(User.objects.filter(username="newbie").exists())
        self.signup()
        self.assertFalse(User.objects.filter(username="newbie").exists())
        self.assertNotContains(self.client.get(reverse("landing")), "Create a free account")

    def test_open_signup_needs_a_confirmed_email_then_works(self):
        SiteConfig.objects.filter(pk=1).update(signup_mode="open")
        self.assertContains(self.client.get(reverse("landing")), "Create a free account")
        self.assertContains(self.client.get(reverse("account_login")), "Create an account")
        self.assertContains(self.client.get(reverse("account_signup")), "Create your account")
        self.signup()
        newbie = User.objects.get(username="newbie")
        self.assertFalse(newbie.is_staff or newbie.is_superuser)
        self.assertEqual(len(mail.outbox), 1)
        # cannot get in before confirming the address
        r = self.client.post(reverse("account_login"), {"login": "newbie", "password": PW})
        self.assertFalse(signed_in(self.client))
        link = re.search(r"https?://[^\s]+/accounts/confirm-email/[^\s/]+/", mail.outbox[0].body).group(0)
        path = "/" + link.split("/", 3)[3]
        # the link alone confirms the address, signs the person in and lands them on the welcome page
        self.assertRedirects(self.client.get(path), "/app/welcome", fetch_redirect_response=False)
        self.assertTrue(signed_in(self.client))
        self.assertTrue(UserProfile.objects.filter(user=newbie).exists())

    def test_duplicate_email_is_refused(self):
        SiteConfig.objects.filter(pk=1).update(signup_mode="open")
        user("first")
        self.signup(name="second", email="first@example.com")
        self.assertFalse(User.objects.filter(username="second").exists())

    def test_users_made_in_the_admin_or_cli_can_still_sign_in(self):
        """createsuperuser makes no confirmed email; the owner must never be locked out."""
        SiteConfig.objects.filter(pk=1).update(signup_mode="open")
        User.objects.create_superuser("owner", password=PW)  # no email at all
        User.objects.create_user("legacy", email="legacy@example.com", password=PW)  # has an email, never confirmed
        for name in ("owner", "legacy"):
            self.client.logout()
            self.client.post(reverse("account_login"), {"login": name, "password": PW})
            self.assertTrue(signed_in(self.client), name)

    def test_unconfirmed_self_registered_accounts_stay_blocked_and_get_a_new_link(self):
        SiteConfig.objects.filter(pk=1).update(signup_mode="open")
        self.signup()
        self.assertEqual(len(mail.outbox), 1)  # exactly one confirmation mail at sign-up
        self.assertTrue(UserProfile.objects.get(user__username="newbie").self_registered)
        self.client.logout()
        for _ in range(2):
            self.client.post(reverse("account_login"), {"login": "newbie", "password": PW})
            self.assertFalse(signed_in(self.client))
        self.assertEqual(len(mail.outbox), 3)  # each blocked attempt sends a fresh link

    def test_the_admin_site_is_not_a_way_around_confirmation(self):
        SiteConfig.objects.filter(pk=1).update(signup_mode="open")
        self.signup()
        self.client.logout()
        self.client.post("/admin/login/?next=/admin/", {"username": "newbie", "password": PW})
        self.assertEqual(self.client.get("/admin/").status_code, 302)  # not staff either way


class GoogleRegistration(TestCase):
    def sociallogin(self, email, verified=True):
        from allauth.account.models import EmailAddress
        from allauth.socialaccount.models import SocialAccount, SocialLogin

        return SocialLogin(user=User(email=email), account=SocialAccount(provider="google", uid="1"),
                           email_addresses=[EmailAddress(email=email, verified=verified)])

    def request(self):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        r = RequestFactory().get("/")
        r.session = {}
        r._messages = FallbackStorage(r)
        return r

    def test_closed_needs_the_allowlist_open_admits_any_verified_email(self):
        from tracker.auth import SocialAdapter

        adapter = SocialAdapter()
        SiteConfig.objects.filter(pk=1).update(google_login_enabled=True, google_allowed_emails="me@gmail.com", signup_mode="closed")
        self.assertTrue(adapter.is_open_for_signup(self.request(), self.sociallogin("me@gmail.com")))
        self.assertFalse(adapter.is_open_for_signup(self.request(), self.sociallogin("anyone@gmail.com")))
        SiteConfig.objects.filter(pk=1).update(signup_mode="open")
        self.assertTrue(adapter.is_open_for_signup(self.request(), self.sociallogin("anyone@gmail.com")))
        self.assertFalse(adapter.is_open_for_signup(self.request(), self.sociallogin("anyone@gmail.com", verified=False)))
        SiteConfig.objects.filter(pk=1).update(google_login_enabled=False)
        self.assertFalse(adapter.is_open_for_signup(self.request(), self.sociallogin("anyone@gmail.com")))


class FirstAccountAndCommands(TestCase):
    def test_first_account_inherits_data_from_before_accounts_existed(self):
        legacy = job(None, company="Legacy Co", description=JD)
        KnowledgeSource.objects.create(owner=None, title="legacy notes", text="x")
        SiteConfig.objects.filter(pk=1).update(profile_cv="LEGACY CV", ai_provider="openai", profile_preferences="remote only")
        first = User.objects.create_superuser("owner", password=PW)
        legacy.refresh_from_db()
        self.assertEqual(legacy.owner, first)
        self.assertEqual(KnowledgeSource.objects.get(title="legacy notes").owner, first)
        profile = UserProfile.objects.get(user=first)
        self.assertEqual((profile.profile_cv, profile.ai_provider, profile.about), ("LEGACY CV", "openai", "remote only"))

    def test_later_accounts_get_nothing_inherited(self):
        User.objects.create_superuser("owner", password=PW)
        orphan = job(None, company="Late orphan")
        second = user("second")
        orphan.refresh_from_db()
        self.assertIsNone(orphan.owner)
        self.assertEqual(Application.objects.filter(owner=second).count(), 0)

    def test_claim_data_command(self):
        User.objects.create_superuser("owner", password=PW)
        orphan = job(None, company="Orphan")
        out = StringIO()
        call_command("claim_data", "owner", stdout=out)
        orphan.refresh_from_db()
        self.assertEqual(orphan.owner.username, "owner")
        self.assertIn("1 application", out.getvalue())

    def test_commands_refuse_to_guess_between_users(self):
        User.objects.create_superuser("one", password=PW)
        User.objects.create_superuser("two", password=PW)
        with self.assertRaises(who.WhoError):
            who.resolve_user(None)
        with self.assertRaises(CommandError):
            call_command("evaluate_jobs")
        with self.assertRaises(CommandError):
            call_command("evaluate_jobs", "--user", "nobody")
        self.assertEqual(who.resolve_user("two").username, "two")

    def test_commands_default_to_the_only_superuser(self):
        owner = User.objects.create_superuser("only", password=PW)
        user("plain")
        self.assertEqual(who.resolve_user(None), owner)

    def test_commands_act_only_for_the_chosen_user(self):
        a, b = user("ca", profile_cv=CV), user("cb", profile_cv=CV)
        ja, jb = job(a, description=JD), job(b, description=JD)
        call_command("evaluate_jobs", "--user", "ca", stdout=StringIO())
        ja.refresh_from_db()
        jb.refresh_from_db()
        self.assertIsNotNone(ja.score)
        self.assertIsNone(jb.score)

    def test_import_command_is_admin_only(self):
        user("regular")
        with self.assertRaises(CommandError):
            call_command("import_careerops", "--user", "regular")


class PublicPages(TestCase):
    def test_privacy_and_terms_are_public_and_editable(self):
        SiteConfig.objects.filter(pk=1).update(privacy_text="We keep nothing but your jobs.")
        r = self.client.get(reverse("privacy"))
        self.assertContains(r, "We keep nothing but your jobs.")
        self.assertEqual(self.client.get(reverse("terms")).status_code, 200)
        self.assertContains(self.client.get(reverse("landing")), reverse("privacy"))

    def test_legal_text_is_escaped(self):
        SiteConfig.objects.filter(pk=1).update(terms_text="<script>alert(1)</script>")
        self.assertNotContains(self.client.get(reverse("terms")), "<script>alert(1)</script>")


class WebAssistantTokens(TestCase):
    """The web MCP endpoint acts as the token's owner only; the full set of checks is in tests_mcp_http.py."""

    def test_a_token_never_reaches_another_persons_data(self):
        from django.urls import reverse
        import json

        a, b = User.objects.create_user("tok-a", password="x" * 20), User.objects.create_user("tok-b", password="x" * 20)
        status = Status.objects.get(name="Evaluated")
        Application.objects.create(owner=a, company="OnlyAnnCo", role="R", status=status)
        Application.objects.create(owner=b, company="OnlyBobCo", role="R", status=status)
        from tracker.models import ApiToken

        _, raw = ApiToken.issue(b, "b", can_write=True)
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_applications", "arguments": {}}}
        r = self.client.post(reverse("mcp_endpoint"), data=json.dumps(body), content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {raw}")
        text = json.dumps(r.json())
        self.assertIn("OnlyBobCo", text)
        self.assertNotIn("OnlyAnnCo", text)


class PrepPlanIsolation(TestCase):
    """Prep plans belong to one person; the full set of checks is in tests_prep.py."""

    def test_another_persons_plan_is_a_404_and_stays_out_of_my_list(self):
        from tracker.models import PrepPlan

        a, b = User.objects.create_user("prep-a", password="x" * 20), User.objects.create_user("prep-b", password="x" * 20)
        plan = PrepPlan.objects.create(owner=a, title="Only A", status="draft")
        self.client.force_login(b)
        self.assertEqual(api(self.client, "get", f"/prep/plans/{plan.pk}").status_code, 404)
        self.assertEqual(api(self.client, "post", f"/prep/plans/{plan.pk}/start").status_code, 404)
        self.assertNotIn("Only A", json.dumps(api(self.client, "get", "/prep/plans").json()))
