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
    Application, Document, DocumentKind, Event, JobSource, KnowledgeSource, LivenessRun, ScanRun, SiteConfig, Status,
    UserProfile,
)
from tracker.services import ai, claim, knowledge, scan, who

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


class Isolation(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = user("alice", profile_cv=CV), user("bob", profile_cv=CV)
        self.job_a = job(self.a, company="AliceCo", description=JD, summary="alice summary")
        self.job_b = job(self.b, company="BobCo", description=JD, summary="bob summary")
        self.client.force_login(self.a)

    def test_dashboard_shows_only_my_jobs(self):
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "AliceCo")
        self.assertNotContains(r, "BobCo")
        self.assertNotContains(r, "bob summary")
        self.assertContains(r, "Tracked roles")

    def test_cannot_act_on_someone_elses_job(self):
        applied = Status.objects.get(name="Applied")
        self.assertEqual(self.client.post(reverse("set_status", args=[self.job_b.pk]), {"status": applied.pk}).status_code, 404)
        self.assertEqual(self.client.post(reverse("evaluate", args=[self.job_b.pk])).status_code, 404)
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
        for action in ("delete", "toggle"):
            self.assertEqual(self.client.post(reverse("knowledge_action", args=[src.pk, action])).status_code, 404)
        self.assertTrue(KnowledgeSource.objects.filter(pk=src.pk, enabled=True).exists())
        self.assertNotContains(self.client.get(reverse("knowledge")), "Bob notes")

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
        data = self.client.get(reverse("liveness_status")).json()
        self.assertEqual(data["total"], 0)  # Bob's run is not Alice's

    def test_scan_runs_and_results_are_per_person(self):
        JobSource.objects.create(name="Acme", connector="greenhouse", board_token="acme", enabled=True)
        other_run = ScanRun.objects.create(owner=self.b, total=9, done=4, running=True)
        data = self.client.get(reverse("scan_status")).json()
        self.assertEqual(data["total"], 0)  # Bob's run is not Alice's
        with mock.patch("tracker.services.scan.fetch_greenhouse") as fetch:
            fetch.return_value = [{"title": "Senior Backend Engineer", "url": "https://x.test/1", "location": ""}]
            scan.start_run(self.a, background=False)
        self.assertFalse(Application.objects.filter(owner=self.b, company="Acme").exists())
        other_run.refresh_from_db()
        self.assertEqual(other_run.added, 0)  # Alice's scan never touched Bob's run or data

    def test_anonymous_visitors_reach_nothing_private(self):
        self.client.logout()
        for name, args in [("dashboard", []), ("profile", []), ("profile_ai", []), ("knowledge", []), ("add_job", []),
                           ("export_data", []), ("document_file", [1]), ("scan_status", [])]:
            r = self.client.get(reverse(name, args=args))
            self.assertEqual(r.status_code, 302, name)
            self.assertIn("/accounts/login/", r["Location"])
        for name, args in [("set_status", [self.job_a.pk]), ("evaluate", [self.job_a.pk]), ("liveness_start", []),
                           ("scan_start", []), ("delete_account", []), ("import_tracker", [])]:
            self.assertEqual(self.client.post(reverse(name, args=args)).status_code, 302, name)


class StaffOnly(TestCase):
    def test_server_features_are_admin_only(self):
        normal = user("normal")
        self.client.force_login(normal)
        r = self.client.post(reverse("import_tracker"))
        self.assertEqual(r.status_code, 403)
        self.assertFalse(r.json()["ok"])
        doc_app = job(normal)
        doc = Document.objects.create(application=doc_app, kind=DocumentKind.objects.get(name="CV"), title="x", source_path="/x")
        self.assertEqual(self.client.post(reverse("push_to_paperless", args=[doc.pk])).status_code, 403)
        self.assertEqual(self.client.get("/admin/").status_code, 302)  # sent to the admin login, not in

    def test_dashboard_hides_server_buttons_from_normal_users(self):
        SiteConfig.objects.filter(pk=1).update(careerops_path="/srv/careerops", paperless_enabled=True, paperless_url="http://p.test")
        self.client.force_login(user("normal"))
        page = self.client.get(reverse("dashboard")).content.decode()
        self.assertFalse('id="btn-import"' in page)
        self.assertFalse("/srv/careerops" in page)
        self.assertFalse("Admin</a>" in page)
        self.client.force_login(user("boss", staff=True))
        page = self.client.get(reverse("dashboard")).content.decode()
        self.assertTrue('id="btn-import"' in page)
        self.assertTrue("Admin</a>" in page)


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
    def setUp(self):
        self.u = user("pat")
        self.client.force_login(self.u)

    def test_dashboard_nudges_until_the_profile_is_complete(self):
        self.assertContains(self.client.get(reverse("dashboard")), "Finish your profile")
        self.client.post(reverse("profile"), {
            "target_roles": "Backend Engineer", "locations": "Dhaka", "remote_preference": "any", "profile_cv": CV,
        })
        self.assertNotContains(self.client.get(reverse("dashboard")), "Finish your profile")

    def test_banner_names_exactly_what_is_missing(self):
        # Neither set yet: both named.
        self.assertContains(self.client.get(reverse("dashboard")), "the roles you want and your CV")
        # Only target_roles set: banner should name just the CV, not both.
        self.client.post(reverse("profile"), {"target_roles": "Backend Engineer"})
        r = self.client.get(reverse("dashboard"))
        self.assertContains(r, "Finish your profile")
        self.assertContains(r, "your CV")
        self.assertNotContains(r, "the roles you want")
        # Both set: banner gone.
        self.client.post(reverse("profile"), {"target_roles": "Backend Engineer", "profile_cv": CV})
        self.assertNotContains(self.client.get(reverse("dashboard")), "Finish your profile")

    def test_profile_saves_roles_and_cv(self):
        r = self.client.post(reverse("profile"), {
            "target_roles": "Backend Engineer\nSolutions Architect",
            "salary_floor": "100,000 BDT/month", "deal_breakers": "On-call", "about": "8 years", "profile_cv": CV,
            "areas-TOTAL_FORMS": 1, "areas-INITIAL_FORMS": 0, "areas-MIN_NUM_FORMS": 0, "areas-MAX_NUM_FORMS": 25,
            "areas-0-place": "Anywhere", "areas-0-allow_remote": "on", "areas-0-salary_period": "month",
        })
        self.assertEqual(r.status_code, 302)
        p = UserProfile.objects.get(user=self.u)
        self.assertEqual(p.target_roles, "Backend Engineer\nSolutions Architect")
        text = p.preferences_text()
        for expected in ["Backend Engineer; Solutions Architect", "Anywhere: remote", "100,000 BDT/month", "On-call", "8 years"]:
            self.assertIn(expected, text)
        self.assertTrue(p.is_complete)
        self.assertContains(self.client.get(reverse("profile")), "Backend Engineer")

    def test_cv_upload_fills_the_cv_text_and_keeps_no_file(self):
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            r = self.client.post(reverse("profile"), {
                "target_roles": "Dev", "remote_preference": "any", "profile_cv": "",
                "cv_file": SimpleUploadedFile("cv.txt", b"Uploaded CV about Rust and Go."),
            })
            self.assertEqual(r.status_code, 302)
            import os
            self.assertEqual(os.listdir(media), [])  # only the text is stored
        self.assertIn("Rust and Go", UserProfile.objects.get(user=self.u).profile_cv)

    def test_bad_cv_upload_is_rejected_with_a_reason(self):
        r = self.client.post(reverse("profile"), {
            "target_roles": "Dev", "remote_preference": "any", "profile_cv": "",
            "cv_file": SimpleUploadedFile("cv.exe", b"MZ"),
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Upload a .txt, .md or .pdf file")

    def test_ai_page_never_shows_a_saved_key(self):
        r = self.client.post(reverse("profile_ai"), {
            "ai_provider": "anthropic", "ai_model": "", "ai_base_url": "", "ai_custom_headers": "", "ai_custom_body": "",
            "ai_custom_response_path": "", "ai_timeout": 60, "ai_max_input_chars": 8000, "rag_enabled": "on", "rag_mode": "lexical",
            "rag_top_k": 5, "rag_chunk_chars": 900, "rag_always_chars": 1500, "rag_embedding_base_url": "", "rag_embedding_model": "",
            "ai_api_key": "sk-ant-visible-secret",
        })
        self.assertEqual(r.status_code, 302)
        profile = UserProfile.objects.get(user=self.u)
        self.assertNotIn("visible-secret", profile.ai_key_encrypted)
        self.assertEqual(profile.effective_ai_key, "sk-ant-visible-secret")
        page = self.client.get(reverse("profile_ai")).content.decode()
        self.assertNotIn("visible-secret", page)
        self.assertIn("saved", page)

    def _ai_post(self, **extra):
        data = {
            "ai_provider": "openai", "ai_model": "m", "ai_base_url": "", "ai_custom_headers": "", "ai_custom_body": "",
            "ai_custom_response_path": "", "ai_timeout": 60, "ai_max_input_chars": 8000, "rag_enabled": "on", "rag_mode": "lexical",
            "rag_top_k": 5, "rag_chunk_chars": 900, "rag_always_chars": 1500, "rag_embedding_base_url": "", "rag_embedding_model": "",
        }
        data.update(extra)
        return self.client.post(reverse("profile_ai"), data)

    def test_ordinary_users_cannot_pick_server_side_providers_or_private_urls(self):
        for provider in ("claude_cli", "agent_sdk"):
            self.assertEqual(self._ai_post(ai_provider=provider).status_code, 200)  # form error, not saved
        for url in ["http://127.0.0.1:11434/v1", "http://169.254.169.254/", "http://localhost/v1", "ftp://x.test"]:
            self.assertEqual(self._ai_post(ai_base_url=url).status_code, 200, url)
        self.assertEqual(self._ai_post(rag_embedding_base_url="http://10.1.2.3/v1").status_code, 200)
        self.assertEqual(UserProfile.objects.get(user=self.u).ai_provider, "none")

    def test_settings_are_bounded(self):
        for field, value in [("ai_timeout", 100000), ("ai_max_input_chars", 99999999), ("rag_top_k", 500), ("rag_chunk_chars", 5)]:
            self.assertEqual(self._ai_post(**{field: value}).status_code, 200, field)

    def test_admins_can_pick_local_providers(self):
        self.client.force_login(user("root", staff=True))
        self.assertEqual(self._ai_post(ai_provider="claude_cli").status_code, 302)
        self.assertEqual(self._ai_post(ai_base_url="http://127.0.0.1:11434/v1").status_code, 302)


class AddingJobsAndDocuments(TestCase):
    def setUp(self):
        self.u = user("quinn", profile_cv=CV)
        self.client.force_login(self.u)

    def test_add_job_belongs_to_me_and_defaults_to_the_first_open_status(self):
        r = self.client.post(reverse("add_job"), {"company": "Globex", "role": "Backend", "url": "https://jobs.example.com/1", "description": JD})
        self.assertEqual(r.status_code, 302)
        app = Application.objects.get(company="Globex")
        self.assertEqual(app.owner, self.u)
        self.assertEqual(app.status.name, "Evaluated")
        self.assertTrue(app.events.exists())
        self.assertContains(self.client.get(reverse("dashboard")), "Globex")

    def test_add_job_validation(self):
        self.assertEqual(self.client.post(reverse("add_job"), {"company": "", "role": ""}).status_code, 200)
        self.assertEqual(self.client.post(reverse("add_job"), {"company": "A", "role": "B", "url": "javascript:alert(1)"}).status_code, 200)
        self.assertEqual(self.client.post(reverse("add_job"), {"company": "A", "role": "B", "description": "x" * 30001}).status_code, 200)
        self.assertFalse(Application.objects.filter(owner=self.u).exists())

    @override_settings(STILLOPEN_MAX_APPLICATIONS=2)
    def test_job_quota(self):
        for i in range(2):
            job(self.u, company=f"J{i}")
        r = self.client.post(reverse("add_job"), {"company": "Third", "role": "R"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "limit of 2")
        self.assertFalse(Application.objects.filter(company="Third").exists())

    def test_knowledge_add_toggle_delete_and_no_file_kept(self):
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            r = self.client.post(reverse("knowledge"), {
                "title": "Projects", "kind": "project", "text": "",
                "file": SimpleUploadedFile("notes.md", b"# Projects\nBuilt a Kubernetes platform with Helm."),
            })
            self.assertEqual(r.status_code, 302)
            import os
            self.assertEqual(os.listdir(media), [])
        src = KnowledgeSource.objects.get(owner=self.u, title="Projects")
        self.assertIn("Kubernetes", src.text)
        self.assertFalse(src.file)
        self.assertGreaterEqual(src.chunks.count(), 1)
        self.client.post(reverse("knowledge_action", args=[src.pk, "toggle"]))
        src.refresh_from_db()
        self.assertFalse(src.enabled)
        self.assertEqual(src.chunks.count(), 0)  # hidden sources contribute nothing
        self.client.post(reverse("knowledge_action", args=[src.pk, "delete"]))
        self.assertFalse(KnowledgeSource.objects.filter(pk=src.pk).exists())

    @override_settings(STILLOPEN_MAX_KNOWLEDGE=1)
    def test_knowledge_quota_and_empty_rejection(self):
        self.assertEqual(self.client.post(reverse("knowledge"), {"title": "Empty", "kind": "other", "text": ""}).status_code, 200)
        self.client.post(reverse("knowledge"), {"title": "One", "kind": "other", "text": "something"})
        r = self.client.post(reverse("knowledge"), {"title": "Two", "kind": "other", "text": "more"})
        self.assertContains(r, "limit of 1")
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
            self.client.post(reverse("delete_account"), {"confirm": "wrong"})
            self.assertTrue(User.objects.filter(username="leaver").exists())  # needs the exact username
            r = self.client.post(reverse("delete_account"), {"confirm": "leaver"})
            self.assertEqual(r.status_code, 302)
            self.assertFalse(os.path.exists(path))  # the stored file is deleted too
        self.assertFalse(User.objects.filter(username="leaver").exists())
        self.assertFalse(Application.objects.filter(company="MineCo").exists())
        self.assertFalse(KnowledgeSource.objects.filter(title="mine").exists())
        self.assertFalse(UserProfile.objects.filter(user_id=me.pk).exists())
        self.assertTrue(Application.objects.filter(pk=theirs.pk).exists())
        self.assertTrue(KnowledgeSource.objects.filter(title="theirs").exists())
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)  # logged out

    def test_admin_accounts_cannot_delete_themselves_here(self):
        boss = user("boss3", staff=True)
        self.client.force_login(boss)
        self.client.post(reverse("delete_account"), {"confirm": "boss3"})
        self.assertTrue(User.objects.filter(username="boss3").exists())

    def test_get_does_not_delete(self):
        me = user("careful")
        self.client.force_login(me)
        self.assertEqual(self.client.get(reverse("delete_account")).status_code, 405)
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
        codes = [self.client.post(reverse("evaluate", args=[ja.pk])).status_code for _ in range(3)]
        self.assertEqual(codes[2], 429)
        self.assertNotEqual(codes[0], 429)
        self.client.force_login(b)  # Alice's limit does not use up Bob's
        self.assertNotEqual(self.client.post(reverse("evaluate", args=[jb.pk])).status_code, 429)


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
        self.assertNotEqual(self.client.get(reverse("dashboard")).status_code, 200)
        link = re.search(r"https?://[^\s]+/accounts/confirm-email/[^\s/]+/", mail.outbox[0].body).group(0)
        path = "/" + link.split("/", 3)[3]
        self.assertEqual(self.client.get(path).status_code, 200)
        self.client.post(path)
        self.client.post(reverse("account_login"), {"login": "newbie", "password": PW})
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
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
            self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200, name)

    def test_unconfirmed_self_registered_accounts_stay_blocked_and_get_a_new_link(self):
        SiteConfig.objects.filter(pk=1).update(signup_mode="open")
        self.signup()
        self.assertEqual(len(mail.outbox), 1)  # exactly one confirmation mail at sign-up
        self.assertTrue(UserProfile.objects.get(user__username="newbie").self_registered)
        self.client.logout()
        for _ in range(2):
            self.client.post(reverse("account_login"), {"login": "newbie", "password": PW})
            self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)
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
        from allauth.socialaccount.models import SocialLogin

        return SocialLogin(user=User(email=email), email_addresses=[EmailAddress(email=email, verified=verified)])

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
