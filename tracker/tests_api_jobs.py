"""The jobs, postings, documents and apply API of the new app: the classic pages' rules hold, and nothing crosses between people."""
import json
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from tracker.models import Application, CVVersion, Document, DocumentKind, Event, JobSource, KnowledgeSource, Posting
from tracker.tests_api import BASE, job, person
from tracker.services import knowledge

PUBLIC_DNS = mock.patch("tracker.services.netguard.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))])


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        self.client.force_login(self.a)

    def post(self, path, body=None):
        return self.client.post(f"{BASE}{path}", data=json.dumps(body if body is not None else {}), content_type="application/json")

    def put(self, path, body):
        return self.client.put(f"{BASE}{path}", data=json.dumps(body), content_type="application/json")

    def posting(self, owner=None, **kw):
        source = JobSource.objects.create(owner=owner, name=kw.pop("name", "Board"), connector="greenhouse", board_token=kw.pop("token", "board"))
        fields = {"source": source, "url": "https://boards.example.com/1", "company": "Board", "title": "Engineer", "title_key": "board|engineer"}
        fields.update(kw)
        return Posting.objects.create(**fields)


class AddJob(Base):
    def test_adds_a_saved_job_and_reads_its_details(self):
        r = self.post("/jobs", {"company": "Globex", "role": "Backend Engineer", "description": "Remote role. Visa sponsorship is available."})
        self.assertEqual(r.status_code, 200)
        app = Application.objects.get(pk=r.json()["id"])
        self.assertEqual((app.owner, app.status.name, app.company), (self.a, "Saved", "Globex"))
        self.assertTrue(Event.objects.filter(application=app, text="Added").exists())
        self.assertEqual(app.details_source, "detected")

    def test_missing_fields_come_back_per_field(self):
        r = self.post("/jobs", {"company": "", "role": ""})
        self.assertEqual(r.status_code, 400)
        self.assertIn("company", r.json()["fields"])
        self.assertIn("role", r.json()["fields"])
        self.assertFalse(Application.objects.exists())

    def test_long_description_and_bad_date_are_refused(self):
        r = self.post("/jobs", {"company": "A", "role": "B", "description": "x" * 30001, "deadline": "soon"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("description", r.json()["fields"])
        self.assertIn("deadline", r.json()["fields"])

    @override_settings(STILLOPEN_MAX_APPLICATIONS=2)
    def test_job_limit(self):
        job(self.a)
        job(self.a)
        r = self.post("/jobs", {"company": "Third", "role": "R"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("limit of 2", r.json()["error"])
        self.assertFalse(Application.objects.filter(company="Third").exists())

    def test_the_limit_counts_only_my_own_jobs(self):
        job(self.b)
        with override_settings(STILLOPEN_MAX_APPLICATIONS=1):
            self.assertEqual(self.post("/jobs", {"company": "Mine", "role": "R"}).status_code, 200)


class QuickAdd(Base):
    @PUBLIC_DNS
    @mock.patch("tracker.services.netguard.requests.get")
    def test_returns_the_prefill_directly_and_saves_nothing(self, get, _dns):
        get.return_value = mock.Mock(
            status_code=200, is_redirect=False, headers={},
            text="<html><head><title>Backend Engineer at Globex</title></head><body><p>" + "Real job text. " * 30 + "</p></body></html>",
        )
        r = self.post("/quickadd", {"url": "https://jobs.example.com/1"})
        data = r.json()
        self.assertEqual((r.status_code, data["role"], data["company"], data["url"]), (200, "Backend Engineer", "Globex", "https://jobs.example.com/1"))
        self.assertIn("Real job text", data["description"])
        self.assertFalse(Application.objects.exists())
        self.assertNotIn("quickadd_prefill", self.client.session)

    def test_needs_a_link(self):
        self.assertEqual(self.post("/quickadd", {"url": "  "}).status_code, 400)

    def test_private_and_local_addresses_are_refused(self):
        for url in ("http://127.0.0.1/admin", "http://localhost:8000/", "ftp://example.com/x", "http://169.254.169.254/latest/meta-data/"):
            with mock.patch("tracker.services.netguard.requests.get") as get:
                r = self.post("/quickadd", {"url": url})
                self.assertEqual(r.status_code, 400, url)
                get.assert_not_called()

    @PUBLIC_DNS
    @mock.patch("tracker.services.netguard.requests.get")
    def test_a_redirect_to_a_private_address_is_refused(self, get, _dns):
        get.return_value = mock.Mock(status_code=302, is_redirect=True, headers={"location": "http://127.0.0.1/secret"}, text="")
        public = [(2, 1, 6, "", ("93.184.216.34", 443))]
        with mock.patch("tracker.services.netguard.socket.getaddrinfo", side_effect=[public, public, [(2, 1, 6, "", ("127.0.0.1", 80))]]):
            r = self.post("/quickadd", {"url": "https://jobs.example.com/1"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(get.call_count, 1)

    def test_throttled(self):
        with override_settings(STILLOPEN_QUICKADD_PER_HOUR=1), mock.patch("tracker.api.jobs.jobtext.fetch_posting", side_effect=__import__("tracker.services.jobtext", fromlist=["x"]).FetchError("nope")):
            self.assertEqual(self.post("/quickadd", {"url": "https://x.example.com"}).status_code, 400)
            self.assertEqual(self.post("/quickadd", {"url": "https://x.example.com"}).status_code, 429)


class EditJob(Base):
    def setUp(self):
        super().setUp()
        self.app = job(self.a, company="Acme", role="Dev", description="Hybrid role in Kuala Lumpur.")

    def url(self, tail="/details"):
        return f"/jobs/{self.app.pk}{tail}"

    def test_get_gives_values_options_and_fit(self):
        data = self.client.get(BASE + self.url()).json()
        self.assertEqual(data["values"]["company"], "Acme")
        self.assertIn({"value": "remote", "label": "Remote"}, data["options"]["arrangement"])
        self.assertIsInstance(data["fit"], list)

    def test_save_marks_the_details_as_set_by_hand(self):
        r = self.put(self.url(), {"company": "Acme", "role": "Dev", "country": "Malaysia", "arrangement": "remote", "notes": "hi"})
        self.assertEqual(r.status_code, 200, r.content)
        self.app.refresh_from_db()
        self.assertEqual((self.app.country, self.app.arrangement, self.app.notes, self.app.details_source), ("MY", "remote", "hi", "manual"))
        self.assertEqual(r.json()["values"]["country"], "Malaysia")

    def test_validation_errors_name_the_field(self):
        r = self.put(self.url(), {"company": "Acme", "role": "Dev", "country": "Narnia", "arrangement": "mars"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("country", r.json()["fields"])
        self.assertIn("arrangement", r.json()["fields"])
        r = self.put(self.url(), {"company": "", "role": "Dev"})
        self.assertIn("company", r.json()["fields"])

    def test_redetect_fills_blanks_but_leaves_manual_details_alone(self):
        r = self.post(self.url("/redetect"))
        self.assertEqual(r.status_code, 200)
        self.app.refresh_from_db()
        self.assertEqual(self.app.arrangement, "hybrid")
        self.assertEqual(self.app.details_source, "detected")
        self.put(self.url(), {"company": "Acme", "role": "Dev", "arrangement": "remote"})
        r = self.post(self.url("/redetect"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("set these details yourself", r.json()["error"])
        self.app.refresh_from_db()
        self.assertEqual(self.app.arrangement, "remote")

    def test_someone_elses_job_is_a_404(self):
        other = job(self.b)
        for call in (self.client.get(f"{BASE}/jobs/{other.pk}/details"), self.put(f"/jobs/{other.pk}/details", {"company": "X", "role": "Y"}), self.post(f"/jobs/{other.pk}/redetect")):
            self.assertEqual(call.status_code, 404)
        other.refresh_from_db()
        self.assertEqual(other.company, "Acme")


class Postings(Base):
    def test_lists_only_visible_sources_with_tracked_state_and_filters(self):
        mine = self.posting(name="Shared", token="shared", title="Python Engineer", url="https://b.example.com/1")
        self.posting(name="Shared2", token="s2", title="Cook", company="Diner", url="https://b.example.com/2", title_key="diner|cook")
        self.posting(owner=self.b, name="BobOnly", token="bob", title="Secret", url="https://b.example.com/3", title_key="bob|secret")
        job(self.a, url="https://b.example.com/1", company="Board")
        data = self.client.get(f"{BASE}/postings").json()
        self.assertEqual(sorted(p["title"] for p in data["postings"]), ["Cook", "Python Engineer"])
        self.assertNotIn("Secret", json.dumps(data))
        self.assertNotIn("BobOnly", json.dumps(data))
        tracked = {p["title"]: p["tracked"] for p in data["postings"]}
        self.assertEqual(tracked, {"Python Engineer": True, "Cook": False})
        self.assertEqual({s["name"] for s in data["sources"]}, {"Shared", "Shared2"})
        self.assertEqual([p["title"] for p in self.client.get(f"{BASE}/postings?q=python").json()["postings"]], ["Python Engineer"])
        self.assertEqual([p["title"] for p in self.client.get(f"{BASE}/postings?source={mine.source_id}").json()["postings"]], ["Python Engineer"])
        self.assertEqual(self.client.get(f"{BASE}/postings?source=abc").status_code, 400)

    def test_sort_by_company_or_title_or_an_unknown_order_is_refused(self):
        self.posting(name="S1", token="s1", company="Zebra", title="Analyst", title_key="s1|analyst")
        self.posting(name="S2", token="s2", company="Acme", title="Cook", title_key="s2|cook")
        self.assertEqual([p["company"] for p in self.client.get(f"{BASE}/postings?sort=company").json()["postings"]], ["Acme", "Zebra"])
        self.assertEqual([p["title"] for p in self.client.get(f"{BASE}/postings?sort=title").json()["postings"]], ["Analyst", "Cook"])
        self.assertEqual(self.client.get(f"{BASE}/postings?sort=bogus").status_code, 400)

    def test_pages_of_fifty(self):
        source = JobSource.objects.create(name="Big", connector="greenhouse", board_token="big")
        Posting.objects.bulk_create([Posting(source=source, url=f"https://x.example.com/{n}", title=f"T{n}", title_key=f"big|{n}") for n in range(55)])
        first = self.client.get(f"{BASE}/postings").json()
        self.assertEqual((first["total"], first["pages"], len(first["postings"])), (55, 2, 50))
        self.assertEqual(len(self.client.get(f"{BASE}/postings?page=2").json()["postings"]), 5)

    def test_repost_pattern_is_reported_as_an_observation(self):
        from tracker.models import PostingSighting
        import datetime

        p1 = self.posting(url="https://b.example.com/1")
        p2 = Posting.objects.create(source=p1.source, url="https://b.example.com/2", company="Board", title="Engineer", title_key=p1.title_key)
        PostingSighting.objects.create(posting=p1, seen_date=datetime.date(2026, 1, 1))
        PostingSighting.objects.create(posting=p2, seen_date=datetime.date(2026, 1, 8))
        rows = self.client.get(f"{BASE}/postings").json()["postings"]
        self.assertEqual({r["repost"]["distinct_urls"] for r in rows}, {2})

    def test_add_to_tracker_once(self):
        p = self.posting(location="Dhaka, Bangladesh")
        r = self.post(f"/postings/{p.pk}/add")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["created"])
        app = Application.objects.get(pk=r.json()["id"])
        self.assertEqual((app.owner, app.status.name, app.posting, app.role), (self.a, "Saved", p, "Engineer"))
        self.assertTrue(Event.objects.filter(application=app, text="Added from All postings").exists())
        again = self.post(f"/postings/{p.pk}/add").json()
        self.assertEqual((again["created"], again["id"]), (False, app.pk))
        self.assertEqual(Application.objects.count(), 1)
        row = self.client.get(f"{BASE}/postings").json()["postings"][0]
        self.assertEqual((row["tracked"], row["job_id"]), (True, app.pk))

    @override_settings(STILLOPEN_MAX_APPLICATIONS=1)
    def test_add_stops_at_the_limit(self):
        job(self.a, url="https://other.example.com")
        p = self.posting()
        r = self.post(f"/postings/{p.pk}/add")
        self.assertEqual(r.status_code, 400)
        self.assertIn("limit of 1", r.json()["error"])

    def test_someone_elses_own_source_posting_is_a_404(self):
        p = self.posting(owner=self.b, token="bobs")
        self.assertEqual(self.post(f"/postings/{p.pk}/add").status_code, 404)
        self.assertFalse(Application.objects.exists())


class Documents(Base):
    def test_list_with_limits_and_cv(self):
        KnowledgeSource.objects.create(owner=self.a, title="Mine", kind="project", text="abc")
        KnowledgeSource.objects.create(owner=self.a, title="CV", key="profile-cv", kind="cv", text="cv text")
        KnowledgeSource.objects.create(owner=self.b, title="Bobs", text="x")
        data = self.client.get(f"{BASE}/documents").json()
        self.assertEqual([s["title"] for s in data["sources"]], ["Mine"])
        self.assertTrue(data["cv"]["present"])
        self.assertEqual(data["limits"]["max_file_bytes"], 2 * 1024 * 1024)
        self.assertFalse(data["can_push_to_paperless"])
        self.assertNotIn("Bobs", json.dumps(data))

    def test_empty_list_has_no_cv(self):
        data = self.client.get(f"{BASE}/documents").json()
        self.assertEqual((data["sources"], data["cv"]["present"]), ([], False))

    def test_add_pasted_text(self):
        r = self.post("/documents", {"title": "Project X", "kind": "project", "text": "Built a thing with Django."})
        self.assertEqual(r.status_code, 200, r.content)
        source = KnowledgeSource.objects.get(pk=r.json()["id"])
        self.assertEqual((source.owner, source.kind), (self.a, "project"))
        self.assertGreaterEqual(r.json()["passages"], 1)

    def test_add_needs_text_or_a_file_and_a_title(self):
        r = self.post("/documents", {"title": "Empty", "kind": "other", "text": ""})
        self.assertEqual(r.status_code, 400)
        self.assertIn("text", r.json()["fields"])
        r = self.post("/documents", {"title": "", "text": "hello"})
        self.assertIn("title", r.json()["fields"])

    def test_upload_keeps_the_text_and_never_the_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            upload = SimpleUploadedFile("notes.txt", b"Led a team of five.", content_type="text/plain")
            r = self.client.post(f"{BASE}/documents", {"title": "Notes", "kind": "experience", "file": upload})
            self.assertEqual(r.status_code, 200, r.content)
            source = KnowledgeSource.objects.get(pk=r.json()["id"])
            self.assertEqual(source.text, "Led a team of five.")
            self.assertFalse(source.file)
            self.assertEqual(list(__import__("pathlib").Path(media).rglob("*.txt")), [])

    def test_upload_limits_and_types(self):
        big = SimpleUploadedFile("big.txt", b"x" * (knowledge.MAX_FILE_BYTES + 1), content_type="text/plain")
        r = self.client.post(f"{BASE}/documents", {"title": "Big", "file": big})
        self.assertEqual(r.status_code, 400)
        self.assertIn("2 MB", r.json()["fields"]["file"][0])
        exe = SimpleUploadedFile("run.exe", b"MZ", content_type="application/octet-stream")
        r = self.client.post(f"{BASE}/documents", {"title": "Nope", "file": exe})
        self.assertEqual(r.status_code, 400)
        self.assertIn("file", r.json()["fields"])
        self.assertFalse(KnowledgeSource.objects.exists())

    @override_settings(STILLOPEN_MAX_KNOWLEDGE=1)
    def test_document_limit(self):
        KnowledgeSource.objects.create(owner=self.a, title="One", text="x")
        r = self.post("/documents", {"title": "Two", "text": "y"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("limit of 1", r.json()["error"])

    def test_toggle_and_delete(self):
        s = KnowledgeSource.objects.create(owner=self.a, title="One", text="some text here")
        self.assertEqual(self.post(f"/documents/{s.pk}/toggle").json()["enabled"], False)
        s.refresh_from_db()
        self.assertFalse(s.enabled)
        self.assertEqual(self.post(f"/documents/{s.pk}/toggle").json()["enabled"], True)
        self.assertEqual(self.client.delete(f"{BASE}/documents/{s.pk}").status_code, 200)
        self.assertFalse(KnowledgeSource.objects.filter(pk=s.pk).exists())

    def test_someone_elses_document_is_a_404(self):
        s = KnowledgeSource.objects.create(owner=self.b, title="Bobs", text="x")
        self.assertEqual(self.post(f"/documents/{s.pk}/toggle").status_code, 404)
        self.assertEqual(self.client.delete(f"{BASE}/documents/{s.pk}").status_code, 404)
        s.refresh_from_db()
        self.assertTrue(s.enabled)

    def test_paperless_is_for_admins_only(self):
        kind = DocumentKind.objects.first()
        mine = Document.objects.create(application=job(self.a), kind=kind, title="cv.pdf")
        theirs = Document.objects.create(application=job(self.b), kind=kind, title="cv.pdf")
        self.assertEqual(self.post(f"/documents/files/{mine.pk}/paperless").status_code, 403)
        self.assertEqual(self.post(f"/documents/files/{theirs.pk}/paperless").status_code, 404)
        self.a.is_staff = True
        self.a.save()
        self.assertEqual(self.post(f"/documents/files/{theirs.pk}/paperless").status_code, 404)
        self.assertTrue(self.client.get(f"{BASE}/documents").json()["can_push_to_paperless"])
        with mock.patch("tracker.api.documents.PaperlessClient.from_config", side_effect=__import__("tracker.services.paperless", fromlist=["x"]).PaperlessError("Paperless is not set up.")):
            r = self.post(f"/documents/files/{mine.pk}/paperless")
        self.assertEqual((r.status_code, r.json()["error"]), (400, "Paperless is not set up."))


class Apply(Base):
    def setUp(self):
        super().setUp()
        self.app = job(self.a, company="Acme", role="Dev", url="https://acme.example.com/1")
        self.master = CVVersion.objects.create(owner=self.a, kind="master", content="# Me\n- built things", label="My CV", approved=True)

    def path(self, tail=""):
        return f"/jobs/{self.app.pk}{tail}"

    def test_page_data(self):
        data = self.client.get(BASE + self.path("/apply")).json()
        self.assertEqual(data["job"]["company"], "Acme")
        self.assertEqual([v["id"] for v in data["versions"]], [self.master.pk])
        self.assertEqual(data["selected"], self.master.pk)
        self.assertTrue(any(c["level"] in ("ok", "warn", "info") for c in data["checks"]))
        self.assertIn("Application: Dev", data["draft"]["subject"])
        self.assertIn({"value": "email", "label": "Email"}, data["channels"])
        self.assertTrue(data["versions"][0]["docx_url"].startswith("/cv/"))

    def test_no_cv_yet(self):
        self.master.delete()
        data = self.client.get(BASE + self.path("/apply")).json()
        self.assertEqual((data["versions"], data["selected"]), ([], None))

    def test_record_sets_applied_and_schedules_the_follow_up(self):
        r = self.post(self.path("/applied"), {"cv": self.master.pk, "channel": "email", "note": "Spoke to Sam", "days": 7})
        self.assertEqual(r.status_code, 200, r.content)
        self.app.refresh_from_db()
        self.assertEqual((self.app.status.name, self.app.applied_cv, self.app.applied_channel, self.app.applied_note), ("Applied", self.master, "email", "Spoke to Sam"))
        self.assertIsNotNone(self.app.follow_up_date)
        self.assertEqual(r.json()["follow_up_date"], self.app.follow_up_date.isoformat())
        self.assertTrue(Event.objects.filter(application=self.app, kind="applied").exists())

    def test_record_with_a_different_cv(self):
        self.assertEqual(self.post(self.path("/applied"), {"cv": None, "days": 5}).status_code, 200)
        self.app.refresh_from_db()
        self.assertIsNone(self.app.applied_cv)

    def test_a_closed_posting_needs_a_confirmation(self):
        Application.objects.filter(pk=self.app.pk).update(live_state="expired")
        r = self.post(self.path("/applied"), {"cv": self.master.pk})
        self.assertEqual(r.status_code, 400)
        self.assertIn("looks closed", r.json()["error"])
        self.assertEqual(self.post(self.path("/applied"), {"cv": self.master.pk, "confirm_closed": True}).status_code, 200)

    def test_bad_input_is_refused_in_plain_words(self):
        for body in ({"days": 0}, {"days": 500}, {"channel": "pigeon"}, {"applied_on": "31/12/2026"}, {"applied_on": "2999-01-01"}):
            r = self.post(self.path("/applied"), body)
            self.assertEqual(r.status_code, 400, body)
        self.app.refresh_from_db()
        self.assertEqual(self.app.status.name, "Evaluated")

    def test_flagged_unapproved_and_foreign_cvs_are_refused(self):
        flagged = CVVersion.objects.create(owner=self.a, kind="tailored", application=self.app, content="# Me\n- Kubernetes", label="T", parent=self.master,
                                           check_report=[{"kind": "name", "text": "Kubernetes", "line": 2}])
        r = self.post(self.path("/applied"), {"cv": flagged.pk})
        self.assertEqual(r.status_code, 400)
        data = self.client.get(BASE + self.path("/apply")).json()
        self.assertNotIn(flagged.pk, [v["id"] for v in data["versions"]])
        self.assertTrue(data["has_flagged"])
        theirs = CVVersion.objects.create(owner=self.b, kind="master", content="# Bob", label="B", approved=True)
        self.assertEqual(self.post(self.path("/applied"), {"cv": theirs.pk}).status_code, 404)
        self.app.refresh_from_db()
        self.assertIsNone(self.app.applied_cv)

    def test_followup_done_and_snooze(self):
        self.post(self.path("/applied"), {"cv": self.master.pk, "days": 2})
        r = self.post(self.path("/followup/snooze"), {"days": 10})
        self.assertEqual(r.status_code, 200)
        self.app.refresh_from_db()
        self.assertEqual(r.json()["follow_up_date"], self.app.follow_up_date.isoformat())
        self.assertEqual(self.post(self.path("/followup/done")).status_code, 200)
        self.app.refresh_from_db()
        self.assertIsNone(self.app.follow_up_date)

    def test_someone_elses_job_is_a_404(self):
        other = job(self.b)
        self.assertEqual(self.client.get(f"{BASE}/jobs/{other.pk}/apply").status_code, 404)
        self.assertEqual(self.post(f"/jobs/{other.pk}/applied", {}).status_code, 404)
        self.assertEqual(self.post(f"/jobs/{other.pk}/followup/done").status_code, 404)
        self.assertEqual(self.post(f"/jobs/{other.pk}/followup/snooze", {"days": 3}).status_code, 404)
        other.refresh_from_db()
        self.assertEqual(other.status.name, "Evaluated")

    def test_nothing_is_ever_sent(self):
        from django.core import mail

        self.post(self.path("/applied"), {"cv": self.master.pk})
        self.assertEqual(mail.outbox, [])
